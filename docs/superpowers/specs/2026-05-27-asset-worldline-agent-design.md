# Asset Worldline Agent Design

Date: 2026-05-27

## Summary

Asset Worldline Agent is a private research web service for cross-asset scenario forecasting. It ingests news, research notes, announcements, policy updates, and industry data from user-specified websites, then runs two isolated scoring branches:

- Human-scored branch: only user-scored event clusters can affect forecasts.
- Model-scored branch: all event clusters are scored automatically by an LLM and never read human scores.

Both branches produce 1-week, 1-month, and 3-month forecasts for a controlled universe of global macro assets, market indexes, and China/US sector proxies. Forecasts include direction, current price, target price, support/resistance, invalidation levels, bull/base/bear scenarios, evidence chains, model disagreements, and branch comparisons.

The service is deployed as a single-server Ubuntu application managed by systemd, backed by PostgreSQL, and protected by application-level admin login.

## Goals

- Let the user configure concrete websites as information sources.
- Normalize articles, PDFs, and RSS items into deduplicated event clusters.
- Keep human-scored and model-scored branches strictly isolated.
- Use three specialist LLM roles plus a judge model to produce structured forecasts.
- Forecast 1W, 1M, and 3M price paths for a fixed initial universe of about 25-35 display objects.
- Bind sector/theme opinions to tradable or priceable proxy assets so forecasts can be reviewed later.
- Provide a dense research dashboard rather than a chat-first interface.
- Support Ubuntu deployment with systemd services, PostgreSQL, logs, and environment-based secrets.

## Non-Goals

- No automated trading or order execution.
- No high-frequency or tick-level market data.
- No paid-wall, captcha, login bypass, or aggressive anti-bot circumvention.
- No full multi-user team workflow in the first version.
- No redistributing full copyrighted research content as a product feature.
- No guarantee that model-generated targets are investment advice.

## Deployment Shape

The first version runs as a single-server web service:

```text
Ubuntu Server
├── Nginx
├── asset-worldline-web.service
├── asset-worldline-worker.service
├── asset-worldline-scheduler.service
├── PostgreSQL
├── /etc/asset-worldline/config.env
├── /var/lib/asset-worldline
└── /var/log/asset-worldline
```

Recommended stack:

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL.
- Worker/scheduler: database-backed job queue for MVP; Redis/RQ or Celery can be added later.
- Frontend: React + Vite.
- Extraction: httpx, trafilatura/readability-style extraction, PyMuPDF or pypdf, optional Playwright fallback.
- Market data: yfinance, Stooq, AKShare, CoinGecko/Binance, FRED, and limited Alpha Vantage validation.

## Authentication

The first version uses application-level admin login:

- Username/password login.
- Passwords stored as argon2 or bcrypt hashes.
- Session cookie with configurable lifetime.
- One admin user for MVP.
- No registration, password reset, OAuth, or roles.

All pages and API routes require authentication except login and health checks. Sensitive actions require an authenticated admin session:

- Edit information sources.
- Configure model roles.
- Trigger forecasts.
- Edit asset universe.
- Delete or disable records.

Provider API keys are read from server environment/config files and are never displayed in clear text in the UI.

## Information Sources

Users add concrete websites from the UI. Each source has:

- Name.
- Source type: financial news, institution/research, company announcement/IR, policy/regulator/central bank, industry association/data, macro calendar, or other.
- Entry URL.
- Fetch mode: RSS, list page, article URL, or PDF URL.
- Language and region.
- Default tags.
- Source weight.
- Fetch frequency.
- Enabled/disabled state.
- Optional browser-rendering flag.
- Optional CSS selectors and URL include/exclude rules.

The source page must include a "test fetch" action that shows candidate articles, timestamps, links, text snippets, and extraction errors before the source is trusted.

Supported in MVP:

- RSS feeds.
- Public list pages.
- Public article pages.
- Manual single-link ingestion.
- Basic PDF text extraction.

Not supported in MVP:

- Login-only content.
- Paid-wall content.
- Captcha.
- Strong Cloudflare or similar anti-bot flows.
- WeChat public account scraping.
- App-only content.

## News Normalization

Fetched content is normalized into `raw_news` records:

- Title.
- Source.
- Source type.
- URL and canonical URL.
- Published time.
- Fetched time.
- Language and region.
- Raw and extracted text.
- Summary.
- Content hash.
- Extraction status.

Raw news is deduplicated and clustered:

1. Normalize URLs.
2. Deduplicate by URL and content hash.
3. Cluster similar titles and summaries.
4. Produce an `event_cluster`.

Event clusters store:

- Canonical title.
- Earliest and latest publish time.
- Source count.
- Source types.
- Representative article.
- Neutral summary.
- Related assets/themes candidates.
- Member articles.

Neutral extraction such as summary, facts, entities, companies, tickers, sectors, and possible affected regions may be shared by both branches. Importance scores, ranking, forecast inputs, model outputs, and forecast results must remain branch-specific.

## Asset Universe

The first version uses about 25-35 display objects.

Display objects are grouped into:

