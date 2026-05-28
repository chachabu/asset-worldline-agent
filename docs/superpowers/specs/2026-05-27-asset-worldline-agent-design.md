# Asset Worldline Agent 设计

日期：2026-05-27

## 摘要

Asset Worldline Agent 是一个私有研究类 Web 服务，用于跨资产情景预测。它从用户指定的网站接入新闻、研报、公告、政策更新和行业数据，然后运行两条互相隔离的评分分支：

- 人工评分分支：只有用户评分后的事件簇可以影响预测。
- 模型评分分支：所有事件簇由 LLM 自动评分，并且永远不能读取人工评分。

两条分支都会为一个受控资产池生成 1 周、1 月、3 月预测，覆盖全球宏观资产、市场指数和中国/美国行业代理资产。预测结果包括方向、当前价格、目标价、支撑/阻力、失效位、多/基准/空三种情景、证据链、模型分歧和分支对比。

服务以单台 Ubuntu 应用部署，由 systemd 管理，使用 PostgreSQL 存储，并通过应用层管理员登录保护。

## 目标

- 允许用户配置具体网站作为信息源。
- 将文章、PDF、RSS item 归一化为去重后的事件簇。
- 保持人工评分分支和模型评分分支严格隔离。
- 使用三个专家 LLM 角色加一个 judge 模型生成结构化预测。
- 为固定初始资产池中的约 25-35 个展示对象预测 1W、1M、3M 价格路径。
- 将行业/主题观点绑定到可交易或可定价的代理资产，方便后续复盘。
- 提供密集型研究仪表盘，而不是 chat-first 界面。
- 支持 Ubuntu + systemd 服务、PostgreSQL、日志和基于环境配置的密钥管理。

## 非目标

- 不做自动交易或下单执行。
- 不接入高频或 tick 级市场数据。
- 不绕过付费墙、验证码、登录限制，也不做激进反爬规避。
- 第一版不做完整的多用户团队工作流。
- 不把完整版权研报内容作为产品功能重新分发。
- 不保证模型生成的目标价构成投资建议。

## 部署形态

第一版作为单机 Web 服务运行：

```text
Ubuntu Server
├── Nginx
├── asset-worldline-web.service
├── asset-worldline-worker.service
├── asset-worldline-scheduler.service
├── PostgreSQL
├── /etc/asset-worldline/config.env
├── /var/lib/asset-worldline
└── /var/log/asset-worldline
```

推荐技术栈：

- 后端：FastAPI、SQLAlchemy、Alembic、PostgreSQL。
- Worker/scheduler：MVP 使用基于数据库的 job queue；后续可加入 Redis/RQ 或 Celery。
- 前端：React + Vite。
- 内容抽取：httpx、trafilatura/readability 风格抽取、PyMuPDF 或 pypdf、可选 Playwright fallback。
- 市场数据：yfinance、Stooq、AKShare、CoinGecko/Binance、FRED，以及有限的 Alpha Vantage 校验。

## 认证

第一版使用应用层管理员登录：

- 用户名/密码登录。
- 密码以 argon2 或 bcrypt hash 存储。
- 带可配置生命周期的 session cookie。
- MVP 阶段只有一个管理员用户。
- 不做注册、密码重置、OAuth 或角色权限。

除登录和 health check 外，所有页面和 API 路由都要求认证。敏感操作必须有已认证的管理员 session：

- 编辑信息源。
- 配置模型角色。
- 触发预测。
- 编辑资产池。
- 删除或禁用记录。

Provider API key 从服务器环境变量或配置文件读取，UI 中永不明文展示。

## 信息源

用户从 UI 添加具体网站。每个 source 包含：

- 名称。
- 来源类型：财经新闻、机构/研究、公司公告/IR、政策/监管/央行、行业协会/数据、宏观日历或其他。
- 入口 URL。
- 抓取模式：RSS、列表页、文章 URL 或 PDF URL。
- 语言和地区。
- 默认标签。
- 来源权重。
- 抓取频率。
- 启用/禁用状态。
- 可选的浏览器渲染开关。
- 可选 CSS selector 和 URL include/exclude 规则。

