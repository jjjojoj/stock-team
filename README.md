# China Stock Team

单人 A 股投研交易系统，基于 OpenClaw cron 调度，统一使用 SQLite + 兼容 JSON 镜像，面向“研究、预测、交易、复盘、学习、看板监控”的完整闭环。

**当前版本**: v3.2  
**更新时间**: 2026-03-25  
**当前状态**: `main` 已完成 cron webhook 收口、面板清理、规则验证与看板联通

---

## 核心特性

- OpenClaw cron 是唯一控制面
- 股票类 cron 统一由脚本自行通过飞书 webhook 发送消息
- 飞书通知统一走卡片优先、超长自动截断、失败回退文本
- 账户、持仓、预测、规则、观察池统一同步到 `database/stock_team.db`
- 8082 面板直接展示真实 cron、规则库、验证池、新闻与账户摘要

---

## 主要工作流

### 1. 开盘前

- `scripts/daily_web_search.py`：联网搜索市场与个股新闻
- `scripts/ai_predictor.py generate`：为持仓与观察池生成早盘预测
- `scripts/price_report.py`：发送早盘持仓卡片

### 2. 盘中

- `scripts/news_trigger.py check`：识别重要新闻并更新预测
- `scripts/midday_review.py`：午盘验证早盘预测并沉淀教训
- `scripts/afternoon_update.py`：生成下午策略卡片
- `scripts/a_share_risk_monitor.py check` / `scripts/circuit_breaker.py check`：风险预警

### 3. 收盘后

- `scripts/selector.py top 10`：动态标准选股
- `scripts/market_review_v2.py`：收盘复盘与选股标准进化
- `scripts/daily_review_closed_loop.py report`：验证到期预测
- `scripts/rule_validator.py validate`：规则验证、调权、晋升/淘汰

### 4. 晚间学习

- `scripts/daily_book_learning.py`：从经典书籍提炼规则并入验证池

---

## 快速开始

```bash
cd ~/.openclaw/workspace/china-stock-team

# 1. 查看动态选股
python3 scripts/selector.py top 5

# 2. 生成早盘预测并发飞书
python3 scripts/ai_predictor.py generate

# 3. 查看规则验证报告
python3 scripts/rule_validator.py report

# 4. 启动看板（默认 8082）
python3 web/dashboard_v3.py
```

浏览器访问：

- `http://127.0.0.1:8082`
- `http://127.0.0.1:8082/cron`

---

## 关键目录

```text
china-stock-team/
├── adapters/        # 行情与基础数据适配层
├── agents/          # 团队角色定义
├── config/          # 持仓、观察池、飞书、策略配置
├── core/            # 统一存储与预测状态工具
├── data/            # 运行时数据与报告输出
├── database/        # SQLite 主账本
├── docs/            # 重构与架构文档
├── learning/        # 学习、规则、记忆与验证池
├── research/        # 个股研究资料
├── scripts/         # 核心业务脚本
├── tests/           # 单元测试
└── web/             # 8082 监控面板
```

---

## 关键脚本

| 脚本 | 作用 |
|------|------|
| `scripts/ai_predictor.py` | 生成股票预测与早盘简报 |
| `scripts/news_trigger.py` | 新闻驱动预测更新 |
| `scripts/selector.py` | 动态标准选股 |
| `scripts/auto_trader_v3.py` | 自动买卖逻辑 |
| `scripts/daily_review_closed_loop.py` | 到期预测复盘 |
| `scripts/rule_validator.py` | 规则验证与晋升/淘汰 |
| `scripts/daily_book_learning.py` | 书籍学习与新规则生成 |
| `scripts/feishu_notifier.py` | 飞书消息统一发送器 |
| `web/dashboard_v3.py` | 主看板 |

---

## 通知与监控

- 飞书 webhook 优先从环境变量 `FEISHU_WEBHOOK_URL` 读取
- 也支持本地私有配置 `config/feishu_config.local.json`
- 仓库中的 `config/feishu_config.json` 只保留非敏感默认项
- 股票类 cron 不再依赖 OpenClaw `announce`
- 面板会把“切换前遗留的旧投递错误”显示为已清理的历史状态，而不是当前故障

本地配置示例：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/your-local-webhook"
```

或复制模板后本地保存：

```bash
cp config/feishu_config.local.example.json config/feishu_config.local.json
```

---

## 文档入口

- [README_v3.md](/Users/joe/.openclaw/workspace/china-stock-team/README_v3.md)：详细运行手册
- [DATA_STANDARD.md](/Users/joe/.openclaw/workspace/china-stock-team/DATA_STANDARD.md)：数据标准
- [docs/CRON_TASKS.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/CRON_TASKS.md)：cron 设计说明
- [docs/REFACTOR_PHASE6_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE6_2026-03-25.md)：webhook 收口记录
- [docs/REFACTOR_PHASE7_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE7_2026-03-25.md)：面板清理与仓库瘦身记录
- [docs/REFACTOR_PHASE8_2026-03-25.md](/Users/joe/.openclaw/workspace/china-stock-team/docs/REFACTOR_PHASE8_2026-03-25.md)：飞书密钥去明文记录

---

## 测试

```bash
python3 -m unittest \
  tests.test_feishu_notifier \
  tests.test_enhanced_cron_handler \
  tests.test_prediction_utils \
  tests.test_storage_sync \
  tests.test_rule_storage \
  tests.test_dashboard_v3
```
