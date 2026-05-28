# Asset Worldline Agent

私有的跨资产情景预测仪表盘。

这个服务用于接入用户指定的网站，抓取并归并新闻和事件，在人工评分与模型评分两条分支之间保持隔离，并为宏观资产、指数、中国/美国行业代理资产生成 1 周、1 月、3 月三个周期的推演。

## 当前状态

这个仓库包含初始 MVP 脚手架：

- 带 session 登录的 FastAPI 后端。
- 基于 SQLAlchemy 的数据模型，覆盖信息源、新闻、事件簇、资产、分支、任务和预测。
- 已预置分支记录、模型角色记录和第一版资产池。
- 基于数据库的 worker/scheduler。
- 市场数据快照服务，带 AKShare、yfinance、Stooq、CoinGecko fallback 路径。
- LLM provider 适配器，支持 OpenAI-compatible APIs、Anthropic、Gemini；当 key 或 provider 不可用时会生成结构化 fallback 输出。
- 双分支预测服务，确保 `human_scored` 与 `model_scored` 的事件输入互不污染。
- React/Vite 研究仪表盘。
- Ubuntu systemd 部署模板，默认使用 SQLite 文件数据库并通过 `IP:8000` 直接访问。
- `docs/` 下的架构与部署文档。
- 完整产品设计文档位于 `docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md`。

信息源 CRUD 和测试抓取已经实现，但定时文章入库和事件聚类还没有接入。文章持久化、事件聚类、更丰富的模型 prompt、专业市场数据适配器仍是后续实现步骤。当前预测服务可以使用真实 provider key 运行，也可以使用确定性的结构化 fallback，因此分支、任务、快照和预测流程可以较早被验证。

## 文档

- [架构](docs/architecture.md)
- [部署](docs/deployment.md)
- [产品设计](docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md)

## 本地后端

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m app.cli init-db
uvicorn app.main:app --reload
```

本地开发默认使用 `sqlite:///./dev.db`，不需要额外安装数据库。如需配置模型 key，可以在 `backend/.env` 中覆盖对应环境变量。

如需更好的市场数据覆盖：

```bash
pip install -e ".[market,pdf]"
```

开发环境下，如果没有提供 bootstrap 密码且 `ENVIRONMENT` 不是 production，会创建一个用户名为 `admin`、密码为 `admin` 的管理员账户。

## 本地前端

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## Worker

另开一个 shell：

```bash
cd backend
source .venv/bin/activate
python -m app.workers.worker
```

scheduler 可以单独启动：

```bash
python -m app.workers.scheduler
```

也可以从 Web UI 手动创建预测任务和市场快照任务。

## 模型 Provider

Provider API key 从环境变量读取：

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
DEEPSEEK_API_KEY
QWEN_API_KEY
STEPFUN_API_KEY
OPENROUTER_API_KEY
```

如果配置的 provider 被禁用或缺少 key，服务会保存一份可审计的 fallback 响应，而不是让整次运行失败。

## 生产目录

推荐路径：

```text
/opt/asset-worldline
/etc/asset-worldline/config.env
/var/lib/asset-worldline
/var/lib/asset-worldline/asset-worldline.db
/var/log/asset-worldline
```

服务：

```text
asset-worldline-web.service
asset-worldline-worker.service
asset-worldline-scheduler.service
```

## 安全说明

- 不要提交真实 API key。
- Provider key 应放在 `/etc/asset-worldline/config.env`。
- Finnhub 等数据源 API key 也应放在 `/etc/asset-worldline/config.env`，不要写入代码或文档。
- UI 只配置 provider/model 角色映射，不展示 API key。
- 默认部署直接监听 `0.0.0.0:8000`，只应暴露在你信任的网络或服务器安全组规则内。