信息源页面必须提供 "test fetch" 操作，在信任该来源前展示候选文章、时间戳、链接、文本片段和抽取错误。

MVP 支持：

- RSS feed。
- 公开列表页。
- 公开文章页。
- 手动单链接入库。
- 基础 PDF 文本抽取。

MVP 不支持：

- 仅登录可见内容。
- 付费墙内容。
- 验证码。
- 强 Cloudflare 或类似反爬流程。
- 微信公众号抓取。
- 仅 App 内可见内容。

## 新闻归一化

抓取内容会归一化为 `raw_news` 记录：

- 标题。
- 来源。
- 来源类型。
- URL 和 canonical URL。
- 发布时间。
- 抓取时间。
- 语言和地区。
- 原始文本和抽取文本。
- 摘要。
- 内容 hash。
- 抽取状态。

原始新闻会被去重并聚类：

1. 归一化 URL。
2. 按 URL 和内容 hash 去重。
3. 聚类相似标题和摘要。
4. 生成 `event_cluster`。

事件簇存储：

- 标准标题。
- 最早和最晚发布时间。
- 来源数量。
- 来源类型。
- 代表文章。
- 中性摘要。
- 相关资产/主题候选。
- 成员文章。

中性抽取结果可以被两条分支共享，例如摘要、事实、实体、公司、ticker、行业和可能受影响地区。重要性评分、排序、预测输入、模型输出和预测结果必须保持分支专属。

## 资产池

第一版使用约 25-35 个展示对象。

展示对象分为：

- 宏观资产。
- 市场指数。
- 行业/主题组。

宏观资产：

- 美元指数。
- 美国 10 年期国债收益率。
- 黄金。
- 原油。
- 铜。
- BTC。
- ETH。
- USD/CNH 或人民币汇率。
- VIX 或等价风险代理。

参考指数：

- S&P 500。
- Nasdaq 100。
- CSI 300。
- 创业板或科创/科技代理。
- Hang Seng Tech。

初始行业/主题组：

- 半导体。
- AI 算力/数据中心。
- 电力/公用事业。
- 电网设备。
- 核电。
- 油气。
- 黄金/贵金属。
- 银行。
- 国防军工。
- 创新药/医疗。
- 有色金属/铜。
- 机器人/自动化。

每个行业/主题都有地区级代理资产绑定：

```text
theme: 半导体
美国 primary proxy: SMH
美国 supporting proxies: SOXX, NVDA, AMD, MU, TSM
中国/香港 primary proxy: 配置的半导体 ETF
中国/香港 supporting proxies: 配置的芯片 ETF 和重点上市公司
```

主题预测以组为单位展示，但价格目标属于 primary proxy。Supporting proxy 用来识别分化并提高复盘质量。

## 市场数据

第一版使用免费数据源并带 fallback：

- 美股/ETF 和部分全球资产：yfinance 为主，Stooq fallback。
- 中国/香港资产和 ETF：AKShare 为主，Stooq 或后续 Eastmoney/Sina adapter fallback。
- 宏观：FRED。
- 加密资产：CoinGecko 为主，Binance market endpoints fallback。
- Alpha Vantage：受免费层限制，只做有限 key-symbol 校验。

市场数据记录必须包含：

- 资产。
- 价格。
- 币种。
- 时间戳。
- 来源。
- 数值是当前、延迟、日频还是陈旧。
- adjusted/raw 标记。
- 抓取状态。
- 历史特征。

预测运行会保存不可变的预测基准快照，这样后续复盘使用的起始价格和历史上下文就与模型当时看到的一致。

刷新模型：

- 全量资产池：主要市场收盘后每日刷新。
- Watchlist：相关市场交易时段内每 30-60 分钟刷新。
- 预测基准快照：每次预测运行前捕获。

## 分支隔离

系统有两条固定分支：

```text
human_scored
model_scored
```

共享输入：