- Macro assets.
- Market indexes.
- Sector/theme groups.

Macro assets:

- US dollar index.
- US 10-year Treasury yield.
- Gold.
- Crude oil.
- Copper.
- BTC.
- ETH.
- USD/CNH or RMB exchange rate.
- VIX or equivalent risk proxy.

Reference indexes:

- S&P 500.
- Nasdaq 100.
- CSI 300.
- ChiNext or STAR/technology proxy.
- Hang Seng Tech.

Initial sector/theme groups:

- Semiconductors.
- AI compute/data centers.
- Power/utilities.
- Grid equipment.
- Nuclear power.
- Oil and gas.
- Gold/precious metals.
- Banks.
- Defense.
- Innovative drugs/healthcare.
- Nonferrous metals/copper.
- Robotics/automation.

Each sector/theme has region-level proxy bindings:

```text
theme: Semiconductors
US primary proxy: SMH
US supporting proxies: SOXX, NVDA, AMD, MU, TSM
CN/HK primary proxy: configured semiconductor ETF
CN/HK supporting proxies: configured chip ETF and key listed companies
```

Theme forecasts are displayed at group level, but price targets belong to the primary proxy. Supporting proxies help identify divergence and improve review quality.

## Market Data

The first version uses free data sources with fallback:

- US stocks/ETFs and some global assets: yfinance primary, Stooq fallback.
- China/HK assets and ETFs: AKShare primary, Stooq or later Eastmoney/Sina adapters as fallback.
- Macro: FRED.
- Crypto: CoinGecko primary, Binance market endpoints fallback.
- Alpha Vantage: limited key-symbol validation due to free-tier limits.

Market data records must include:

- Asset.
- Price.
- Currency.
- Timestamp.
- Source.
- Whether the value is current, delayed, daily, or stale.
- Adjusted/raw flag.
- Fetch status.
- Historical features.

Forecast runs save immutable prediction-base snapshots so later reviews use the same starting prices and historical context that the model saw.

Refresh model:

- Full asset universe: daily after major market closes.
- Watchlist: intraday every 30-60 minutes during relevant market hours.
- Forecast base snapshot: captured before each forecast run.

## Branch Isolation

The system has two fixed branches:

```text
human_scored
model_scored
```

Shared inputs:

- Raw news.
- Event clusters.
- Neutral summaries/entities.
- Asset universe.
- Market snapshots.
- Source metadata.

Isolated data:

- Event scores.
- Selected forecast context.
- Prompt input ordering.
- Agent discussions.
- Forecast outputs.
- Target prices.
- Evaluations.

All branch-specific records carry `branch_id`.

Human branch rules:

- Only manually scored event clusters with score greater than 0 can enter forecasts.
- Score 0 means ignored.
- Unscored event clusters never enter human branch forecasts.
- User scores include importance, impact direction, impact horizons, related assets/themes, and optional notes.

Model branch rules:

- All event clusters are scored automatically.
- The model scorer cannot read human scores.
- The model branch selects events by model importance, novelty, time decay, and source metadata.

## LLM Roles

The model pool is configurable by role:

- Auto scoring model.
- Neutral extraction/summarization model.
- Macro asset model.
- Industry/sector model.
- Market trading model.
- Judge aggregation model.

Provider keys are loaded from environment/config files. The UI configures provider/model mapping, temperature, timeout, token limits, and enabled state.

Specialist roles:

- Macro asset model: rates, dollar, inflation, central banks, commodities, risk appetite, cross-asset transmission.
- Industry/sector model: policy, supply chains, orders, inventory, margins, sector/company mapping.
- Market trading model: price levels, volatility, flows, positioning, short-term catalysts, risk/reward.
- Judge model: aggregates only the three specialist outputs and provided input data; it must not introduce new evidence.

## Forecast Workflow

Each forecast run creates a branch-specific context:

- Branch.
- Prediction run.
- Event snapshot.
- Market snapshot.
- Selected event clusters.
- Asset universe.
- Historical price features.

Discussion is structured, not free-form chat:

1. Independent round: each specialist produces forecasts and reasoning.
2. Review round: each specialist reviews the other two outputs and flags agreement, disagreement, omissions, and overreach.
3. Revision round: each specialist updates forecasts.
4. Judge round: the judge emits final structured forecasts.

Each final forecast is keyed by:

- Branch.
- Prediction run.
- Asset group.
- Region.
- Horizon: 1W, 1M, or 3M.

Forecast output includes:

- Direction: bullish, bearish, neutral, volatile, or divergent.
- Current price.
- Base target.
- Bull target.
- Bear target.
- Support levels.
- Resistance levels.
- Invalidation level or invalidation rules.
- Confidence.
- Linked event clusters.
- Bull/base/bear scenario summaries.
- Catalysts.
- Invalidation signals.
- Model disagreement summary.

Target prices must be checked against historical volatility and recent high/low ranges. Large moves are allowed only when the model explains the event shock and confidence.

## UI

The UI is a research dashboard.

Navigation:

