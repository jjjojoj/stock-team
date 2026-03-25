# AI 股票团队运行手册 v3.2

**更新时间**: 2026-03-25  
**状态**: 当前主线说明文档

---

## 系统定位

这是一个用 OpenClaw 驱动的单人股票团队操作系统，不是单一的选股脚本集合。

当前主链路：

1. 搜新闻
2. 生成预测
3. 盘中跟踪
4. 自动交易
5. 到期复盘
6. 规则验证
7. 书籍学习
8. 面板监控

---

## 调度原则

- 唯一控制面：`OpenClaw cron`
- 股票类任务统一 `delivery.mode = none`
- 飞书消息统一由脚本自己调用 webhook 发送
- 不再依赖 OpenClaw `announce` 给飞书群发总结

查看 cron：

```bash
openclaw cron list --json
```

立即执行某个任务：

```bash
openclaw cron run <job_id>
```

---

## 当前核心任务

### 开盘前

| 时间 | 任务 | 脚本 |
|------|------|------|
| 09:00 | 开盘前联网搜索 | `scripts/daily_web_search.py` |
| 09:30 | 早上 AI 预测生成 | `scripts/ai_predictor.py generate` |
| 09:35 | 持仓汇报-早盘开盘 | `scripts/price_report.py` |

### 盘中

| 时间 | 任务 | 脚本 |
|------|------|------|
| 10:00/12:00/14:00 | 新闻监控-预测更新 | `scripts/news_trigger.py check` |
| 11:30 | 午盘反思 | `scripts/midday_review.py` |
| 13:00 | 下午开盘前更新 | `scripts/afternoon_update.py` |
| 09:25/14:25 | 涨跌停实时监控 | `scripts/a_share_risk_monitor.py check` |
| 09:25/14:25 | 熔断紧急减仓 | `scripts/circuit_breaker.py check` |

### 收盘后

| 时间 | 任务 | 脚本 |
|------|------|------|
| 15:00 | 动态标准选股 | `scripts/selector.py top 10` |
| 15:05 | 持仓汇报-收盘汇总 | `scripts/price_report.py` |
| 15:10 | 自动卖出 | `scripts/auto_trader_v3.py 卖出` |
| 15:30 | 收盘复盘 + 选股标准进化 | `scripts/market_review_v2.py` |
| 15:30 | 每日预测复盘 | `scripts/daily_review_closed_loop.py report` |
| 16:00 | 每日绩效汇报 | `scripts/daily_performance_report.py` |
| 16:00 | 规则验证（每日） | `scripts/rule_validator.py validate` |

### 晚间

| 时间 | 任务 | 脚本 |
|------|------|------|
| 20:00 | 每日炒股书籍学习 | `scripts/daily_book_learning.py` |

---

## 数据存储

### 主账本

- 路径：`database/stock_team.db`
- 主要表：`positions` `account` `predictions` `watchlist` `prediction_rules` `rule_validation_pool` `rejected_rules`

### JSON 兼容镜像

- `config/watchlist.json`
- `data/predictions.json`
- `learning/prediction_rules.json`
- `learning/rule_validation_pool.json`
- `learning/rejected_rules.json`

原则：

- DB 是主真源
- JSON 主要用于兼容旧脚本与导出

---

## 飞书通知

统一入口：

- `scripts/feishu_notifier.py`

发送策略：

- 卡片优先
- 按段拆分
- 超长自动截断
- 卡片失败回退文本

配置文件：

- `config/feishu_config.json`

---

## 看板

启动：

```bash
python3 web/dashboard_v3.py
```

默认地址：

- `http://127.0.0.1:8082`

关键 API：

- `/api/openclaw_cron`
- `/api/rules`
- `/api/validation-pool`
- `/api/watchlist`
- `/api/news-summary`
- `/api/monitoring-summary`

监控说明：

- 已切换到脚本 webhook 后，旧 `Message failed` 不再当成当前故障
- 看板会把这类历史状态展示成已清理状态

---

## 建议的日常命令

```bash
# 选股
python3 scripts/selector.py top 5

# 生成预测
python3 scripts/ai_predictor.py generate

# 查看规则报告
python3 scripts/rule_validator.py report

# 手动复盘到期预测
python3 scripts/daily_review_closed_loop.py report

# 手动发一条飞书测试卡片
python3 scripts/feishu_notifier.py --test
```

---

## 本周重构记录

- [docs/REFACTOR_PHASE1_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE1_2026-03-25.md)
- [docs/REFACTOR_PHASE2_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE2_2026-03-25.md)
- [docs/REFACTOR_PHASE3_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE3_2026-03-25.md)
- [docs/REFACTOR_PHASE4_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE4_2026-03-25.md)
- [docs/REFACTOR_PHASE5_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE5_2026-03-25.md)
- [docs/REFACTOR_PHASE6_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE6_2026-03-25.md)
- [docs/REFACTOR_PHASE7_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE7_2026-03-25.md)