- 原始新闻。
- 事件簇。
- 中性摘要/实体。
- 资产池。
- 市场快照。
- 信息源元数据。

隔离数据：

- 事件评分。
- 被选中的预测上下文。
- Prompt 输入排序。
- Agent 讨论。
- 预测输出。
- 目标价。
- 评估。

所有分支专属记录都携带 `branch_id`。

人工分支规则：

- 只有人工评分大于 0 的事件簇可以进入预测。
- 分数 0 表示忽略。
- 未评分事件簇永不进入人工分支预测。
- 用户评分包括重要性、影响方向、影响周期、相关资产/主题和可选备注。

模型分支规则：

- 所有事件簇都自动评分。
- 模型评分器不能读取人工评分。
- 模型分支按模型重要性、新颖性、时间衰减和来源元数据选择事件。

## LLM 角色

模型池按角色配置：

- 自动评分模型。
- 中性抽取/摘要模型。
- 宏观资产模型。
- 行业/板块模型。
- 市场交易模型。
- Judge 聚合模型。

Provider key 从环境变量或配置文件加载。UI 配置 provider/model 映射、temperature、timeout、token limit 和 enabled 状态。

专家角色：

- 宏观资产模型：利率、美元、通胀、央行、大宗商品、风险偏好、跨资产传导。
- 行业/板块模型：政策、供应链、订单、库存、利润率、行业/公司映射。
- 市场交易模型：价格位、波动率、资金流、仓位、短期催化、风险收益比。
- Judge 模型：只聚合三个专家输出和给定输入数据；不能引入新证据。

## 预测流程

每次预测运行都会创建分支专属上下文：

- 分支。
- 预测运行。
- 事件快照。
- 市场快照。
- 选中的事件簇。
- 资产池。
- 历史价格特征。

讨论是结构化流程，不是自由聊天：

1. 独立轮：每个专家生成预测和理由。
2. 评审轮：每个专家评审另外两个输出，标记一致、分歧、遗漏和过度推断。
3. 修订轮：每个专家更新预测。
4. Judge 轮：judge 输出最终结构化预测。

每条最终预测由以下字段定位：

- 分支。
- 预测运行。
- 资产组。
- 地区。
- 周期：1W、1M 或 3M。

预测输出包含：

- 方向：bullish、bearish、neutral、volatile 或 divergent。
- 当前价格。
- 基准目标。
- 多头目标。
- 空头目标。
- 支撑位。
- 阻力位。
- 失效位或失效规则。
- 置信度。
- 关联事件簇。
- 多/基准/空情景摘要。
- 催化因素。
- 失效信号。
- 模型分歧摘要。

目标价必须结合历史波动率和近期高低点区间检查。大幅波动预测是允许的，但模型必须解释事件冲击和置信度。

## UI

UI 是研究仪表盘。

导航：

- Overview。
- Information Sources。
- News Pool。
- Human Scoring。
- Model Scoring。
- Forecast Matrix。
- Asset Detail。
- Branch Comparison。
- Review/Evaluation。
- Model Config。
- System Status。

核心页面：

- Overview：系统健康、近期任务、最新分支运行、未评分事件数量、失败来源、模型失败和市场热力图。
- Information Sources：添加、编辑、测试来源，并查看抓取日志。
- News Pool：带成员文章和中性摘要的事件簇。
- Human Scoring：快速 0-5 评分和高级影响字段。
- Model Scoring：模型评分、置信度、受影响资产、理由和重新运行控制。
- Forecast Matrix：资产行，以及 US/CN/global 的 1W/1M/3M 列，并带分支切换。
- Asset Detail：价格快照、目标价、关键位、情景、证据、agent 轮次和代理资产分化。
- Branch Comparison：按资产和事件解释人工分支与模型分支差异。
- Review/Evaluation：方向命中率、目标价误差、分支对比和人工事件标注。
- Model Config：角色到模型的映射和连接测试。
- System Status：任务队列、失败任务、来源健康度、模型日志、市场源状态、服务/日志路径。

