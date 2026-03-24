# Phase 4 重构记录（2026-03-25）

## 目标

基于现有 `web/dashboard_v3.py` 继续收尾监控面板，把仍然使用占位数据的页面全部接到真实数据源，并补齐可复用测试。

本阶段关注三件事：

1. 让监控、研究、交易、回测、报告、新闻页面全部显示真实数据。
2. 修复前端与后端接口返回结构不一致的问题。
3. 增加 dashboard 数据提取和 summary 组装的测试，避免后续回归。

---

## 代码变更

### 1. `web/dashboard_v3.py`

#### 后端数据侧

- 新增 dashboard summary 接口：
  - `/api/monitoring-summary`
  - `/api/research-summary`
  - `/api/trading-summary`
  - `/api/backtests`
  - `/api/reports-summary`
  - `/api/news-summary`
- 新增/完善的数据提取函数：
  - `get_monitoring_snapshot()`
  - `get_research_snapshot()`
  - `get_trading_snapshot()`
  - `get_backtest_results()`
  - `get_reports_snapshot()`
  - `get_news_snapshot()`
- `get_predictions()` 不再只返回 `active` 预测，改为返回最近预测记录，供“最近胜率”和“近期预测列表”使用。
- 新增 `_strip_markdown_emphasis()`，用于清理周报中 `**36.5%**` 这类 markdown 包裹值。
- 修复 `get_enhanced_cron_data()` 中 `task_id` 未定义问题。

#### 前端页面侧

- 概览页：
  - 补上 `overview-profit-badge`
  - 补上 `overview-scripts-status`
  - 接上“周期 / 防御”风格数据
- 监控页：
  - 把假数据“上证指数 / 深证成指”替换为真实可得的“市场数据 API / 搜索 API”
  - 新增 API 健康列表渲染
  - 接上熔断任务实时状态
- AI 预测页：
  - 修复 `/api/predictions` 返回对象、前端却按数组读取的问题
  - 修复“昨日预测”统计逻辑
  - 接上“最近胜率”
- 选股页：
  - 修复 `/api/selector-results` 返回对象、前端却按数组读取的问题
- 研究页：
  - 接上 `data/research_*.json`
  - 接上 `data/daily_search/laverify_summary.txt`
- 事件页：
  - 修复 `/api/events-today` 返回对象、前端却按数组读取的问题
  - 补上事件列表数量 badge
- 交易页：
  - 接上 `account / positions / trades`
  - 渲染今日交易记录表
- 持仓页：
  - 接上止盈止损表
- 回测页：
  - 接上 `outputs/backverify_*.md` 与 `outputs/weekly_backtest_*.md`
- 报告页：
  - 把占位文案“周度收益 / 同比 / 累计收益”调整为当前真实可提供的“准确率 / 综合得分 / 摘要”
  - 接上 `data/weekly_reports/*.md` 与 `data/reviews/*.md`
- 新闻页：
  - 接上 `news_labels` 数据表

---

## 新增测试

### 2. `tests/test_dashboard_v3.py`

新增 3 组单测：

1. `get_api_health_snapshot()` 可以把 `config/api_status.json` 展平为 dashboard 可消费结构。
2. `get_reports_snapshot()` 可以正确读取周报与复盘，并去掉 markdown 强调符号。
3. `get_backtest_results()` 可以从 markdown 回测报告中抽取期间、收益率、回撤和夏普比率。

---

## 验证记录

### 语法检查

```bash
python3 -m py_compile web/dashboard_v3.py
```

### 单元测试

```bash
python3 -m unittest tests.test_dashboard_v3 tests.test_prediction_utils tests.test_storage_sync tests.test_rule_storage
```

结果：`Ran 10 tests ... OK`

### HTTP 烟测

临时在 `8092` 端口启动 dashboard 后验证：

```bash
curl -sf http://127.0.0.1:8092/api/monitoring-summary
curl -sf http://127.0.0.1:8092/api/research-summary
curl -sf http://127.0.0.1:8092/api/trading-summary
curl -sf http://127.0.0.1:8092/
```

确认点：

- 新增 summary API 可以正常返回真实数据
- 首页 HTML 已包含新的监控字段与前端绑定逻辑

---

## 当前状态

完成后，`dashboard_v3` 已经从“部分占位面板”变成“主要页面均接真实数据”的状态。

仍然保留的现实限制：

- 监控页没有直接 A 股指数实时行情源，所以该页改为展示当前系统真实可得的 API 健康与熔断状态，而不再展示伪造指数数值。
- `account.position_count` 和 `positions` 表在本地运行数据里仍可能短期不一致，这属于历史账户同步数据问题，不是 dashboard 渲染问题。
