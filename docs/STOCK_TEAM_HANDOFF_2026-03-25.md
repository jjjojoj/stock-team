# Stock Team Handoff Summary

日期：2026-03-25

## 适用对象

这份文档用于给后续接手本项目的 OpenClaw / 操作人员快速补齐上下文。

重点不是策略细节，而是“系统现在被改成了什么样子、哪些约定已经变化、哪些地方不能再按旧理解操作”。

## 一、系统级改动总览

从最初版本到当前主线，股票团队已经从“脚本集合 + 多处 JSON + 混合调度”演进为：

- OpenClaw cron 为唯一调度控制面
- SQLite 为主真源，JSON 为兼容镜像
- 飞书通知统一由脚本自行调用 webhook 发送
- Dashboard 基于真实 cron / DB / JSON 兼容层展示
- 项目支持 OpenClaw 一句话部署和本地 bootstrap

## 二、已经完成的关键重构

### 1. 数据层统一

已完成：

- `positions / account / predictions / watchlist / prediction_rules / rule_validation_pool / rejected_rules` 已纳入统一存储层
- `database/stock_team.db` 成为主账本
- JSON 文件不再是主真源，只保留为兼容旧脚本与导出镜像

关键文件：

- `core/storage.py`
- `core/predictions.py`
- `scripts/prediction_system.py`
- `scripts/sync_positions.py`
- `scripts/auto_trader_v3.py`
- `scripts/ai_predictor.py`

### 2. 预测与复盘口径统一

已完成：

- 预测状态与结果 schema 统一
- 复盘逻辑不再混用多套验证窗口
- 无到期预测时，不再往群里发送“0 条验证”的无效复盘消息

关键文件：

- `scripts/daily_review_closed_loop.py`
- `scripts/prediction_system.py`
- `scripts/rule_validator.py`

### 3. 规则系统与验证池统一

已完成：

- `rule_validation.py` 和 `rule_validator.py` 已收口为一套统一验证逻辑
- 规则库、验证池、淘汰池已进入 SQLite 主账本
- Dashboard 已可直接读取规则库和验证池真实数据

关键文件：

- `scripts/rule_validator.py`
- `scripts/rule_validation.py`
- `web/dashboard_v3.py`

### 4. 调度层收口

已完成：

- 当前认定的唯一控制面是 `OpenClaw cron`
- 仓库内旧 scheduler / crontab 风格内容不再代表真实生产调度
- Dashboard 读取 `openclaw cron list --json` 展示真实任务状态

关键文件：

- `web/enhanced_cron_handler.py`
- `scripts/scheduler.py`

### 4.1 运行护栏与半自动托管增强

已完成：

- 新增运行护栏配置与状态层，统一管理任务锁、只读模式、数据新鲜度检查
- 选股、研究、预测、交易、午盘学习已接入 guardrails
- 午盘学习从“单次启发式调参”升级为“最小样本门槛 + 连续错误触发 + 小步调整 + 自动回滚”
- 新增共享基本面访问层，优先尝试实时/缓存数据，失败时再回退到维护快照

关键文件：

- `config/runtime_guardrails.json`
- `core/runtime_guardrails.py`
- `core/fundamentals.py`
- `scripts/midday_review.py`
- `scripts/daily_stock_research.py`
- `scripts/selector.py`
- `scripts/ai_predictor.py`
- `scripts/auto_trader_v3.py`

### 4.2 多 Agent 提案流水线已落地

已完成：

- 新增统一 proposal workflow 层
- Research 会正式提交提案
- Quant 会把验证结果挂回提案
- Trader 买入现在只执行正式审批链中的提案
- Dashboard 交易页已能展示 proposal pipeline 状态与最近交接记录

当前正式状态流：

- `pending`
- `quant_validated`
- `risk_checked`
- `approved`
- `executed`

关键文件：

- `core/proposals.py`
- `scripts/daily_stock_research.py`
- `scripts/ai_predictor.py`
- `scripts/auto_trader_v3.py`
- `scripts/proposal_pipeline.py`
- `scripts/team_coordinator.py`
- `web/dashboard_v3.py`

### 5. 监控面板改为真实数据

已完成：

- Dashboard 接入真实规则、验证池、观察池、新闻摘要、账户摘要
- cron 历史投递错误已做兼容处理，不再把旧 `Message failed` 误判为当前故障
- 当前面板应以 `http://127.0.0.1:8082` 的实时接口为准

关键文件：

- `web/dashboard_v3.py`
- `web/enhanced_cron_handler.py`
- `tests/test_dashboard_v3.py`
- `tests/test_enhanced_cron_handler.py`

### 6. 飞书通知链已统一

已完成：

- 股票任务不再依赖 OpenClaw `announce` 给群发正文
- 统一使用 `scripts/feishu_notifier.py`
- 发送策略：卡片优先、超长截断、失败回退文本
- webhook 已改为“环境变量 / 本地私有配置优先”，仓库不再保存明文地址

关键文件：

