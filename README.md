# China Stock Team

[简体中文](README.zh-CN.md) | [English](README.en.md)

An OpenClaw-managed research, prediction, rule-learning, and paper-trading system for the China A-share market.

China Stock Team is designed as a long-running operating system rather than a single stock-picking script. It combines market news tracking, prediction generation, rule validation, simulated execution, closed-loop review, and operator monitoring into one workflow.

## Choose Your Language

- [简体中文文档](README.zh-CN.md)
- [English Documentation](README.en.md)

## Quick Facts

| Item | Value |
| --- | --- |
| Orchestration | `OpenClaw cron` |
| Source of truth | `database/stock_team.db` |
| Execution mode | paper trading by default |
| Notifications | Feishu webhook, script-owned delivery |
| Dashboard | `web/dashboard_v3.py` on `8082` |

## Quick Start

```bash
git clone https://github.com/jjjojoj/stock-team.git
cd stock-team
bash scripts/bootstrap_openclaw.sh
python3 web/dashboard_v3.py
```

Open:

- `http://127.0.0.1:8082`
- `http://127.0.0.1:8082/cron`

## Documentation

- [中文 README](README.zh-CN.md)
- [English README](README.en.md)
- [Operations Manual](README_v3.md)
- [Deploy With OpenClaw](OPENCLAW_DEPLOY.md)
- [OpenClaw Operator Checklist](docs/OPENCLAW_OPERATOR_CHECKLIST_2026-03-26.md)

## Scope

This repository is intended for:

- long-running simulation
- rule-learning validation
- OpenClaw-managed daily operation
- operator-in-the-loop supervision

It is not positioned as:

- one-click retail brokerage automation
- guaranteed-profit strategy software
- fully autonomous real-money trading
