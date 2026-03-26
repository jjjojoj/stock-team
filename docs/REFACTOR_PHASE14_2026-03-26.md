# Refactor Phase 14 - Paper Execution and Self Healing

日期：2026-03-26

## 本轮目标

- 把自动交易从“信号即成交”升级为更真实的模拟交易执行层
- 把运行护栏从“自动只读”升级为“失败补跑 + 备用源切换 + 下游自动收口”
- 让 Dashboard 能直接看到模拟订单、自愈补跑和备用源切换状态

## 主要改动

### 1. 更真实的模拟交易引擎

新增：
- `config/paper_execution.json`
- `core/simulated_execution.py`

能力：
- 模拟下单、成交、部分成交、剩余挂单
- 模拟滑点、手续费、过户费、卖出印花税
- 模拟订单账本 `simulated_orders`
- 模拟成交账本 `simulated_fills`
- 与 `trades` 表联动，记录 `execution_order_id / execution_status / fill_ratio / slippage / pnl`

交易主链更新：
- `scripts/auto_trader_v3.py`

行为变化：
- 买入和卖出不再直接改仓位，而是先进入模拟执行层
- 部分成交会保留剩余订单，后续任务运行时自动补记
- 超时未完成订单会自动撤销剩余部分
- 持仓、现金、旧 `trade_history.json` 兼容记录都会跟随真实成交回写

### 2. 更强的任务自愈

更新：
- `core/runtime_guardrails.py`
- `config/runtime_guardrails.json`

新增能力：
- 关键任务失败后自动补跑
- 对不可补跑场景做过滤，例如：
  - 只读模式
  - 观察池为空
  - 预测股票池为空
  - 预测缺失
  - 可用现金不足
- 下游链路自动收口：
  - `prediction_generate` 依赖 `selector / daily_stock_research`
  - `trade_buy` 依赖 `selector / ai_predictor`
- 记录并展示：
  - `task_retries`
  - `recent_recoveries`
  - `recent_fallbacks`

### 3. 备用数据源切换可见化

更新：
- `core/fundamentals.py`
- `scripts/selector.py`
- `scripts/auto_trader_v3.py`

行为变化：
- 交易报价从 `live_api -> tencent_quote -> fundamentals/cache -> simulated_price`
- 基本面从 `live -> cache -> snapshot/watchlist/legacy`
- 每次切换备用源都会写入 guardrails state，供 Dashboard 和 OpenClaw 值守使用

### 4. Dashboard 托管驾驶舱增强

更新：
- `web/dashboard_v3.py`

新增展示：
- 模拟订单统计
- 未完成订单数 / 部分成交数
- 自愈补跑次数
- 备用源切换次数
- 最近自动补跑摘要

## 数据层变更

更新：
- `core/storage.py`

新增/增强：
- `simulated_orders`
- `simulated_fills`
- `trades` 扩展列
- 空数据库下自动创建 `predictions / positions / trades / account` 基础表
- 新增订单摘要读取函数：
  - `load_recent_simulated_orders()`
  - `load_open_simulated_orders()`
  - `get_simulated_order_metrics()`

## 测试

新增：
- `tests/test_simulated_execution.py`

更新：
- `tests/test_runtime_guardrails.py`
- `tests/test_dashboard_v3.py`

验证通过：

```bash
python3 -m py_compile core/storage.py core/simulated_execution.py core/runtime_guardrails.py core/fundamentals.py scripts/auto_trader_v3.py scripts/selector.py web/dashboard_v3.py
python3 -m unittest tests.test_simulated_execution tests.test_runtime_guardrails tests.test_dashboard_v3 tests.test_real_data_paths
python3 -m unittest tests.test_real_data_paths tests.test_storage_sync tests.test_selector tests.test_daily_performance_report
python3 scripts/auto_trader_v3.py --buy --dry-run
```

## 当前效果

- 自动交易已经不是“信号即成交”，而是“下单 -> 成交/部分成交 -> 补记 -> 撤单”
- 系统失败后不再只有只读保护，还能自动补跑关键任务
- 上游失败会自动阻断下游敏感链路，避免错误继续扩散
- OpenClaw 和 Dashboard 都能看到自愈与备用源切换状态

## 尚未做的部分

- 模拟交易还没有引入盘口深度和分钟级成交队列
- 自动补跑目前以关键主链任务为主，尚未覆盖所有外围历史实验脚本
- `auto_trader_v3_buy` 仍然默认保守，不做自动补跑，避免重复建仓
