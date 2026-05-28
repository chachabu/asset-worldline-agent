# Deployment

This guide deploys Asset Worldline Agent to a single Ubuntu server with PostgreSQL, systemd, and Nginx.

## Target Layout

```text
/opt/asset-worldline              # application checkout
/etc/asset-worldline/config.env   # secrets and runtime config
/var/lib/asset-worldline          # private runtime data
/var/log/asset-worldline          # optional log directory
```

systemd services:

```text
asset-worldline-web.service
asset-worldline-worker.service
asset-worldline-scheduler.service
```

## 1. Install System Packages

```bash
sudo apt update
sudo apt install -y \
  git curl build-essential nginx postgresql postgresql-contrib \
  python3 python3-venv python3-pip nodejs npm
```

Python `3.12+` is recommended because the backend package declares `requires-python >=3.12`.

## 2. Create App User and Directories

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin asset-worldline 2>/dev/null || true
sudo mkdir -p /opt/asset-worldline /etc/asset-worldline /var/lib/asset-worldline /var/log/asset-worldline
sudo chown -R asset-worldline:asset-worldline /opt/asset-worldline /var/lib/asset-worldline /var/log/asset-worldline
```

## 3. Clone the Repository

```bash
sudo -u asset-worldline git clone git@github.com:chachabu/asset-worldline-agent.git /opt/asset-worldline
```

If the server does not have GitHub SSH deploy access, clone with HTTPS or copy a release tarball instead.

## 4. Create PostgreSQL Database

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE USER asset_worldline WITH PASSWORD 'change-this-password';
CREATE DATABASE asset_worldline OWNER asset_worldline;
\q
```

## 5. Configure Environment

Create `/etc/asset-worldline/config.env`:

```bash
sudo install -o root -g asset-worldline -m 0640 /opt/asset-worldline/.env.example /etc/asset-worldline/config.env
sudo nano /etc/asset-worldline/config.env
```

Minimum required values:

```text
DATABASE_URL=postgresql+psycopg2://asset_worldline:change-this-password@127.0.0.1:5432/asset_worldline
SECRET_KEY=replace-with-a-long-random-secret
ADMIN_BOOTSTRAP_USER=admin
ADMIN_BOOTSTRAP_PASSWORD=replace-before-first-start
```

Optional provider keys:

```text
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

Do not commit this file.

## 6. Install Backend Dependencies

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline python3 -m venv .venv
sudo -u asset-worldline .venv/bin/pip install --upgrade pip
sudo -u asset-worldline .venv/bin/pip install -e ".[market,pdf]"
```

If market/PDF extras are slow or unavailable, use the minimal install first:

```bash
sudo -u asset-worldline .venv/bin/pip install -e .
```

## 7. Build Frontend

```bash
cd /opt/asset-worldline/frontend
sudo -u asset-worldline npm install
sudo -u asset-worldline npm run build
```

The built files are written to:

```text
/opt/asset-worldline/frontend/dist
```

FastAPI serves these files in production.

## 8. Initialize Database

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli init-db'
```

To rotate or create the admin password later:

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli create-admin --username admin --password "new-password"'
```

## 9. Install systemd Services

```bash
sudo cp /opt/asset-worldline/deploy/systemd/asset-worldline-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now asset-worldline-web.service
sudo systemctl enable --now asset-worldline-worker.service
sudo systemctl enable --now asset-worldline-scheduler.service
```

Check status:

```bash
systemctl status asset-worldline-web.service
systemctl status asset-worldline-worker.service
systemctl status asset-worldline-scheduler.service
```

Logs:

```bash
journalctl -u asset-worldline-web.service -f
journalctl -u asset-worldline-worker.service -f
journalctl -u asset-worldline-scheduler.service -f
```

## 10. Configure Nginx

```bash
sudo cp /opt/asset-worldline/deploy/nginx/asset-worldline.conf /etc/nginx/sites-available/asset-worldline.conf
sudo ln -sf /etc/nginx/sites-available/asset-worldline.conf /etc/nginx/sites-enabled/asset-worldline.conf
sudo nginx -t
sudo systemctl reload nginx
```

The template listens on port `80` and proxies to `127.0.0.1:8000`.

For public deployment, add HTTPS with Certbot or your existing certificate automation before exposing the service.

## 11. Smoke Test

Local server checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1/health
```

Expected:

```json
{"status":"ok"}
```

Then open the server URL in a browser and log in with the configured admin account.

Recommended first UI checks:

1. Open `System Status` and enqueue a market snapshot.
2. Open `Forecast Matrix` and run `model_scored`.
3. Confirm a job appears in `System Status`.
4. Confirm forecast rows appear after the worker completes the job.

## 12. Common Operations

Restart after code or config changes:

```bash
sudo systemctl restart asset-worldline-web.service
sudo systemctl restart asset-worldline-worker.service
sudo systemctl restart asset-worldline-scheduler.service
```

Pull latest code:

```bash
cd /opt/asset-worldline
sudo -u asset-worldline git pull --ff-only
cd backend
sudo -u asset-worldline .venv/bin/pip install -e ".[market,pdf]"
cd ../frontend
sudo -u asset-worldline npm install
sudo -u asset-worldline npm run build
sudo systemctl restart asset-worldline-web.service asset-worldline-worker.service asset-worldline-scheduler.service
```

Backup database:

```bash
sudo -u postgres pg_dump asset_worldline > asset_worldline_$(date +%F).sql
```

Backup runtime data:

```bash
sudo tar -czf asset_worldline_data_$(date +%F).tar.gz /var/lib/asset-worldline
```

## Troubleshooting

Web service starts but UI is blank:

- Run `npm run build` under `/opt/asset-worldline/frontend`.
- Confirm `/opt/asset-worldline/frontend/dist/index.html` exists.
- Check `journalctl -u asset-worldline-web.service -n 200`.

Login fails:

- Confirm `ADMIN_BOOTSTRAP_USER` and password are correct.
- Run `create-admin` to reset the password.
- Confirm `SECRET_KEY` is stable between restarts.

Market snapshot job fails:

- Check worker logs with `journalctl -u asset-worldline-worker.service -n 200`.
- Confirm optional dependencies were installed with `pip install -e ".[market,pdf]"`.
- Some free providers may intermittently fail; failed quote rows are stored with `fetch_status`.

LLM output falls back instead of calling a provider:

- Confirm the role in Model Config uses a supported provider.
- Confirm the corresponding API key exists in `/etc/asset-worldline/config.env`.
- Restart the web and worker services after changing provider keys.
