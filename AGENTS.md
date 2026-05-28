# Asset Worldline Agent 项目说明

这是一个私有投资研究工作流工具，不是自动交易系统。

## 安全边界

- 不要提交真实 API key、市场数据凭证、cookie 或付费内容导出。
- 将 `/etc/asset-worldline/config.env`、本地 `.env` 文件、日志、PDF 下载和抽取后的文章视为私有数据。
- 除非用户明确要求，不要添加交易执行能力。

## 架构

- 后端：`backend/app`，FastAPI + SQLAlchemy。
- 前端：`frontend/src`，React + Vite。
- 部署模板：`deploy/`。
- 架构文档：`docs/architecture.md`。
- 部署手册：`docs/deployment.md`。
- 产品设计：`docs/superpowers/specs/2026-05-27-asset-worldline-agent-design.md`。

## 分支隔离

产品要求 `human_scored` 与 `model_scored` 两条分支严格隔离。不要让模型评分分支的 prompt、评分、预测或评估读取人工评分，也不要让人工分支预测包含未被人工评分的事件。

## 部署偏好

目标部署方式是 Ubuntu + systemd + SQLite。默认不依赖 PostgreSQL 或 Nginx，FastAPI 直接监听 `0.0.0.0:8000`，通过 `http://服务器IP:8000` 访问。
