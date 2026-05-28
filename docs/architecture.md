# Architecture

Asset Worldline Agent is a private research dashboard for cross-asset scenario forecasting. It is not an automated trading system.

## System Diagram

```mermaid
flowchart LR
    User[Admin User] --> Nginx[Nginx Reverse Proxy]
    Nginx --> Web[FastAPI Web/API Service]
    Web --> Frontend[React/Vite Static UI]
    Web --> DB[(PostgreSQL)]
    Web --> Jobs[Jobs Table]

    Scheduler[Scheduler Service] --> Jobs
    Worker[Worker Service] --> Jobs
    Worker --> DB

    Worker --> Sources[Configured Websites/RSS/PDF]
    Worker --> MarketData[Market Data Providers]
    Worker --> LLMs[LLM Providers]

    MarketData --> AKShare[AKShare]
    MarketData --> YFinance[yfinance]
    MarketData --> Stooq[Stooq]
    MarketData --> CoinGecko[CoinGecko]

    LLMs --> OpenAI[OpenAI-compatible]
    LLMs --> Anthropic[Anthropic]
    LLMs --> Gemini[Gemini]
```

## Runtime Services

The production deployment uses three systemd services:

| Service | Entry Point | Purpose |
|---|---|---|
| `asset-worldline-web.service` | `uvicorn app.main:app` | Serves API, sessions, and built frontend assets. |
| `asset-worldline-worker.service` | `python -m app.workers.worker` | Executes queued jobs: market snapshots and prediction runs. |
| `asset-worldline-scheduler.service` | `python -m app.workers.scheduler` | Enqueues recurring source-fetch jobs. |

PostgreSQL stores all durable state. Nginx proxies public traffic to FastAPI on `127.0.0.1:8000`.

## Core Components

```mermaid
flowchart TB
    subgraph API[FastAPI API]
        Auth[Session Auth]
        SourcesAPI[Information Sources API]
        NewsAPI[News and Scoring API]
        AssetsAPI[Asset Universe API]
        ForecastAPI[Forecast and Jobs API]
        ModelAPI[Model Config API]
    end

    subgraph Services[Backend Services]
        Fetcher[Source Fetcher]
        Market[MarketDataService]
        LLM[LLMClient]
        Predictor[PredictionService]
        Runner[JobRunner]
    end

    subgraph DB[PostgreSQL Tables]
        Users[users]
        SourceTables[information_sources/raw_news/event_clusters]
        AssetTables[asset_groups/assets/market_snapshots/market_prices]
        BranchTables[branches/event_scores/prediction_runs]
        ForecastTables[agent_outputs/asset_forecasts/forecast_scenarios]
        JobTables[jobs]
    end

    API --> DB
    Runner --> Fetcher
    Runner --> Market
    Runner --> Predictor
    Predictor --> LLM
    Services --> DB
```

## Data Flow

```mermaid
sequenceDiagram
    participant Admin as Admin UI
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Worker as Worker
    participant Market as MarketDataService
    participant LLM as LLMClient

    Admin->>API: Add information source / score events / trigger run
    API->>DB: Store source, score, or job
    Worker->>DB: Claim pending job
    Worker->>Market: Refresh prediction-base market snapshot
    Market->>DB: Save market_snapshot and market_prices
    Worker->>DB: Load branch-specific event_scores
    Worker->>LLM: Specialist and judge prompts
    LLM-->>Worker: JSON forecast output or structured fallback
    Worker->>DB: Save agent_outputs, asset_forecasts, forecast_scenarios
    Admin->>API: Load forecast matrix and details
    API->>DB: Query latest forecasts
```

## Branch Isolation

There are two fixed branches:

- `human_scored`: only manually scored event clusters with `importance > 0` enter forecasts.
- `model_scored`: event clusters are scored automatically by the model scorer.

Shared data:

- Raw news.
- Event clusters.
- Neutral summaries and entities.
- Asset universe.
- Market snapshots.
- Source metadata.

Branch-specific data:

- `event_scores`.
- `prediction_runs`.
- `agent_outputs`.
- `asset_forecasts`.
- `forecast_scenarios`.
- `forecast_evaluations`.

Every branch-specific table carries `branch_id` directly or through `prediction_run_id`.

```mermaid
flowchart LR
    Raw[raw_news] --> Clusters[event_clusters]
    Clusters --> Neutral[Neutral extraction]

    Neutral --> HumanQueue[Human scoring queue]
    HumanQueue --> HumanScores[event_scores: human_scored]
    HumanScores --> HumanRun[prediction_run: human_scored]

    Neutral --> ModelScorer[Model scorer]
    ModelScorer --> ModelScores[event_scores: model_scored]
    ModelScores --> ModelRun[prediction_run: model_scored]

    HumanRun --> HumanForecasts[asset_forecasts: human_scored]
    ModelRun --> ModelForecasts[asset_forecasts: model_scored]
```

## Forecast Workflow

`PredictionService` runs forecasts in four phases:

1. Ensure a recent market snapshot exists.
2. For `model_scored`, create missing automatic event scores.
3. Run three specialist roles:
   - `macro_asset_model`
   - `industry_sector_model`
   - `market_trading_model`
4. Run `judge_aggregator` and persist final forecasts.

If a provider is disabled, missing an API key, or returns invalid JSON, `LLMClient` stores a structured fallback response instead of failing the whole run. This keeps the job auditable and lets UI flows work before production model keys are configured.

## Market Data

`MarketDataService` attempts free providers in this order:

- CN/HK assets: AKShare first, then yfinance/Stooq fallback.
- US/global assets: yfinance first, then Stooq fallback.
- Crypto assets: CoinGecko first.

Each `market_price` stores:

- Price and currency.
- `as_of` timestamp.
- Provider source.
- Fetch status.
- Historical features such as recent returns, 3-month high/low, and volatility where available.

## Frontend

The React/Vite frontend currently exposes:

- Login.
- Overview.
- Information sources and test fetch.
- News pool.
- Human scoring.
- Asset universe.
- Forecast matrix.
- Model configuration.
- System jobs and manual market snapshot trigger.

FastAPI serves `frontend/dist` in production when the frontend is built.

