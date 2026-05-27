from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utcnow
from app.models import Asset, AssetGroup, MarketPrice, MarketSnapshot


@dataclass(frozen=True)
class MarketQuote:
    asset_id: int
    symbol: str
    price: float | None
    currency: str | None
    as_of: Any
    source: str
    adjusted: bool = False
    fetch_status: str = "ok"
    historical_features: dict[str, Any] = field(default_factory=dict)


class MarketDataService:
    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds

    def create_snapshot(
        self,
        db: Session,
        snapshot_type: str = "daily",
        asset_ids: list[int] | None = None,
    ) -> MarketSnapshot:
        query = select(Asset).where(Asset.enabled.is_(True)).order_by(Asset.symbol)
        if asset_ids:
            query = query.where(Asset.id.in_(asset_ids))
        assets = db.scalars(query).all()

        snapshot = MarketSnapshot(
            snapshot_type=snapshot_type,
            captured_at=utcnow(),
            source_summary={
                "requested_assets": len(assets),
                "providers": ["akshare", "yfinance", "stooq", "coingecko"],
            },
        )
        db.add(snapshot)
        db.flush()

        for asset in assets:
            quote = self.fetch_quote(asset)
            db.add(
                MarketPrice(
                    snapshot_id=snapshot.id,
                    asset_id=asset.id,
                    price=quote.price,
                    currency=quote.currency or asset.currency,
                    as_of=quote.as_of,
                    source=quote.source,
                    adjusted=quote.adjusted,
                    fetch_status=quote.fetch_status,
                    historical_features=quote.historical_features,
                )
            )
        db.commit()
        db.refresh(snapshot)
        return snapshot

    def fetch_quote(self, asset: Asset) -> MarketQuote:
        providers = asset.data_sources or []
        if asset.asset_type == "crypto" or asset.market == "crypto":
            quote = self._fetch_coingecko(asset)
            if quote.fetch_status == "ok":
                return quote

        if asset.market in {"cn", "hk"}:
            quote = self._fetch_akshare(asset)
            if quote.fetch_status == "ok":
                return quote

        if "yfinance" in providers or asset.market in {"us", "global", "hk", "cn"}:
            quote = self._fetch_yfinance(asset)
            if quote.fetch_status == "ok":
                return quote

        if "stooq" in providers:
            quote = self._fetch_stooq(asset)
            if quote.fetch_status == "ok":
                return quote

        return MarketQuote(
            asset_id=asset.id,
            symbol=asset.symbol,
            price=None,
            currency=asset.currency,
            as_of=utcnow(),
            source="none",
            fetch_status="failed",
            historical_features={},
        )

    def latest_price_by_asset(self, db: Session, asset_ids: list[int]) -> dict[int, MarketPrice]:
        if not asset_ids:
            return {}
        prices = db.scalars(
            select(MarketPrice)
            .where(MarketPrice.asset_id.in_(asset_ids))
            .order_by(MarketPrice.asset_id.asc(), MarketPrice.as_of.desc().nullslast(), MarketPrice.id.desc())
        ).all()
        latest: dict[int, MarketPrice] = {}
        for price in prices:
            latest.setdefault(price.asset_id, price)
        return latest

    def latest_snapshot(self, db: Session) -> MarketSnapshot | None:
        return db.scalars(select(MarketSnapshot).order_by(MarketSnapshot.captured_at.desc()).limit(1)).first()

    def latest_snapshot_with_prices(self, db: Session) -> MarketSnapshot | None:
        return db.scalars(
            select(MarketSnapshot)
            .options(selectinload(MarketSnapshot.prices))
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(1)
        ).first()

    def ensure_recent_snapshot(self, db: Session, max_age_hours: int = 24) -> MarketSnapshot:
        snapshot = self.latest_snapshot(db)
        if snapshot and snapshot.captured_at:
            captured_at = snapshot.captured_at
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=UTC)
            if captured_at >= utcnow() - timedelta(hours=max_age_hours):
                return snapshot
        return self.create_snapshot(db, snapshot_type="prediction_base")

    def _fetch_yfinance(self, asset: Asset) -> MarketQuote:
        try:
            import yfinance as yf  # type: ignore[import-not-found]

            ticker = yf.Ticker(asset.symbol)
            history = ticker.history(period="6mo", interval="1d", auto_adjust=False)
            if history.empty:
                return self._failed_quote(asset, "yfinance", "empty_history")
            close = history["Close"].dropna()
            if close.empty:
                return self._failed_quote(asset, "yfinance", "empty_close")
            price = float(close.iloc[-1])
            as_of = close.index[-1].to_pydatetime()
            features = self._historical_features([float(value) for value in close.tail(130).tolist()])
            currency = None
            try:
                currency = ticker.fast_info.get("currency")
            except Exception:  # noqa: BLE001 - optional metadata should not fail quote
                currency = None
            return MarketQuote(
                asset_id=asset.id,
                symbol=asset.symbol,
                price=price,
                currency=currency or asset.currency,
                as_of=as_of,
                source="yfinance",
                historical_features=features,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors must be captured as status
            return self._failed_quote(asset, "yfinance", str(exc))

    def _fetch_akshare(self, asset: Asset) -> MarketQuote:
        try:
            import akshare as ak  # type: ignore[import-not-found]

            symbol = self._akshare_symbol(asset)
            if asset.market == "hk":
                frame = ak.stock_hk_hist(symbol=symbol, period="daily", adjust="qfq")
            elif asset.asset_type == "etf":
                frame = ak.fund_etf_hist_em(symbol=symbol, period="daily", adjust="qfq")
            else:
                frame = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            if frame is None or frame.empty:
                return self._failed_quote(asset, "akshare", "empty_frame")
            close_column = self._first_existing_column(frame, ["收盘", "close", "Close"])
            date_column = self._first_existing_column(frame, ["日期", "date", "Date"])
            if not close_column:
                return self._failed_quote(asset, "akshare", "missing_close_column")
            closes = [float(value) for value in frame[close_column].dropna().tail(130).tolist()]
            if not closes:
                return self._failed_quote(asset, "akshare", "empty_close")
            as_of = utcnow()
            if date_column:
                try:
                    as_of = self._coerce_datetime(frame[date_column].dropna().iloc[-1])
                except Exception:  # noqa: BLE001
                    as_of = utcnow()
            return MarketQuote(
                asset_id=asset.id,
                symbol=asset.symbol,
                price=closes[-1],
                currency=asset.currency or ("HKD" if asset.market == "hk" else "CNY"),
                as_of=as_of,
                source="akshare",
                historical_features=self._historical_features(closes),
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed_quote(asset, "akshare", str(exc))

    def _fetch_stooq(self, asset: Asset) -> MarketQuote:
        stooq_symbol = self._stooq_symbol(asset)
        url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
            rows = response.text.strip().splitlines()
            if len(rows) < 2:
                return self._failed_quote(asset, "stooq", "empty_csv")
            values = rows[-1].split(",")
            if len(values) < 5:
                return self._failed_quote(asset, "stooq", "bad_csv")
            closes = []
            for row in rows[1:][-130:]:
                columns = row.split(",")
                if len(columns) >= 5:
                    try:
                        closes.append(float(columns[4]))
                    except ValueError:
                        continue
            price = closes[-1] if closes else float(values[4])
            return MarketQuote(
                asset_id=asset.id,
                symbol=asset.symbol,
                price=price,
                currency=asset.currency,
                as_of=utcnow(),
                source="stooq",
                historical_features=self._historical_features(closes),
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed_quote(asset, "stooq", str(exc))

    def _fetch_coingecko(self, asset: Asset) -> MarketQuote:
        coin_id = {"BTC-USD": "bitcoin", "ETH-USD": "ethereum"}.get(asset.symbol)
        if not coin_id:
            return self._failed_quote(asset, "coingecko", "unsupported_crypto_symbol")
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"}
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
            data = response.json()
            price = float(data[coin_id]["usd"])
            change_24h = data[coin_id].get("usd_24h_change")
            return MarketQuote(
                asset_id=asset.id,
                symbol=asset.symbol,
                price=price,
                currency="USD",
                as_of=utcnow(),
                source="coingecko",
                historical_features={"return_1d_pct": change_24h},
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed_quote(asset, "coingecko", str(exc))

    def _historical_features(self, closes: list[float]) -> dict[str, Any]:
        clean = [value for value in closes if value > 0]
        if not clean:
            return {}
        latest = clean[-1]
        features: dict[str, Any] = {
            "last_close": latest,
            "high_3m": max(clean[-63:]),
            "low_3m": min(clean[-63:]),
        }
        for window in (20, 60, 120):
            if len(clean) > window:
                start = clean[-window - 1]
                features[f"return_{window}d_pct"] = ((latest / start) - 1) * 100
        returns = []
        for previous, current in zip(clean[-61:-1], clean[-60:], strict=False):
            if previous:
                returns.append((current / previous) - 1)
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
            features["volatility_60d_pct"] = (variance**0.5) * (252**0.5) * 100
        return features

    def _stooq_symbol(self, asset: Asset) -> str:
        symbol = asset.symbol.lower()
        if asset.market == "us" and "." not in symbol and not symbol.startswith("^"):
            return f"{symbol}.us"
        return symbol.replace("^", "")

    def _akshare_symbol(self, asset: Asset) -> str:
        return asset.symbol.upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")

    def _first_existing_column(self, frame: Any, candidates: list[str]) -> str | None:
        columns = {str(column): str(column) for column in frame.columns}
        for candidate in candidates:
            if candidate in columns:
                return columns[candidate]
        return None

    def _coerce_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if hasattr(value, "to_pydatetime"):
            converted = value.to_pydatetime()
            return converted if converted.tzinfo else converted.replace(tzinfo=UTC)
        if isinstance(value, str):
            try:
                converted = datetime.fromisoformat(value)
                return converted if converted.tzinfo else converted.replace(tzinfo=UTC)
            except ValueError:
                return utcnow()
        return utcnow()

    def _failed_quote(self, asset: Asset, source: str, error: str) -> MarketQuote:
        return MarketQuote(
            asset_id=asset.id,
            symbol=asset.symbol,
            price=None,
            currency=asset.currency,
            as_of=utcnow(),
            source=source,
            fetch_status=f"failed:{error[:70]}",
            historical_features={},
        )


def latest_primary_prices(db: Session, groups: list[AssetGroup]) -> dict[int, MarketPrice]:
    primary_ids = [
        asset.id
        for group in groups
        for asset in group.assets
        if asset.role == "primary" and asset.enabled
    ]
    return MarketDataService().latest_price_by_asset(db, primary_ids)
