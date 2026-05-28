# 部署

这份指南用于把 Asset Worldline Agent 部署到单台 Ubuntu 服务器，依赖 PostgreSQL、systemd 和 Nginx。

## 目标目录

```text
/opt/asset-worldline              # 应用代码目录
/etc/asset-worldline/config.env   # 密钥和运行时配置
/var/lib/asset-worldline          # 私有运行时数据
/var/log/asset-worldline          # 可选日志目录
```

systemd 服务：

```text
asset-worldline-web.service
asset-worldline-worker.service
asset-worldline-scheduler.service
```

## 1. 安装系统包

```bash
sudo apt update
sudo apt install -y \
  git curl build-essential nginx postgresql postgresql-contrib \
  python3 python3-venv python3-pip nodejs npm
```

建议使用 Python `3.12+`，因为后端包声明了 `requires-python >=3.12`。

## 2. 创建应用用户和目录

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin asset-worldline 2>/dev/null || true
sudo mkdir -p /opt/asset-worldline /etc/asset-worldline /var/lib/asset-worldline /var/log/asset-worldline
sudo chown -R asset-worldline:asset-worldline /opt/asset-worldline /var/lib/asset-worldline /var/log/asset-worldline
```

## 3. Clone 仓库

```bash
sudo -u asset-worldline git clone git@github.com:chachabu/asset-worldline-agent.git /opt/asset-worldline
```

如果服务器没有 GitHub SSH deploy access，可以改用 HTTPS clone，或复制 release tarball。

## 4. 创建 PostgreSQL 数据库

```bash
sudo -u postgres psql
```

在 `psql` 内执行：

```sql
CREATE USER asset_worldline WITH PASSWORD 'change-this-password';
CREATE DATABASE asset_worldline OWNER asset_worldline;
\q
```

## 5. 配置环境

创建 `/etc/asset-worldline/config.env`：

```bash
sudo install -o root -g asset-worldline -m 0640 /opt/asset-worldline/.env.example /etc/asset-worldline/config.env
sudo nano /etc/asset-worldline/config.env
```

最低必填值：

```text
DATABASE_URL=postgresql+psycopg2://asset_worldline:change-this-password@127.0.0.1:5432/asset_worldline
SECRET_KEY=replace-with-a-long-random-secret
ADMIN_BOOTSTRAP_USER=admin
ADMIN_BOOTSTRAP_PASSWORD=replace-before-first-start
```

可选 provider key：

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

不要提交这个文件。

## 6. 安装后端依赖

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline python3 -m venv .venv
sudo -u asset-worldline .venv/bin/pip install --upgrade pip
sudo -u asset-worldline .venv/bin/pip install -e ".[market,pdf]"
```

如果 market/PDF extras 安装较慢或暂时不可用，可以先使用最小安装：

```bash
sudo -u asset-worldline .venv/bin/pip install -e .
```

## 7. 构建前端

```bash
cd /opt/asset-worldline/frontend
sudo -u asset-worldline npm install
sudo -u asset-worldline npm run build
```

构建产物会写入：

```text
/opt/asset-worldline/frontend/dist
```

生产环境由 FastAPI 提供这些文件。

## 8. 初始化数据库

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli init-db'
```

后续如需轮换或创建管理员密码：

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli create-admin --username admin --password "new-password"'
```

## 9. 安装 systemd 服务

```bash
sudo cp /opt/asset-worldline/deploy/systemd/asset-worldline-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now asset-worldline-web.service
sudo systemctl enable --now asset-worldline-worker.service
sudo systemctl enable --now asset-worldline-scheduler.service
```

查看状态：

```bash
systemctl status asset-worldline-web.service
systemctl status asset-worldline-worker.service
systemctl status asset-worldline-scheduler.service
```

查看日志：

```bash
journalctl -u asset-worldline-web.service -f
journalctl -u asset-worldline-worker.service -f
journalctl -u asset-worldline-scheduler.service -f
```

## 10. 配置 Nginx

```bash
sudo cp /opt/asset-worldline/deploy/nginx/asset-worldline.conf /etc/nginx/sites-available/asset-worldline.conf
sudo ln -sf /etc/nginx/sites-available/asset-worldline.conf /etc/nginx/sites-enabled/asset-worldline.conf
sudo nginx -t
sudo systemctl reload nginx
```

模板监听 `80` 端口，并代理到 `127.0.0.1:8000`。

对公网部署时，在暴露服务前使用 Certbot 或已有证书自动化配置 HTTPS。

## 11. 冒烟测试

本机服务检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1/health
```

期望输出：

```json
{"status":"ok"}
```

然后在浏览器打开服务器 URL，并使用配置好的管理员账号登录。

推荐的第一轮 UI 检查：

1. 打开 `System Status`，入队一个市场快照任务。
2. 打开 `Forecast Matrix`，运行 `model_scored`。
3. 确认 `System Status` 中出现任务。
4. Worker 完成任务后，确认预测行已出现。

## 12. 常用操作

代码或配置变更后重启：

```bash
sudo systemctl restart asset-worldline-web.service
sudo systemctl restart asset-worldline-worker.service
sudo systemctl restart asset-worldline-scheduler.service
```

拉取最新代码：

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

备份数据库：

```bash
sudo -u postgres pg_dump asset_worldline > asset_worldline_$(date +%F).sql
```

备份运行时数据：

```bash
sudo tar -czf asset_worldline_data_$(date +%F).tar.gz /var/lib/asset-worldline
```

## 故障排查

Web 服务启动了但 UI 空白：

- 在 `/opt/asset-worldline/frontend` 下运行 `npm run build`。
- 确认 `/opt/asset-worldline/frontend/dist/index.html` 存在。
- 查看 `journalctl -u asset-worldline-web.service -n 200`。

登录失败：

- 确认 `ADMIN_BOOTSTRAP_USER` 和密码正确。
- 运行 `create-admin` 重置密码。
- 确认 `SECRET_KEY` 在重启之间保持稳定。

市场快照任务失败：

- 用 `journalctl -u asset-worldline-worker.service -n 200` 查看 worker 日志。
- 确认可选依赖已通过 `pip install -e ".[market,pdf]"` 安装。
- 部分免费 provider 可能间歇失败；失败报价行会带 `fetch_status` 存储。

LLM 输出进入 fallback 而不是调用 provider：

- 确认 Model Config 中该角色使用的是支持的 provider。
- 确认对应 API key 存在于 `/etc/asset-worldline/config.env`。
- 修改 provider key 后重启 web 和 worker 服务。
