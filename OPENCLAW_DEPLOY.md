# Deploy With OpenClaw

下面这份内容是给 OpenClaw 直接使用的开箱即用部署指令。

## 一句话 Prompt

请把 `jjjojoj/stock-team` 部署到本地 `~/.openclaw/workspace/china-stock-team`：如果目录不存在就 clone，进入项目后执行 `bash scripts/bootstrap_openclaw.sh`，不要把任何 webhook 或 API key 写进 git 跟踪文件；如需飞书通知就引导我把 webhook 写到 `config/feishu_config.local.json` 或环境变量 `FEISHU_WEBHOOK_URL`，最后启动 `python3 web/dashboard_v3.py` 并验证 `http://127.0.0.1:8082` 可访问。

## 标准 Prompt

如果你希望 OpenClaw 更稳地完成整个初始化，可以直接给它下面这段：

```text
请帮我部署 China Stock Team 到本地 OpenClaw 工作区。

要求：
1. 如果 `~/.openclaw/workspace/china-stock-team` 不存在，就从 GitHub 拉取仓库。
2. 进入项目目录后执行 `bash scripts/bootstrap_openclaw.sh`。
3. 不要把任何 webhook、API key 或本地账户信息写入 git 跟踪文件。
4. 如果我要启用飞书通知，请指导我把 webhook 写入 `config/feishu_config.local.json` 或环境变量 `FEISHU_WEBHOOK_URL`。
5. 初始化完成后启动 `python3 web/dashboard_v3.py`。
6. 用浏览器或 curl 验证 `http://127.0.0.1:8082` 可访问。
7. 最后告诉我下一步如何配置 OpenClaw cron 与联网搜索。
```

## Bootstrap Script

项目已内置：

- `requirements-openclaw.txt`
- `scripts/bootstrap_openclaw.sh`

脚本会完成这些事情：

1. 创建或复用 `venv`
2. 安装核心依赖
3. 准备运行目录
4. 初始化 SQLite 表结构
5. 运行基础 smoke tests
6. 按需生成本地飞书配置模板

可选参数：

```bash
bash scripts/bootstrap_openclaw.sh --skip-install
bash scripts/bootstrap_openclaw.sh --skip-tests
bash scripts/bootstrap_openclaw.sh --start-dashboard
```

## 本地敏感配置

### 飞书 webhook

- 环境变量：`FEISHU_WEBHOOK_URL`
- 或本地私有文件：`config/feishu_config.local.json`

### 注意

- 不要把本地私有配置提交回仓库
- 仓库中的 `config/feishu_config.json` 仅保留共享默认项

## 推荐交付方式

如果你准备把这个项目交给别人配合 OpenClaw 使用，建议直接发送两样东西：

1. 仓库链接
2. 上面的“一句话 Prompt”

这样对方基本可以直接把 prompt 丢给 OpenClaw，让它完成本地初始化与首轮验证。