- `scripts/feishu_notifier.py`
- `scripts/price_report.py`
- `config/feishu_config.json`
- `config/feishu_config.local.example.json`

### 7. 仓库已完成瘦身

已完成：

- 删除大量被 git 跟踪的 `__pycache__`、`.DS_Store` 和临时报表
- 新增 `.gitignore`
- README 和运行手册重写为当前主线状态

### 8. OpenClaw 开箱部署能力

已完成：

- 新增 `OPENCLAW_DEPLOY.md`
- 新增 `scripts/bootstrap_openclaw.sh`
- 新增 `requirements-openclaw.txt`
- `start.sh` 已改为当前主线可用入口

## 三、当前运行约定

### 1. 模型使用策略

按当前用户确认的最终运行约定：

| 场景 | 模型策略 |
| --- | --- |
| 主对话 / 主会话 | `custom-api123-icu/claude-sonnet-4-6` |
| 全局 fallback | `zai/glm-5` |
| 股票团队 cron | 显式使用 `zai/glm-5`，以降低成本 |

一句话理解：

- 你和 OpenClaw 的主对话走 Claude
- 股票团队的例行 cron 走 GLM-5
- 两者分工不同，成本和体验分开控制

### 2. 调度理解

不要再用系统 `crontab -l` 作为股票团队的真实调度依据。

正确检查方式：

```bash
openclaw cron list --json
```

### 3. 飞书通知理解

不要再把“OpenClaw delivery error”直接等同于“股票脚本执行失败”。

当前股票任务的正文通知主要由脚本自己发 webhook，OpenClaw `delivery.mode` 只是辅助状态，不是业务正文链路。

## 四、当前最重要的文件

### 核心入口

- `README.md`
- `README_v3.md`
- `OPENCLAW_DEPLOY.md`
- `docs/OPENCLAW_OPERATOR_CHECKLIST_2026-03-26.md`

### 核心系统

- `core/storage.py`
- `core/simulated_execution.py`
- `scripts/feishu_notifier.py`
- `scripts/ai_predictor.py`
- `scripts/selector.py`
- `scripts/daily_review_closed_loop.py`
- `scripts/rule_validator.py`
- `web/dashboard_v3.py`
- `web/enhanced_cron_handler.py`

### 本轮重构记录

- `docs/REFACTOR_PHASE1_2026-03-25.md`
- `docs/REFACTOR_PHASE2_2026-03-25.md`
- `docs/REFACTOR_PHASE3_2026-03-25.md`
- `docs/REFACTOR_PHASE4_2026-03-25.md`
- `docs/REFACTOR_PHASE5_2026-03-25.md`
- `docs/REFACTOR_PHASE6_2026-03-25.md`
- `docs/REFACTOR_PHASE7_2026-03-25.md`
- `docs/REFACTOR_PHASE8_2026-03-25.md`
- `docs/REFACTOR_PHASE9_2026-03-26.md`
- `docs/REFACTOR_PHASE10_2026-03-26.md`
- `docs/REFACTOR_PHASE11_2026-03-26.md`
- `docs/REFACTOR_PHASE12_2026-03-26.md`
- `docs/REFACTOR_PHASE13_2026-03-26.md`
- `docs/REFACTOR_PHASE14_2026-03-26.md`
- `docs/REFACTOR_PHASE15_2026-03-31.md`
- `docs/REFACTOR_PHASE16_2026-04-10.md`

## 五、后续 OpenClaw 需要记住的判断

1. 股票团队项目的“真实运行状态”优先看 OpenClaw cron + Dashboard，不优先看旧文档或旧 shell 菜单。
2. 任何涉及数据一致性的改动，优先围绕 `database/stock_team.db` 设计，不要再回到“JSON 直写为主”。
3. 任何飞书 webhook / API key 都不应进入 git 跟踪文件。
4. 用户主对话模型和股票 cron 模型是分开的，不能因为主会话用 Claude 就推断 cron 也在用 Claude。
5. 当前仓库已经具备 OpenClaw 开箱部署能力，优先使用 `bash scripts/bootstrap_openclaw.sh`，不要再沿用旧 `start.sh` 时代的假设。
6. 当前主链已经接近真闭环，但午盘学习和运行安全现在由 `runtime_guardrails` 统一托底；后续任何“自动调参/自动交易”改动都不应绕过这一层。
7. 当前交易执行层已经升级为“模拟订单 -> 成交/部分成交 -> 账本回写 -> 自动补记”，不要再把 `auto_trader_v3.py` 当作“信号直接改仓位”的脚本来理解。
8. 当前值守不仅要看 guardrails 事件，还要看 `self_healing` 和 `simulated_orders`，因为这两者已经决定系统是否真的处于可托管状态。
9. 从 2026-04-10 开始，`ai_predictor` 改成按交易日刷新，同标的旧 active prediction 会先归档再生成今日新预测，不应再把 4 月初那种“老预测连续多日复用”视为正常。
10. 从 2026-04-10 开始，`selector top` 会正式同步 watchlist 和 proposal pipeline；Dashboard 交易页也会直接解释“今天为什么没交易”。
