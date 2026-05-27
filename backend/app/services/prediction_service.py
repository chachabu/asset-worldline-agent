from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utcnow
from app.models import (
    AgentOutput,
    AssetForecast,
    AssetGroup,
    Branch,
    EventCluster,
    EventScore,
    ForecastScenario,
    MarketPrice,
    ModelConfig,
    PredictionRun,
)
from app.services.llm_client import LLMClient
from app.services.market_data import MarketDataService

HORIZONS = ("1W", "1M", "3M")
SPECIALIST_ROLES = ("macro_asset_model", "industry_sector_model", "market_trading_model")
DIRECTION_SIGNS = {
    "positive": 1.0,
    "bullish": 1.0,
    "利好": 1.0,
    "negative": -1.0,
    "bearish": -1.0,
    "利空": -1.0,
    "neutral": 0.0,
    "中性": 0.0,
    "uncertain": 0.0,
    "不确定": 0.0,
}


@dataclass(frozen=True)
class BranchContext:
    branch: Branch
    event_scores: list[EventScore]
    selected_event_ids: list[int]
    groups: list[AssetGroup]
    latest_prices: dict[int, MarketPrice]


class PredictionService:
    def __init__(
        self,
        market_data: MarketDataService | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.market_data = market_data or MarketDataService()
        self.llm_client = llm_client or LLMClient()

    def run_prediction(self, db: Session, run: PredictionRun) -> int:
        branch = db.get(Branch, run.branch_id)
        if not branch:
            raise ValueError(f"Branch {run.branch_id} not found")

        market_snapshot = self.market_data.ensure_recent_snapshot(db)
        run.market_snapshot_id = market_snapshot.id
        run.status = "running"
        run.started_at = utcnow()
        db.flush()

        model_configs = self._model_configs(db)
        if branch.name == "model_scored":
            self._auto_score_events(db, branch, model_configs)

        context = self._build_context(db, branch)
        run.selected_event_cluster_ids = context.selected_event_ids
        db.flush()

        specialist_outputs = self._run_specialist_rounds(db, run, context, model_configs)
        forecast_payload = self._judge_forecasts(db, run, context, model_configs, specialist_outputs)
        forecast_count = self._persist_forecasts(db, run, context, forecast_payload)

        run.status = "succeeded"
        run.finished_at = utcnow()
        db.commit()
        return forecast_count

    def _model_configs(self, db: Session) -> dict[str, ModelConfig]:
        configs = db.scalars(select(ModelConfig)).all()
        return {config.role: config for config in configs}

    def _auto_score_events(
        self,
        db: Session,
        branch: Branch,
        model_configs: dict[str, ModelConfig],
    ) -> None:
        clusters = db.scalars(select(EventCluster).order_by(EventCluster.created_at.desc()).limit(200)).all()
        existing_ids = set(
            db.scalars(select(EventScore.event_cluster_id).where(EventScore.branch_id == branch.id)).all()
        )
        config = model_configs.get("auto_scorer")
        for cluster in clusters:
            if cluster.id in existing_ids:
                continue
            fallback = self._fallback_score(cluster)
            result = self.llm_client.generate_structured(
                config,
                system_prompt=(
                    "Score the market importance of this event for a cross-asset forecast desk. "
                    "Return JSON with importance, confidence, novelty, direction, impact_horizons, "
                    "affected_groups, affected_assets, and reason."
                ),
                user_payload=self._cluster_payload(cluster),
                fallback=fallback,
            )
            data = {**fallback, **result.json_data}
            db.add(
                EventScore(
                    branch_id=branch.id,
                    event_cluster_id=cluster.id,
                    score_type="model",
                    importance=float(data.get("importance", 0.0)),
                    confidence=self._optional_float(data.get("confidence")),
                    novelty=self._optional_float(data.get("novelty")),
                    direction=data.get("direction") or "uncertain",
                    impact_horizons=list(data.get("impact_horizons") or HORIZONS),
                    affected_groups=list(data.get("affected_groups") or cluster.involved_themes or []),
                    affected_assets=list(data.get("affected_assets") or cluster.involved_assets or []),
                    reason=data.get("reason") or "Auto-scored by model/fallback.",
                    payload={
                        "llm": {
                            "provider": result.provider,
                            "model": result.model,
                            "prompt_hash": result.prompt_hash,
                            "used_fallback": result.used_fallback,
                        },
                        "raw": result.json_data,
                    },
                )
            )
        db.commit()

    def _build_context(self, db: Session, branch: Branch) -> BranchContext:
        groups = db.scalars(
            select(AssetGroup)
            .options(selectinload(AssetGroup.assets))
            .where(AssetGroup.enabled.is_(True))
            .order_by(AssetGroup.category.asc(), AssetGroup.name.asc())
            .limit(35)
        ).all()
        score_query = (
            select(EventScore)
            .options(selectinload(EventScore.cluster))
            .where(EventScore.branch_id == branch.id, EventScore.importance > 0)
            .order_by(EventScore.importance.desc(), EventScore.updated_at.desc())
            .limit(80)
        )
        event_scores = db.scalars(score_query).all()
        primary_ids = [
            asset.id
            for group in groups
            for asset in group.assets
            if asset.role == "primary" and asset.enabled
        ]
        latest_prices = self.market_data.latest_price_by_asset(db, primary_ids)
        return BranchContext(
            branch=branch,
            event_scores=event_scores,
            selected_event_ids=[score.event_cluster_id for score in event_scores],
            groups=groups,
            latest_prices=latest_prices,
        )

    def _run_specialist_rounds(
        self,
        db: Session,
        run: PredictionRun,
        context: BranchContext,
        model_configs: dict[str, ModelConfig],
    ) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        first_round_by_role: dict[str, dict[str, Any]] = {}
        for role in SPECIALIST_ROLES:
            fallback = self._role_fallback(role, context)
            result = self.llm_client.generate_structured(
                model_configs.get(role),
                system_prompt=self._role_prompt(role),
                user_payload=self._prediction_payload(context),
                fallback=fallback,
            )
            first_round_by_role[role] = result.json_data
            outputs.append({"role": role, "round": "independent", "data": result.json_data})
            db.add(
                AgentOutput(
                    prediction_run_id=run.id,
                    branch_id=context.branch.id,
                    role=role,
                    round_name="independent",
                    model_provider=result.provider,
                    model_name=result.model,
                    prompt_hash=result.prompt_hash,
                    output_text=result.text,
                    output_json=result.json_data,
                )
            )

        for role in SPECIALIST_ROLES:
            fallback = {
                "agreements": ["Specialists share the same branch-specific event context."],
                "disagreements": ["No external model review available in fallback mode."],
                "omissions": [],
                "overreach_warnings": [],
            }
            result = self.llm_client.generate_structured(
                model_configs.get(role),
                system_prompt=(
                    f"You are the {role}. Review other specialist outputs. "
                    "Return JSON with agreements, disagreements, omissions, and overreach_warnings."
                ),
                user_payload={"own_role": role, "first_round": first_round_by_role},
                fallback=fallback,
            )
            outputs.append({"role": role, "round": "review", "data": result.json_data})
            db.add(
                AgentOutput(
                    prediction_run_id=run.id,
                    branch_id=context.branch.id,
                    role=role,
                    round_name="review",
                    model_provider=result.provider,
                    model_name=result.model,
                    prompt_hash=result.prompt_hash,
                    output_text=result.text,
                    output_json=result.json_data,
                )
            )

        for role in SPECIALIST_ROLES:
            fallback = self._role_fallback(role, context, revised=True)
            result = self.llm_client.generate_structured(
                model_configs.get(role),
                system_prompt=(
                    f"You are the {role}. Revise your forecast after peer review. "
                    "Return structured JSON, keeping all evidence inside this branch context."
                ),
                user_payload={"context": self._prediction_payload(context), "peer_outputs": outputs},
                fallback=fallback,
            )
            outputs.append({"role": role, "round": "revision", "data": result.json_data})
            db.add(
                AgentOutput(
                    prediction_run_id=run.id,
                    branch_id=context.branch.id,
                    role=role,
                    round_name="revision",
                    model_provider=result.provider,
                    model_name=result.model,
                    prompt_hash=result.prompt_hash,
                    output_text=result.text,
                    output_json=result.json_data,
                )
            )

        db.flush()
        return outputs

    def _judge_forecasts(
        self,
        db: Session,
        run: PredictionRun,
        context: BranchContext,
        model_configs: dict[str, ModelConfig],
        specialist_outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback = {"forecasts": self._heuristic_forecasts(context)}
        result = self.llm_client.generate_structured(
            model_configs.get("judge_aggregator"),
            system_prompt=(
                "Aggregate specialist outputs into final forecasts. You may only use provided "
                "branch context and specialist outputs. Return JSON: {\"forecasts\": [...]}."
            ),
            user_payload={
                "context": self._prediction_payload(context),
                "specialist_outputs": specialist_outputs,
                "required_fields": [
                    "asset_group_id",
                    "region",
                    "horizon",
                    "direction",
                    "confidence",
                    "current_price",
                    "base_target",
                    "bull_target",
                    "bear_target",
                    "support_levels",
                    "resistance_levels",
                    "invalidation",
                    "linked_event_cluster_ids",
                    "model_disagreements",
                    "rationale",
                    "scenarios",
                ],
            },
            fallback=fallback,
        )
        db.add(
            AgentOutput(
                prediction_run_id=run.id,
                branch_id=context.branch.id,
                role="judge_aggregator",
                round_name="aggregate",
                model_provider=result.provider,
                model_name=result.model,
                prompt_hash=result.prompt_hash,
                output_text=result.text,
                output_json=result.json_data,
            )
        )
        forecasts = result.json_data.get("forecasts")
        return result.json_data if isinstance(forecasts, list) and forecasts else fallback

    def _persist_forecasts(
        self,
        db: Session,
        run: PredictionRun,
        context: BranchContext,
        forecast_payload: dict[str, Any],
    ) -> int:
        group_by_id = {group.id: group for group in context.groups}
        count = 0
        for item in forecast_payload.get("forecasts", []):
            group_id = int(item.get("asset_group_id", 0) or 0)
            group = group_by_id.get(group_id)
            if not group:
                continue
            primary = self._primary_asset_by_id(group, self._optional_int(item.get("primary_asset_id")))
            forecast = AssetForecast(
                prediction_run_id=run.id,
                branch_id=context.branch.id,
                asset_group_id=group.id,
                primary_asset_id=primary.id if primary else None,
                region=str(item.get("region") or group.region),
                horizon=str(item.get("horizon") or "1M"),
                direction=str(item.get("direction") or "neutral"),
                confidence=self._optional_float(item.get("confidence")),
                current_price=self._optional_float(item.get("current_price")),
                base_target=self._optional_float(item.get("base_target")),
                bull_target=self._optional_float(item.get("bull_target")),
                bear_target=self._optional_float(item.get("bear_target")),
                support_levels=self._float_list(item.get("support_levels")),
                resistance_levels=self._float_list(item.get("resistance_levels")),
                invalidation=item.get("invalidation"),
                linked_event_cluster_ids=list(item.get("linked_event_cluster_ids") or []),
                model_disagreements=item.get("model_disagreements"),
                rationale=item.get("rationale"),
            )
            db.add(forecast)
            db.flush()
            for scenario in item.get("scenarios") or []:
                db.add(
                    ForecastScenario(
                        forecast_id=forecast.id,
                        scenario_type=str(scenario.get("scenario_type") or "base"),
                        target_price=self._optional_float(scenario.get("target_price")),
                        summary=str(scenario.get("summary") or ""),
                        catalysts=list(scenario.get("catalysts") or []),
                        invalidations=list(scenario.get("invalidations") or []),
                    )
                )
            count += 1
        db.flush()
        return count

    def _heuristic_forecasts(self, context: BranchContext) -> list[dict[str, Any]]:
        forecasts: list[dict[str, Any]] = []
        signal, linked_ids, driver_summary = self._branch_signal(context.event_scores)
        for group in context.groups:
            for primary in self._primary_assets(group):
                price_record = context.latest_prices.get(primary.id) if primary else None
                current_price = price_record.price if price_record else None
                features = price_record.historical_features if price_record else {}
                region = primary.market if group.region == "cross_market" else group.region
                for horizon in HORIZONS:
                    pct = self._target_move_pct(signal, horizon, features)
                    direction = self._direction_from_pct(pct)
                    targets = self._targets(current_price, pct)
                    confidence = self._confidence(context.event_scores, abs(signal))
                    forecasts.append(
                        {
                            "asset_group_id": group.id,
                            "primary_asset_id": primary.id if primary else None,
                            "region": region,
                            "horizon": horizon,
                            "direction": direction,
                            "confidence": confidence,
                            "current_price": current_price,
                            "base_target": targets["base"],
                            "bull_target": targets["bull"],
                            "bear_target": targets["bear"],
                            "support_levels": self._support_levels(current_price, features),
                            "resistance_levels": self._resistance_levels(current_price, features),
                            "invalidation": self._invalidation(direction, group.name),
                            "linked_event_cluster_ids": linked_ids[:12],
                            "model_disagreements": (
                                "Fallback heuristic used; real model disagreement will appear when "
                                "provider keys are configured."
                            ),
                            "rationale": (
                                f"{context.branch.name} branch forecast for "
                                f"{primary.symbol if primary else group.name} based on "
                                f"{len(context.event_scores)} scored events. {driver_summary}"
                            ),
                            "scenarios": self._scenarios(current_price, targets, direction, group.name),
                        }
                    )
        return forecasts

    def _branch_signal(self, scores: list[EventScore]) -> tuple[float, list[int], str]:
        if not scores:
            return 0.0, [], "No scored events are available, so targets remain neutral."
        weighted = 0.0
        total = 0.0
        linked_ids: list[int] = []
        for score in scores:
            sign = DIRECTION_SIGNS.get((score.direction or "uncertain").lower(), 0.0)
            importance = max(0.0, min(float(score.importance), 5.0))
            weighted += sign * importance
            total += importance
            linked_ids.append(score.event_cluster_id)
        signal = weighted / total if total else 0.0
        return signal, linked_ids, f"Net branch signal is {signal:.2f} from {len(scores)} scored events."

    def _target_move_pct(self, signal: float, horizon: str, features: dict[str, Any]) -> float:
        horizon_magnitude = {"1W": 0.025, "1M": 0.065, "3M": 0.12}[horizon]
        volatility = self._optional_float(features.get("volatility_60d_pct")) or 25.0
        volatility_cap = min(max(volatility / 100 * {"1W": 0.35, "1M": 0.75, "3M": 1.2}[horizon], 0.015), 0.35)
        return max(min(signal * horizon_magnitude, volatility_cap), -volatility_cap)

    def _targets(self, current_price: float | None, move_pct: float) -> dict[str, float | None]:
        if not current_price:
            return {"base": None, "bull": None, "bear": None}
        span = max(abs(move_pct), 0.02)
        return {
            "base": round(current_price * (1 + move_pct), 4),
            "bull": round(current_price * (1 + move_pct + span), 4),
            "bear": round(current_price * (1 + move_pct - span), 4),
        }

    def _support_levels(self, current_price: float | None, features: dict[str, Any]) -> list[float]:
        if not current_price:
            return []
        low_3m = self._optional_float(features.get("low_3m"))
        levels = [current_price * 0.97]
        if low_3m:
            levels.append(low_3m)
        return sorted({round(level, 4) for level in levels})

    def _resistance_levels(self, current_price: float | None, features: dict[str, Any]) -> list[float]:
        if not current_price:
            return []
        high_3m = self._optional_float(features.get("high_3m"))
        levels = [current_price * 1.03]
        if high_3m:
            levels.append(high_3m)
        return sorted({round(level, 4) for level in levels})

    def _scenarios(
        self,
        current_price: float | None,
        targets: dict[str, float | None],
        direction: str,
        group_name: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "scenario_type": "base",
                "target_price": targets["base"],
                "summary": f"{group_name} follows the branch base case with {direction} bias.",
                "catalysts": ["Scored events continue to be validated by price action."],
                "invalidations": ["New events reverse the branch signal."],
            },
            {
                "scenario_type": "bull",
                "target_price": targets["bull"],
                "summary": f"{group_name} benefits from stronger risk appetite or positive confirmation.",
                "catalysts": ["Positive follow-through in related proxies."],
                "invalidations": ["Breakdown below near support."],
            },
            {
                "scenario_type": "bear",
                "target_price": targets["bear"],
                "summary": f"{group_name} reprices lower if evidence weakens or macro pressure rises.",
                "catalysts": ["Negative confirmation in news or price action."],
                "invalidations": ["Recovery above near resistance."],
            },
        ]

    def _invalidation(self, direction: str, group_name: str) -> str:
        if direction == "bullish":
            return f"{group_name} fails if price loses support while new evidence turns negative."
        if direction == "bearish":
            return f"{group_name} fails if price breaks resistance while new evidence turns positive."
        return f"{group_name} remains neutral until scored evidence or price confirms a directional break."

    def _direction_from_pct(self, pct: float) -> str:
        if pct > 0.015:
            return "bullish"
        if pct < -0.015:
            return "bearish"
        return "neutral"

    def _confidence(self, scores: list[EventScore], signal_strength: float) -> float:
        if not scores:
            return 0.2
        avg_importance = sum(score.importance for score in scores) / len(scores)
        confidence = 0.25 + min(avg_importance / 10, 0.35) + min(signal_strength * 0.25, 0.25)
        return round(min(confidence, 0.85), 3)

    def _role_fallback(self, role: str, context: BranchContext, revised: bool = False) -> dict[str, Any]:
        signal, linked_ids, driver_summary = self._branch_signal(context.event_scores)
        return {
            "role": role,
            "round": "revision" if revised else "independent",
            "branch": context.branch.name,
            "net_signal": signal,
            "linked_event_cluster_ids": linked_ids[:12],
            "summary": driver_summary,
            "watch_items": [group.name for group in context.groups[:8]],
            "used_fallback": True,
        }

    def _role_prompt(self, role: str) -> str:
        return {
            "macro_asset_model": (
                "You are the macro asset model. Focus on rates, dollar, inflation, central banks, "
                "commodities, and cross-asset transmission. Return compact JSON."
            ),
            "industry_sector_model": (
                "You are the industry sector model. Focus on policy, supply chains, earnings, "
                "orders, inventories, margins, and sector proxy mapping. Return compact JSON."
            ),
            "market_trading_model": (
                "You are the market trading model. Focus on price levels, volatility, flows, "
                "positioning, catalysts, and risk/reward. Return compact JSON."
            ),
        }[role]

    def _prediction_payload(self, context: BranchContext) -> dict[str, Any]:
        return {
            "branch": context.branch.name,
            "events": [
                {
                    "event_cluster_id": score.event_cluster_id,
                    "title": score.cluster.canonical_title,
                    "summary": score.cluster.summary,
                    "importance": score.importance,
                    "direction": score.direction,
                    "impact_horizons": score.impact_horizons,
                    "affected_groups": score.affected_groups,
                    "affected_assets": score.affected_assets,
                    "reason": score.reason,
                }
                for score in context.event_scores[:40]
            ],
            "asset_groups": [
                {
                    "id": group.id,
                    "name": group.name,
                    "category": group.category,
                    "region": group.region,
                    "primary_proxies": [
                        {"asset_id": asset.id, "symbol": asset.symbol, "market": asset.market}
                        for asset in self._primary_assets(group)
                    ],
                }
                for group in context.groups
            ],
        }

    def _cluster_payload(self, cluster: EventCluster) -> dict[str, Any]:
        return {
            "event_cluster_id": cluster.id,
            "title": cluster.canonical_title,
            "summary": cluster.summary,
            "source_count": cluster.source_count,
            "source_types": cluster.source_types,
            "involved_assets": cluster.involved_assets,
            "involved_themes": cluster.involved_themes,
            "neutral_extraction": cluster.neutral_extraction,
        }

    def _fallback_score(self, cluster: EventCluster) -> dict[str, Any]:
        high_weight_types = {"policy", "announcement", "research", "industry_data"}
        source_type_bonus = 1 if set(cluster.source_types or []).intersection(high_weight_types) else 0
        source_bonus = min(cluster.source_count, 3) * 0.5
        importance = min(5.0, 1.5 + source_bonus + source_type_bonus)
        return {
            "importance": importance,
            "confidence": 0.45,
            "novelty": 0.5,
            "direction": "uncertain",
            "impact_horizons": list(HORIZONS),
            "affected_groups": cluster.involved_themes or [],
            "affected_assets": cluster.involved_assets or [],
            "reason": "Fallback auto score based on source count and source type.",
        }

    def _primary_assets(self, group: AssetGroup):
        primaries = [asset for asset in group.assets if asset.role == "primary" and asset.enabled]
        if primaries:
            return primaries
        first_enabled = next((asset for asset in group.assets if asset.enabled), None)
        return [first_enabled] if first_enabled else [None]

    def _primary_asset_by_id(self, group: AssetGroup, asset_id: int | None):
        if asset_id:
            found = next((asset for asset in group.assets if asset.id == asset_id and asset.enabled), None)
            if found:
                return found
        return self._primary_assets(group)[0]

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _float_list(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        floats = [self._optional_float(item) for item in value]
        return [item for item in floats if item is not None]
