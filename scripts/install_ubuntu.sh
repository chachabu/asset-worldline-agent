#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-asset-worldline}"
APP_DIR="${APP_DIR:-/opt/asset-worldline}"

sudo useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER" 2>/dev/null || true
sudo mkdir -p /etc/asset-worldline /var/lib/asset-worldline /var/log/asset-worldline "$APP_DIR"
sudo chown -R "$APP_USER:$APP_USER" /var/lib/asset-worldline /var/log/asset-worldline "$APP_DIR"

echo "Copy the repository to $APP_DIR, create /etc/asset-worldline/config.env, then install the systemd units from deploy/systemd."

