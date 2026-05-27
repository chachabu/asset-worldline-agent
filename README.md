# Asset Worldline Agent

Private cross-asset scenario forecasting dashboard.

The service ingests user-specified websites, clusters news/events, keeps human-scored and model-scored branches isolated, and prepares 1W/1M/3M forecasts for macro assets, indexes, and China/US sector proxies.

## Current Status

This repository contains the initial MVP scaffold:

- FastAPI backend with session login.
- SQLAlchemy data model for sources, news, event clusters, assets, branches, jobs, and forecasts.
- Seeded branch records, model-role records, and first-pass asset universe.
- Database-backed worker/scheduler skeleton.
- React/Vite research dashboard.
- Ubuntu systemd and Nginx deployment templates.
- Full product design at `docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md`.

Real market-data adapters, LLM adapters, article persistence, event clustering, and forecast generation logic are the next implementation steps. The current worker creates neutral scaffold forecasts so the matrix and job flow can be exercised.

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

