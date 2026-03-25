# Phase 6: 股票 Cron Webhook 统一

日期：2026-03-25

## 目标

把股票相关 cron 任务统一切到同一个飞书群 webhook。

同时解决两个遗留问题：

1. 旧的 OpenClaw `announce` 投递还在跑，造成 `Message failed`
2. 部分脚本仍然手写文本消息，卡片格式、长度控制和回退策略不统一

## 本轮代码改动

### 1. 统一飞书发送器

文件：

- `scripts/feishu_notifier.py`

改动：

- 默认改为 `interactive` 卡片发送
- 按段落拆分卡片内容，避免单块内容过长
- 对消息体做保守长度控制，超长时自动截断
- 卡片发送失败时自动回退到 `text` 消息
- 保留统一 `send_feishu_message(...)` 入口，供股票脚本复用

设计说明：

- 参考飞书官方内容平台关于自定义机器人消息体大小的说明，JSON 建议不超过 30 KB
- 实现中使用更保守的 `28 KB` 安全阈值

### 2. 旧文本发送脚本改为统一 notifier

已改脚本：

- `scripts/daily_stock_research.py`
- `scripts/midday_review.py`
- `scripts/price_report.py`
- `scripts/api_health_monitor.py`
- `scripts/a_share_risk_monitor.py`
- `scripts/circuit_breaker.py`
- `scripts/market_style_monitor.py`
- `scripts/daily_performance_report.py`

效果：

- 地址统一从 `FEISHU_WEBHOOK_URL` 或本地私有配置读取
- 卡片格式统一
- 不再各脚本重复拼接 webhook payload

### 3. 原来依赖 OpenClaw announce 的任务补脚本发送能力

已补发消息能力：

- `scripts/news_trigger.py`
- `scripts/daily_web_search.py`
- `scripts/selector.py`
- `scripts/rule_validator.py`
- `scripts/ai_predictor.py`
- `scripts/backtester.py`
- `scripts/overfitting_test.py`

新增脚本：

- `scripts/afternoon_update.py`

用途：

- 为“下午开盘前更新”提供明确脚本入口
- 读取午盘反思、当前预测、账户与观察池，生成统一下午策略卡片

### 4. 复盘语义修正

文件：

- `scripts/daily_review_closed_loop.py`

改动：

- 当日无到期预测时，不再向群里发送“0 条验证”的无意义复盘消息
- 消息文案明确说明：该任务是“到期预测验证”，不是盘中涨跌快评

## OpenClaw cron 外部配置改动

已将股票相关 cron 任务的 `delivery.mode` 统一切为 `none`，避免继续走旧 `announce` 链路。

同时更新 payload message，改为：

- 明确运行具体脚本
- 说明“脚本会自行通过 webhook 发送飞书卡片”
- 明确“不再使用 OpenClaw announce 发送聊天消息”

已切换为 `delivery.mode = none` 的股票任务包括：

- 每日深度研究 1 股
- 新闻监控-预测更新
- API 健康检查
- 持仓汇报（早盘/午盘开盘/午盘收盘/收盘）
- 午盘反思
- 下午开盘前更新
- 选股层 - 动态标准选股
- 交易层 - 自动买入 / 自动卖出
- 收盘复盘 + 选股标准进化
- 每日预测复盘
- 每日绩效汇报
- 规则验证（每日）
- 每日炒股书籍学习
- 市场风格监控
- 开盘前联网搜索
- 早上AI预测生成
- 每周回测验证（保留）
- 每月过拟合测试
- 压力测试

## 监控面板兼容改动

文件：

- `web/enhanced_cron_handler.py`
- `tests/test_enhanced_cron_handler.py`

改动：

- 当任务已经切到 `delivery.mode = none`
- 且历史错误仍是旧的 `⚠️ ✉️ Message failed`

则面板显示为：

- `warning`
- `legacy_notify_error`
- 文案：`历史旧投递错误；当前已切换脚本 webhook，等待下次运行刷新`

这样可以避免旧历史状态继续被误判为当前红色失败。

## 验证记录

本地验证：

- `python3 -m py_compile scripts/feishu_notifier.py ...`
- `python3 -m unittest tests.test_feishu_notifier tests.test_enhanced_cron_handler tests.test_prediction_utils tests.test_storage_sync tests.test_rule_storage tests.test_dashboard_v3`

实际 webhook 发送验证：

- `python3 scripts/rule_validator.py validate`
- `python3 scripts/selector.py top 3`
- `python3 scripts/daily_web_search.py`
- `python3 scripts/afternoon_update.py`

均已实际发出飞书卡片。

## 备注

OpenClaw `cron run` 在当前版本下更像“异步入队”，不会立刻同步回最终状态。
因此旧的 `lastError` 需要等任务下一次真实完成后刷新；本轮已通过面板兼容逻辑避免误报。
