# Phase 8: 飞书 Webhook 去明文

日期：2026-03-25

## 目标

1. 清掉仓库当前版本里的飞书 webhook 明文
2. 改成环境变量和本地私有配置优先
3. 更新说明文档，避免后续再次把地址写进仓库

## 本轮改动

文件：

- `scripts/feishu_notifier.py`
- `scripts/price_report.py`
- `config/feishu_config.json`
- `config/feishu_config.local.example.json`
- `.gitignore`
- `README.md`
- `README_v3.md`
- `docs/REFACTOR_PHASE6_2026-03-25.md`

处理方式：

- 新增读取优先级：`FEISHU_WEBHOOK_URL` > `config/feishu_config.local.json` > `config/feishu_config.json`
- 仓库内 `config/feishu_config.json` 改为无敏感信息模板
- 新增 `config/feishu_config.local.example.json` 作为本地私有配置样例
- `config/feishu_config.local.json` 加入 `.gitignore`
- `price_report.py` 不再直接读取仓库配置，而是复用统一 notifier

## 本机兼容处理

为了不影响当前机器继续发飞书：

- 本地应保留 `config/feishu_config.local.json`
- 或设置环境变量 `FEISHU_WEBHOOK_URL`

## 备注

本轮只清理了当前版本中的明文地址。

如果要把 Git 历史中的旧明文也彻底抹掉，需要另做一次历史重写并强推。
