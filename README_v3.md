# China Stock Team Operations Manual

本文件面向项目维护者与日常使用者，描述当前主线的运行方式、数据口径、通知接入和面板能力。

## 1. System Positioning

China Stock Team 不是单一选股脚本，而是一套围绕 A 股场景构建的单人投研交易操作系统。系统覆盖以下核心链路：

1. 新闻收集
2. 预测生成
3. 盘中跟踪
4. 风险控制
5. 交易执行
6. 到期复盘
7. 规则验证
8. 知识学习
9. 面板监控

## 2. Operating Principles

- 唯一控制面：`OpenClaw cron`
- 唯一主数据源：`database/stock_team.db`
- JSON 文件仅用于兼容旧脚本与导出
- 股票任务通知统一由脚本调用飞书 webhook
- 面板与 cron 状态以实际运行数据为准

常用调度命令：

```bash
openclaw cron list --json
openclaw cron run <job_id>
```

OpenClaw 首次部署入口：

- `bash scripts/bootstrap_openclaw.sh`
- 说明文档见 [OPENCLAW_DEPLOY.md](OPENCLAW_DEPLOY.md)

## 3. Daily Workflow

### 开盘前

| 时间 | 任务 | 脚本 |
| --- | --- | --- |
| 09:00 | 开盘前联网搜索 | `scripts/daily_web_search.py` |
| 09:30 | 早盘 AI 预测生成 | `scripts/ai_predictor.py generate` |
| 09:35 | 早盘持仓汇报 | `scripts/price_report.py` |

### 盘中

| 时间 | 任务 | 脚本 |
| --- | --- | --- |
| 10:00 / 12:00 / 14:00 | 新闻监控与预测更新 | `scripts/news_trigger.py check` |
| 11:30 | 午盘反思 | `scripts/midday_review.py` |
| 13:00 | 下午策略更新 | `scripts/afternoon_update.py` |
| 09:25 / 14:25 | 涨跌停监控 | `scripts/a_share_risk_monitor.py check` |
| 09:25 / 14:25 | 熔断减仓检查 | `scripts/circuit_breaker.py check` |

### 收盘后

| 时间 | 任务 | 脚本 |
| --- | --- | --- |
| 15:00 | 动态标准选股 | `scripts/selector.py top 10` |
| 15:05 | 收盘持仓汇报 | `scripts/price_report.py` |
| 15:10 | 自动卖出 | `scripts/auto_trader_v3.py` |
| 15:30 | 收盘复盘与标准进化 | `scripts/market_review_v2.py` |
| 15:30 | 到期预测复盘 | `scripts/daily_review_closed_loop.py report` |
| 16:00 | 每日绩效汇报 | `scripts/daily_performance_report.py` |
| 16:00 | 规则验证 | `scripts/rule_validator.py validate` |

### 晚间

| 时间 | 任务 | 脚本 |
| --- | --- | --- |
| 20:00 | 书籍学习与规则沉淀 | `scripts/daily_book_learning.py` |

## 4. Data Model

### 主账本

- 路径：`database/stock_team.db`
- 核心表：`positions`、`account`、`predictions`、`watchlist`、`prediction_rules`、`rule_validation_pool`、`rejected_rules`

### 兼容镜像

- `config/watchlist.json`
- `data/predictions.json`
- `learning/prediction_rules.json`
- `learning/rule_validation_pool.json`
- `learning/rejected_rules.json`

### 原则

- 数据写入优先落到数据库
- JSON 作为兼容层存在，不再视为系统唯一真源
- 面板读取优先使用数据库和 OpenClaw 状态

## 5. Feishu Notifications

统一入口：

- `scripts/feishu_notifier.py`

发送策略：

- 卡片优先
- 按段拆分
- 超长自动截断
- 卡片失败时回退文本消息

配置优先级：

1. 环境变量 `FEISHU_WEBHOOK_URL`
2. 本地私有配置 `config/feishu_config.local.json`
3. 仓库模板 `config/feishu_config.json`

接入方式：

1. 在飞书群里创建“自定义机器人”
2. 复制机器人生成的 webhook
3. 复制模板：

```bash
cp config/feishu_config.local.example.json config/feishu_config.local.json
```

4. 将 webhook 写入 `config/feishu_config.local.json`
5. 或使用环境变量：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/your-local-webhook"
```

6. 运行测试命令确认通知链路正常：

```bash
python3 scripts/feishu_notifier.py --test
```

## 6. Dashboard

启动方式：

```bash
python3 web/dashboard_v3.py
```

默认地址：

- `http://127.0.0.1:8082`

主要接口：

- `/api/openclaw_cron`
- `/api/rules`
- `/api/validation-pool`
- `/api/watchlist`
- `/api/news-summary`
- `/api/monitoring-summary`

状态说明：

- 已切换为脚本 webhook 的旧 `Message failed` 会显示为历史已清理状态
- 正在运行的任务显示为 `running`
- 当前面板应以实时 OpenClaw 返回值为准

## 7. Recommended Commands

```bash
# 动态选股
python3 scripts/selector.py top 5

# 生成早盘预测
python3 scripts/ai_predictor.py generate

# 查看规则报告
python3 scripts/rule_validator.py report

# 手动复盘到期预测
python3 scripts/daily_review_closed_loop.py report

# 启动面板
python3 web/dashboard_v3.py
```

## 8. OpenClaw Turnkey Delivery

如果你要把项目交给其他 OpenClaw 用户，推荐直接给对方：

1. 仓库地址
2. [OPENCLAW_DEPLOY.md](OPENCLAW_DEPLOY.md) 里的“一句话 Prompt”
3. 本地敏感信息配置原则：只写本地私有文件，不写 git 跟踪文件

标准初始化命令：

```bash
bash scripts/bootstrap_openclaw.sh
```

## 9. Reference Documents

### 基础文档

- [README](README.md)
- [OpenClaw 操作员巡检清单](docs/OPENCLAW_OPERATOR_CHECKLIST_2026-03-26.md)
- [数据标准](DATA_STANDARD.md)
- [实盘环境说明](REAL_TRADING_ENV.md)
- [团队章程](TEAM_CHARTER.md)
- [版本记录](VERSION.md)

### 架构与规则

- [架构总览](docs/architecture_v3.md)
- [Cron 任务设计](docs/CRON_TASKS.md)
- [规则系统说明](docs/RULE_SYSTEM_EXPLAINED.md)
- [完整闭环说明](docs/COMPLETE_LOOP_v3.md)