UI 应该是密集、克制、工作导向的。它不应该是 landing page，也不应该是 chat-first 界面。

## 数据库模型

核心表：

- `users`。
- `information_sources`。
- `raw_news`。
- `event_clusters`。
- `event_cluster_members`。
- `asset_groups`。
- `assets`。
- `market_snapshots`。
- `market_prices`。
- `branches`。
- `event_scores`。
- `prediction_runs`。
- `agent_outputs`。
- `asset_forecasts`。
- `forecast_scenarios`。
- `forecast_evaluations`。
- `model_configs`。
- `jobs`。

重要关联字段：

- `branch_id`。
- `prediction_run_id`。
- `market_snapshot_id`。
- 运行中包含的 event cluster ID。

## 后台任务

Scheduler 创建任务；worker 执行任务。任务类型：

- `fetch_source`。
- `extract_article`。
- `cluster_events`。
- `auto_score_events`。
- `refresh_market_snapshot`。
- `run_prediction`。
- `evaluate_forecasts`。

任务存储：

- 类型。
- 状态。
- 优先级。
- Payload。
- 计划时间。
- 开始/结束时间。
- 错误消息。
- 重试次数。

MVP 可以使用基于数据库的队列。当任务量需要时，再加入 Redis/RQ/Celery。

## 复盘与评估

MVP 评估：

- 拉取预测周期对应的代理资产实际价格。
- 将方向与实际涨跌比较。
- 将目标价与实际价格比较。
- 展示分支级和资产级目标价误差。
- 允许用户手动标注定性事件结果或失效触发。

后续评估：

- 按分支、资产、周期、来源类型和模型角色统计方向命中率。
- 目标价误差分布。
- 过度自信检测。
- 按新闻类别对比人工评分与模型评分质量。

## 系统配置

示例 `/etc/asset-worldline/config.env`：

```text
DATABASE_URL=
SECRET_KEY=
ADMIN_BOOTSTRAP_USER=
ADMIN_BOOTSTRAP_PASSWORD_HASH=

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

## MVP 里程碑

### MVP 1：预测闭环

- 管理员登录。
- 信息源 CRUD 和测试抓取。
- RSS/list/article/PDF 抽取。
- 新闻池和事件簇。
- 人工评分。
- 模型评分。
- 资产池和代理资产配置。
- 免费来源市场快照。
- 模型角色配置。
- 人工分支和模型分支预测运行。
- 预测矩阵。
- 资产详情。
- 分支对比。
- 基础评估。
- systemd 部署文件。

### MVP 2：质量和复盘

- 更强的评估仪表盘。
- 目标价误差和命中率分析。
- 预测失效跟踪。
- 更好的来源诊断。
- 模型评分质量报告。
- 按资产和周期统计分支表现。

### MVP 3：研究台功能

- 站点专属 adapter。
- 更好的 PDF/研报解析。
- 价格触发提醒。
- 飞书/email 通知。
- 更多市场数据 provider。
- 预测报告导出。
- 多用户权限。

## 复用建议

创建一个新项目，而不是直接修改 `TradingAgents` 或现有内容工具。

本地项目中可参考的内容：

- `ai_hotspot_content_studio`：fetcher 模式、HTTP/browser helper、AI client 思路、本地 Web 工作流。
- `crypto_hotspot_writer`：多来源接入和排序思路。
- `social_media_ai_monitor`：监控服务和通知模式。
- `TradingAgents`：多 agent 角色与 debate 结构，但不要作为直接代码基础。

新项目应该拥有自己的数据库 schema、分支隔离模型、预测工作流、UI 和 systemd 部署。

## 开放实现选择

这些选择允许在实现中调整，不需要修改产品设计：

- 前端静态资源由 FastAPI 提供，还是直接由 Nginx 提供。
- 第一版 worker 使用数据库轮询，还是轻量 queue library。
- 具体 UI 组件库。
- 第一版行业代理资产的精确 symbol，只要存在 theme-to-primary-proxy 映射。
- 各资产类型的精确市场数据 provider 顺序，只要保存来源元数据。