- Overview.
- Information Sources.
- News Pool.
- Human Scoring.
- Model Scoring.
- Forecast Matrix.
- Asset Detail.
- Branch Comparison.
- Review/Evaluation.
- Model Config.
- System Status.

Key pages:

- Overview: system health, recent jobs, latest branch runs, unscored event count, failed sources, model failures, and market heat map.
- Information Sources: add/edit/test sources and inspect fetch logs.
- News Pool: event clusters with member articles and neutral summaries.
- Human Scoring: fast 0-5 scoring plus advanced impact fields.
- Model Scoring: model scores, confidence, affected assets, reasons, and rerun controls.
- Forecast Matrix: asset rows and US/CN/global 1W/1M/3M columns with branch toggle.
- Asset Detail: price snapshot, targets, levels, scenarios, evidence, agent rounds, and proxy divergence.
- Branch Comparison: explain human-vs-model differences by asset and by event.
- Review/Evaluation: direction hit rate, target error, branch comparison, and manual event annotations.
- Model Config: role-to-model mapping and connection tests.
- System Status: job queue, failed jobs, source health, model logs, market source status, service/log paths.

The UI should be dense, restrained, and work-focused. It should not be a landing page or chat-first surface.

## Database Model

Core tables:

- `users`.
- `information_sources`.
- `raw_news`.
- `event_clusters`.
- `event_cluster_members`.
- `asset_groups`.
- `assets`.
- `market_snapshots`.
- `market_prices`.
- `branches`.
- `event_scores`.
- `prediction_runs`.
- `agent_outputs`.
- `asset_forecasts`.
- `forecast_scenarios`.
- `forecast_evaluations`.
- `model_configs`.
- `jobs`.

Important linking fields:

- `branch_id`.
- `prediction_run_id`.
- `market_snapshot_id`.
- Event cluster IDs included in a run.

## Background Jobs

The scheduler creates jobs; the worker executes jobs. Job types:

- `fetch_source`.
- `extract_article`.
- `cluster_events`.
- `auto_score_events`.
- `refresh_market_snapshot`.
- `run_prediction`.
- `evaluate_forecasts`.

Jobs store:

- Type.
- Status.
- Priority.
- Payload.
- Scheduled time.
- Start/end times.
- Error message.
- Retry count.

MVP can use a database-backed queue. Redis/RQ/Celery can be added when job volume requires it.

## Review and Evaluation

MVP evaluation:

- Pull actual proxy prices for forecast horizons.
- Compare direction against realized move.
- Compare target prices against realized prices.
- Show branch-level and asset-level target error.
- Let the user manually mark qualitative event outcomes or invalidation triggers.

Later evaluation:

- Direction hit rate by branch, asset, horizon, source type, and model role.
- Target price error distributions.
- Overconfidence detection.
- Human-vs-model scoring quality by news category.

## System Configuration

Example `/etc/asset-worldline/config.env`:

```text
DATABASE_URL=
SECRET_KEY=
ADMIN_BOOTSTRAP_USER=
ADMIN_BOOTSTRAP_PASSWORD_HASH=

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
DEEPSEEK_API_KEY=
QWEN_API_KEY=
STEPFUN_API_KEY=
OPENROUTER_API_KEY=

FRED_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

## MVP Milestones

### MVP 1: Forecast Loop

- Admin login.
- Information source CRUD and test fetch.
- RSS/list/article/PDF extraction.
- News pool and event clusters.
- Human scoring.
- Model scoring.
- Asset universe and proxy config.
- Market snapshots from free sources.
- Model role config.
- Human and model branch forecast runs.
- Forecast matrix.
- Asset details.
- Branch comparison.
- Basic evaluation.
- systemd deployment files.

### MVP 2: Quality and Review

- Stronger evaluation dashboards.
- Target error and hit-rate analytics.
- Prediction invalidation tracking.
- Better source diagnostics.
- Model scoring quality reports.
- Branch performance by asset and horizon.

### MVP 3: Research Desk Features

- Site-specific adapters.
- Better PDF/research parsing.
- Price trigger alerts.
- Feishu/email notifications.
- More market data providers.
- Forecast report export.
- Multi-user permissions.

## Reuse Guidance

Create a new project rather than modifying `TradingAgents` or existing content tools directly.

Useful references from local projects:

- `ai_hotspot_content_studio`: fetcher pattern, HTTP/browser helpers, AI client ideas, local web workflow.
- `crypto_hotspot_writer`: multi-source ingestion and ranking ideas.
- `social_media_ai_monitor`: monitor service and notification patterns.
- `TradingAgents`: multi-agent role and debate structure, not as a direct code base.

The new project should own its database schema, branch isolation model, forecast workflow, UI, and systemd deployment.

## Open Implementation Choices

These are allowed to vary during implementation without changing the product design:

- Whether frontend static assets are served by FastAPI or directly by Nginx.
- Whether the first worker uses database polling or a lightweight queue library.
- Exact UI component library.
- Exact first-pass sector proxy symbols, as long as theme-to-primary-proxy mapping exists.
- Exact market-data provider order per asset type, as long as source metadata is saved.

