# China Stock Team

面向 A 股场景的单人投研交易系统。项目基于 OpenClaw cron 调度，围绕“新闻跟踪、预测生成、交易执行、规则验证、复盘学习、监控面板”构建了一条可持续运行的闭环。

## Project Status

| 项目项 | 说明 |
| --- | --- |
| 当前版本 | `v3.2` |
| 调度方式 | `OpenClaw cron` |
| 通知方式 | 脚本自发飞书 webhook |
| 主数据源 | `database/stock_team.db` |
| 监控面板 | `web/dashboard_v3.py`，默认 `8082` |
| 当前分支状态 | `main` 已完成 webhook 收口、面板清理、README 重构 |

## What This Project Does

- 开盘前抓取市场与个股新闻，生成当日预测与持仓汇报
- 盘中根据新闻和风险条件触发预测更新与风险提醒
- 收盘后执行动态选股、到期预测复盘和规则验证
- 晚间从书籍与历史经验中提炼新规则，补充验证池
- 通过统一看板展示 cron 任务、规则状态、观察池、新闻摘要和账户概况

## System Overview

### 业务链路

1. `daily_web_search.py` 获取市场新闻与热点线索
2. `ai_predictor.py` 生成持仓和观察池预测
3. `news_trigger.py` 在盘中根据新事件更新判断
4. `auto_trader_v3.py` / 风控脚本执行交易与预警逻辑
5. `daily_review_closed_loop.py` 复盘到期预测
6. `rule_validator.py` 验证、调权、晋升或淘汰规则
7. `daily_book_learning.py` 将外部知识沉淀到规则系统
8. `dashboard_v3.py` 汇总运行态信息并对外展示

### 核心原则

- `OpenClaw cron` 是唯一调度控制面
- SQLite 是主真源，JSON 保留为兼容镜像
- 飞书通知统一走公共发送器，卡片优先、失败回退文本
- 面板展示真实运行状态，而不是手工维护的静态数据

## Quick Start

### 1. 常用命令

```bash
cd ~/.openclaw/workspace/china-stock-team

# 动态选股
python3 scripts/selector.py top 5

# 生成早盘预测
python3 scripts/ai_predictor.py generate

# 查看规则验证报告
python3 scripts/rule_validator.py report

# 启动监控面板
python3 web/dashboard_v3.py
```

### 2. 面板地址

- `http://127.0.0.1:8082`
- `http://127.0.0.1:8082/cron`

### 3. 测试

```bash
python3 -m unittest \
  tests.test_feishu_notifier \
  tests.test_enhanced_cron_handler \
  tests.test_prediction_utils \
  tests.test_storage_sync \
  tests.test_rule_storage \
  tests.test_dashboard_v3
```

## Deploy With OpenClaw

项目已经提供给 OpenClaw 使用的部署入口：

- [OpenClaw 部署说明](OPENCLAW_DEPLOY.md)
- `bash scripts/bootstrap_openclaw.sh`
- `requirements-openclaw.txt`

如果你希望别人直接把仓库交给 OpenClaw 开箱即用，最短可用提示词是：

```text
请把 jjjojoj/stock-team 部署到本地 ~/.openclaw/workspace/china-stock-team：如果目录不存在就 clone，进入项目后执行 bash scripts/bootstrap_openclaw.sh，不要把任何 webhook 或 API key 写进 git 跟踪文件；如需飞书通知就引导我把 webhook 写到 config/feishu_config.local.json 或 FEISHU_WEBHOOK_URL，最后启动 python3 web/dashboard_v3.py 并验证 http://127.0.0.1:8082 可访问。
```

## Repository Structure

```text
china-stock-team/
├── adapters/        # 数据源适配层
├── agents/          # 团队角色与行为定义
├── config/          # 配置文件与本地模板
├── core/            # 统一存储与预测状态工具
├── data/            # 运行时输出与中间数据
├── database/        # SQLite 数据库
├── docs/            # 架构、重构与设计文档
├── learning/        # 规则、验证池与学习资产
├── research/        # 个股研究资料
├── scripts/         # 核心业务脚本
├── tests/           # 单元测试
└── web/             # 监控面板与 cron 状态接口
```

## Key Components

| 组件 | 作用 |
| --- | --- |
| `scripts/ai_predictor.py` | 预测生成与早盘摘要 |
| `scripts/news_trigger.py` | 盘中新闻触发器 |
| `scripts/selector.py` | 动态标准选股 |
| `scripts/auto_trader_v3.py` | 自动交易逻辑 |
| `scripts/daily_review_closed_loop.py` | 到期预测复盘 |
| `scripts/rule_validator.py` | 规则验证与晋升/淘汰 |
| `scripts/daily_book_learning.py` | 书籍知识学习与规则沉淀 |
| `scripts/feishu_notifier.py` | 飞书发送器 |
| `web/dashboard_v3.py` | 监控面板 |

## Feishu Notification Setup

项目默认不在仓库中保存 webhook。启用飞书通知时，请使用以下任一方式：

1. 在飞书群中创建“自定义机器人”并复制 webhook
2. 设置环境变量 `FEISHU_WEBHOOK_URL`
3. 或复制 `config/feishu_config.local.example.json` 为 `config/feishu_config.local.json`
4. 将 webhook 写入本地私有配置，不要提交到仓库
5. 使用 `python3 scripts/feishu_notifier.py --test` 做连通性验证

环境变量示例：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/your-local-webhook"
```

本地配置示例：

```bash
cp config/feishu_config.local.example.json config/feishu_config.local.json
```

## Documentation Index

### 核心文档

- [运行手册](README_v3.md)
- [OpenClaw 部署说明](OPENCLAW_DEPLOY.md)
- [OpenClaw 操作员巡检清单](docs/OPENCLAW_OPERATOR_CHECKLIST_2026-03-26.md)
- [数据标准](DATA_STANDARD.md)
- [实盘环境说明](REAL_TRADING_ENV.md)
- [团队章程](TEAM_CHARTER.md)
- [版本记录](VERSION.md)

### 架构与设计

- [架构总览](docs/architecture_v3.md)
- [Cron 任务设计](docs/CRON_TASKS.md)
- [规则系统说明](docs/RULE_SYSTEM_EXPLAINED.md)
- [完整闭环说明](docs/COMPLETE_LOOP_v3.md)

### 近期重构记录

- [Phase 9: 通知质量与真实日报修复](docs/REFACTOR_PHASE9_2026-03-26.md)
- [Phase 10: 真实数据清理与闭环复核](docs/REFACTOR_PHASE10_2026-03-26.md)
- [Phase 11: 半自动托管稳定版](docs/REFACTOR_PHASE11_2026-03-26.md)
- [Phase 12: Dashboard 托管驾驶舱升级](docs/REFACTOR_PHASE12_2026-03-26.md)
- [Phase 13: 自动降级与只读保护](docs/REFACTOR_PHASE13_2026-03-26.md)
- [Phase 6: Webhook 收口](docs/REFACTOR_PHASE6_2026-03-25.md)
- [Phase 7: 面板清理与仓库瘦身](docs/REFACTOR_PHASE7_2026-03-25.md)
- [Phase 8: Webhook 去明文](docs/REFACTOR_PHASE8_2026-03-25.md)

## Notes

- 当前仓库中的运行态数据、日志、学习记录可能会持续变化，不应直接作为代码版本状态判断依据
- 如果需要彻底清理历史里曾出现过的敏感 webhook，需要额外执行 git 历史重写
