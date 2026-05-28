# Asset Worldline Agent Notes

This is a private investment-research workflow tool, not an automated trading system.

## Safety

- Never commit real API keys, market-data credentials, cookies, or paid-content exports.
- Treat `/etc/asset-worldline/config.env`, local `.env` files, logs, PDF downloads, and extracted articles as private data.
- Do not add trade execution features unless explicitly requested.

## Architecture

- Backend: `backend/app`, FastAPI + SQLAlchemy.
- Frontend: `frontend/src`, React + Vite.
- Deployment templates: `deploy/`.
- Architecture doc: `docs/architecture.md`.
- Deployment runbook: `docs/deployment.md`.
- Product design: `docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md`.

## Branch Isolation

The product requires strict separation between `human_scored` and `model_scored` branches. Do not let model-scored prompts, scores, forecasts, or evaluations read human scores, and do not let human-branch forecasts include unscored events.

## Deployment Preference

Target deployment is Ubuntu with systemd, PostgreSQL, and Nginx.
