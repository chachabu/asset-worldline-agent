# 部署

这份指南用于把 Asset Worldline Agent 部署到单台 Ubuntu 服务器。默认部署不需要 PostgreSQL 或 Nginx：应用使用 SQLite 文件数据库，通过 systemd 管理，并直接用 `http://服务器IP:8000` 访问。

## 目标目录

```text
/opt/asset-worldline                                # 应用代码目录
/etc/asset-worldline/config.env                     # 密钥和运行时配置
/var/lib/asset-worldline                            # 私有运行时数据
/var/lib/asset-worldline/asset-worldline.db         # SQLite 数据库文件
/var/log/asset-worldline                            # 可选日志目录
```

systemd 服务：

```text
asset-worldline-web.service
asset-worldline-worker.service
asset-worldline-scheduler.service
```

默认访问地址：

```text
http://服务器IP:8000
```

## 1. 安装系统包

```bash
sudo apt update
sudo apt install -y \
  git curl build-essential sqlite3 \
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

## 4. 配置环境

创建 `/etc/asset-worldline/config.env`：

```bash
sudo install -o root -g asset-worldline -m 0640 /opt/asset-worldline/.env.example /etc/asset-worldline/config.env
sudo nano /etc/asset-worldline/config.env
```

最低必填值：

```text
DATABASE_URL=sqlite:////var/lib/asset-worldline/asset-worldline.db
SECRET_KEY=replace-with-a-long-random-secret
SESSION_COOKIE_SECURE=false
ADMIN_BOOTSTRAP_USER=admin
ADMIN_BOOTSTRAP_PASSWORD=replace-before-first-start
```

`SESSION_COOKIE_SECURE=false` 适用于当前这种 `http://服务器IP:8000` 直连部署。如果后续通过 HTTPS 访问，应改为 `true` 并重启 Web 服务。

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

## 5. 安装后端依赖

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

## 6. 构建前端

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

## 7. 初始化数据库

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli init-db'
```

初始化后应能看到 SQLite 数据库文件：

```bash
ls -lh /var/lib/asset-worldline/asset-worldline.db
```

后续如需轮换或创建管理员密码：

```bash
cd /opt/asset-worldline/backend
sudo -u asset-worldline bash -lc 'set -a; source /etc/asset-worldline/config.env; set +a; .venv/bin/python -m app.cli create-admin --username admin --password "new-password"'
```

## 8. 安装 systemd 服务

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

`asset-worldline-web.service` 默认监听 `0.0.0.0:8000`。如果服务器启用了防火墙，需要放行端口：

```bash
sudo ufw allow 8000/tcp
```

## 9. 冒烟测试

本机服务检查：

```bash
curl http://127.0.0.1:8000/health
```

从外部访问：

```bash
curl http://服务器IP:8000/health
```

期望输出：

```json
{"status":"ok"}
```

然后在浏览器打开 `http://服务器IP:8000`，并使用配置好的管理员账号登录。

推荐的第一轮 UI 检查：

1. 打开 `System Status`，入队一个市场快照任务。
2. 打开 `Forecast Matrix`，运行 `model_scored`。
3. 确认 `System Status` 中出现任务。
4. Worker 完成任务后，确认预测行已出现。

## 10. 常用操作

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

备份 SQLite 数据库：

```bash
sudo -u asset-worldline sqlite3 /var/lib/asset-worldline/asset-worldline.db ".backup '/var/lib/asset-worldline/asset-worldline_$(date +%F).db'"
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

浏览器无法访问 `http://服务器IP:8000`：

- 确认 `systemctl status asset-worldline-web.service` 是 running。
- 确认服务监听端口：`ss -ltnp | grep 8000`。
- 检查云安全组或本机防火墙是否放行 `8000/tcp`。

登录失败：

- 确认 `ADMIN_BOOTSTRAP_USER` 和密码正确。
- 运行 `create-admin` 重置密码。
- 确认 `SECRET_KEY` 在重启之间保持稳定。
- 如果登录返回成功但后续页面数据为空或接口持续 `401`，且当前使用 `http://服务器IP:8000` 访问，确认 `SESSION_COOKIE_SECURE=false`。

数据库文件不存在：

- 重新运行 `init-db`。
- 确认 `/var/lib/asset-worldline` 属主是 `asset-worldline`。
- 确认 `/etc/asset-worldline/config.env` 中的 `DATABASE_URL` 是 `sqlite:////var/lib/asset-worldline/asset-worldline.db`。

市场快照任务失败：

- 用 `journalctl -u asset-worldline-worker.service -n 200` 查看 worker 日志。
- 确认可选依赖已通过 `pip install -e ".[market,pdf]"` 安装。
- 部分免费 provider 可能间歇失败；失败报价行会带 `fetch_status` 存储。

LLM 输出进入 fallback 而不是调用 provider：

- 确认 Model Config 中该角色使用的是支持的 provider。
- 确认对应 API key 存在于 `/etc/asset-worldline/config.env`。
- 修改 provider key 后重启 web 和 worker 服务。

SQLite 出现 `database is locked`：

- 当前代码已对 SQLite 启用 WAL 和 `busy_timeout=5000`，正常单人使用不应频繁出现。
- 如果同一时间跑大量抓取、预测和评估任务，先降低任务频率或暂停 scheduler。
- 如果后续需要多人高并发或大量后台任务，再考虑切换到 PostgreSQL。
