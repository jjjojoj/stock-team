# Phase 13 - Autopilot Safeguards And Auto Read-Only

Date: 2026-03-26

## Goal

继续朝“除了真实下单外尽量全托管”的方向推进，把系统从“有监控、有护栏”进一步升级为：

- 连续异常时能自动降级
- 不用人工盯着就能进入只读保护
- 主链恢复稳定后能自动退出保护
- Dashboard 能直接解释当前为什么不适合继续放手自动运行

## What Changed

### 1. Runtime guardrails 增加 autopilot 状态机

- 文件: `core/runtime_guardrails.py`
- 文件: `config/runtime_guardrails.json`

新增能力：

- 关键任务连续失败计数
- 自动进入只读模式
- 自动只读到期与恢复成功计数
- 自动退出只读模式
- 任务健康状态持久化到 `data/runtime_guardrails_state.json`

当前关键任务：

- `ai_predictor`
- `selector`
- `daily_stock_research`
- `midday_review`
- `auto_trader_v3_buy`
- `auto_trader_v3_sell`

结果：

- 现在系统不会只是“记住哪里坏了”
- 它会在连续坏掉时主动收缩自动能力，先保护资金与预测链

### 2. 主链任务新增成功回执

- 文件: `scripts/ai_predictor.py`
- 文件: `scripts/selector.py`
- 文件: `scripts/daily_stock_research.py`
- 文件: `scripts/midday_review.py`
- 文件: `scripts/auto_trader_v3.py`

新增行为：

- 成功执行后会写入 guardrail success
- 如果之前触发过自动只读，成功回执会参与恢复计数
- `auto_trader_v3.py` 的卖出检查在“无卖出信号”时不再返回非零退出码

结果：

- 自动只读不再只能进不能出
- 正常“无信号”不会再被误当成任务失败

### 3. Dashboard 接入自动只读与恢复状态

- 文件: `web/dashboard_v3.py`

现在 monitoring 页面会直接显示：

- 当前是否处于只读模式
- 只读是手动触发还是自动保护
- 自动只读原因
- 最近 guardrail errors / warnings
- 当前托管模式与自动运行评级

结果：

- Dashboard 现在不仅展示“运行了什么”
- 也能展示“现在为什么该继续自动、为什么该保守”

## Validation

执行通过：

- `python3 -m py_compile core/runtime_guardrails.py scripts/ai_predictor.py scripts/auto_trader_v3.py scripts/daily_stock_research.py scripts/midday_review.py scripts/selector.py web/dashboard_v3.py tests/test_runtime_guardrails.py tests/test_dashboard_v3.py`
- `python3 -m unittest tests.test_runtime_guardrails tests.test_dashboard_v3 tests.test_enhanced_cron_handler`
- `python3 -m unittest tests.test_real_data_paths tests.test_fundamentals tests.test_midday_review tests.test_ai_predictor tests.test_selector tests.test_feishu_notifier tests.test_daily_performance_report tests.test_rule_storage`

新增验证重点：

- 连续 critical errors 会自动触发只读
- 连续 success 会自动恢复
- monitoring API 会返回 autopilot / auto-read-only 状态

## Operational Meaning

这轮之后，股票团队更接近你要的“全托管模拟盘”了：

- 不是只靠你盯 dashboard
- 系统自己会在关键异常时收手
- 恢复后也能自己慢慢放开

但它仍然不是“完全无监督”：

- 自动恢复依赖关键任务真实恢复成功
- 输入数据如果长期过期，Dashboard 仍会把状态评成需要人工介入
- 目前保护重点仍放在预测生成和自动买入，不是对所有外围实验模块全面接管

## Bottom Line

当前更准确的状态是：

- 模拟托管：基本成立
- 自动降级：已具备
- 自动恢复：已具备基础版
- 完全无人值守：还差更完整的数据源自愈和模拟撮合层
