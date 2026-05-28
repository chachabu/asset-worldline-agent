# Asset Worldline Agent

Private cross-asset scenario forecasting dashboard.

The service is designed to ingest user-specified websites, cluster news/events, keep human-scored and model-scored branches isolated, and prepare 1W/1M/3M forecasts for macro assets, indexes, and China/US sector proxies.

## Current Status

This repository contains the initial MVP scaffold:

- FastAPI backend with session login.
- SQLAlchemy data model for sources, news, event clusters, assets, branches, jobs, and forecasts.
- Seeded branch records, model-role records, and first-pass asset universe.
- Database-backed worker/scheduler.
- Market-data snapshot service with AKShare, yfinance, Stooq, and CoinGecko fallback paths.
- LLM provider adapter for OpenAI-compatible APIs, Anthropic, and Gemini, with structured fallback output when keys or providers are unavailable.
- Double-branch prediction service that keeps human-scored and model-scored event inputs isolated.
- React/Vite research dashboard.
- Ubuntu systemd and Nginx deployment templates.
- Architecture and deployment docs under `docs/`.
- Full product design at `docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md`.

Information-source CRUD and test fetch are implemented, but scheduled article persistence and event clustering are not wired yet. Article persistence, event clustering, richer model prompts, and professional market-data adapters remain next implementation steps. The current prediction service can run with real provider keys or deterministic structured fallbacks so the branch, job, snapshot, and forecast flows can be exercised early.

## Documentation

- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Product Design](docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md)

## Local Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
cp ../.env.example .env
python -m app.cli init-db
uvicorn app.main:app --reload
```

For better market coverage:

```bash
pip install -e ".[market,pdf]"
```

Development defaults create an `admin` user with password `admin` when no bootstrap password is provided and `ENVIRONMENT` is not production.

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Worker

In another shell:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.worker
```

The scheduler can be started separately:

```bash
python -m app.workers.scheduler
```

Manual prediction and market snapshot jobs can also be created from the Web UI.

## Model Providers

Provider API keys are read from environment variables:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
DEEPSEEK_API_KEY
QWEN_API_KEY
STEPFUN_API_KEY
OPENROUTER_API_KEY
```

If a configured provider is disabled or missing a key, the service stores an auditable fallback response instead of failing the run.

## Production Layout

Recommended paths:

```text
/opt/asset-worldline
/etc/asset-worldline/config.env
/var/lib/asset-worldline
/var/log/asset-worldline
```

Services:

```text
asset-worldline-web.service
asset-worldline-worker.service
asset-worldline-scheduler.service
```

## Security Notes

- Do not commit real API keys.
- Provider keys should live in `/etc/asset-worldline/config.env`.
- The UI only configures provider/model role mapping; it does not display API keys.
- Public deployments should run behind Nginx with HTTPS.
