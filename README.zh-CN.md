<div align="center">

# China Stock Team

**让 AI 替你盯盘、选股、复盘——24小时不休息**

[中文](README.md) | [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3-blue)
![OpenClaw](https://img.shields.io/badge/OpenClaw-cron%20managed-black)
![SQLite](https://img.shields.io/badge/Data-SQLite-0f766e)
![Mode](https://img.shields.io/badge/Trading-Paper-orange)

</div>

---

大多数「AI 炒股项目」只做到链路中的一段——选股脚本、新闻摘要或漂亮的回测图表。

**China Stock Team 不一样**：它是一套能长期 24/7 自动运行的完整闭环系统，从早盘预测到收盘复盘，从规则学习到风险预警，全部自动完成。你只需要在手机上收飞书通知，决定要不要真的买。

```
开盘前  →  新闻扫描 + AI 预测生成
盘中    →  事件跟踪 + 风险监控
收盘后  →  动态选股 + 闭环复盘
夜间    →  规则验证 + 经验沉淀
全天候  →  飞书推送 + Dashboard 监控
```

---

## 核心特性

- **新闻驱动研究** — 跟踪市场、观察池与持仓相关资讯，识别催化剂
- **AI 预测流水线** — 生成方向判断、置信度和风险说明，可复盘可验证
- **规则引擎** — 从历史交易中自动提炼规则，持续迭代，有晋升有淘汰
- **模拟交易执行** — 支持模拟下单、成交、部分成交、手续费、滑点
- **闭环复盘** — 到期预测自动验证、准确率更新、规则调权
- **运维驾驶舱** — 实时展示 cron、风险、规则、观察池、交易状态
- **运行护栏** — 任务锁、只读模式、自愈补跑、数据新鲜度检查

---

## 快速开始

```bash
git clone https://github.com/jjjojoj/stock-team.git
cd stock-team
bash scripts/bootstrap_openclaw.sh
python3 web/dashboard_v3.py
```

打开浏览器：
- 主面板：`http://127.0.0.1:8082`
- Cron 监控：`http://127.0.0.1:8082/cron`

> 需要预先安装 [OpenClaw](https://github.com/openclaw/openclaw) 并配置飞书 webhook。

---

## 系统概览

| 项目 | 说明 |
|---|---|
| 调度方式 | OpenClaw cron（唯一控制面） |
| 数据主真源 | database/stock_team.db（SQLite） |
| 执行模式 | 默认模拟交易，支持切换真实模式 |
| 通知方式 | 飞书 webhook，卡片式推送 |
| 面板入口 | web/dashboard_v3.py，端口 8082 |

---

## 核心模块

| 模块 | 文件 | 说明 |
|---|---|---|
| 存储层 | core/storage.py | 统一账本读写 |
| AI 预测 | scripts/ai_predictor.py | 方向预测生成 |
| 动态选股 | scripts/selector.py | 综合评分选股 |
| 闭环复盘 | scripts/daily_review_closed_loop.py | 收盘复盘 |
| 规则验证 | scripts/rule_validator.py | 规则迭代 |
| 飞书通知 | scripts/feishu_notifier.py | 推送服务 |
| 监控面板 | web/dashboard_v3.py | 实时 Dashboard |

---

## 文档

- [English README](README.en.md)
- [运行手册](README_v3.md)
- [OpenClaw 部署说明](OPENCLAW_DEPLOY.md)
- [数据统一标准](DATA_STANDARD.md)

---

## 免责声明

本项目仅用于技术研究和模拟交易学习，不构成任何投资建议。股市有风险，入市需谨慎。

---

<div align="center">

如果这个项目对你有帮助，欢迎 Star 支持一下！

</div>
