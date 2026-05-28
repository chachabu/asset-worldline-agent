# SQLite 直连 systemd 部署设计

日期：2026-05-28

## 背景

当前产品是单人私用的研究仪表盘。默认部署如果要求 PostgreSQL 和 Nginx，会增加安装、备份、故障排查和运维成本。第一阶段更适合用一个本地 SQLite 文件保存状态，并让 FastAPI 通过 systemd 直接监听端口。

## 决策

默认生产部署改为：

- SQLite 文件数据库：`/var/lib/asset-worldline/asset-worldline.db`。
- FastAPI 直接监听：`0.0.0.0:8000`。
- 访问方式：`http://服务器IP:8000`。
- systemd 服务：`asset-worldline-web.service`、`asset-worldline-worker.service`、`asset-worldline-scheduler.service`。
- 默认不安装 PostgreSQL。
- 默认不配置 Nginx。

保留 `DATABASE_URL` 配置入口。后续如果出现多人高并发、大量后台任务或更强数据治理需求，可以再切换到 PostgreSQL。

## 实现要求

- `.env.example` 默认给出 SQLite 生产路径。
- SQLAlchemy engine 在 SQLite 下启用：
  - `PRAGMA foreign_keys=ON`
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA busy_timeout=5000`
- `psycopg2-binary` 不再是默认依赖，改为可选 `postgres` extra。
- systemd web 服务监听 `0.0.0.0:8000`。
- systemd 服务不依赖 `postgresql.service`。
- 部署文档以 SQLite + systemd + IP:端口访问为默认路径。
- Nginx 仅作为未来 HTTPS 或反向代理需求的升级选择，不作为当前默认部署步骤。

## 取舍

SQLite 的优势是部署轻、备份简单、足够支撑单人研究场景。它的限制是写并发能力弱于 PostgreSQL，因此不适合作为多人高并发或大量任务同时写入的长期方案。当前通过 WAL 和 `busy_timeout` 降低单机多进程下的锁冲突风险。

## 验收标准

- 不安装 PostgreSQL 时，`python -m app.cli init-db` 可以创建并初始化 SQLite 数据库。
- systemd web 服务可以直接通过 `http://服务器IP:8000` 访问。
- README、部署文档、架构文档和产品设计不再把 PostgreSQL/Nginx 描述为默认依赖。
