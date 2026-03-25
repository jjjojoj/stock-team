# REFACTOR PHASE 9 - 2026-03-26

## 本轮目标

修复 2026-03-25 晚间飞书通知里暴露出的 4 类问题：

1. 规则验证日报同一条规则同时出现在活跃库、验证池、淘汰库。
2. 每日绩效汇报仍在使用模拟数据，不是真实运行结果。
3. 持仓汇报仍依赖 `config/positions.json`，空仓时会发“暂无持仓配置”这种低质量提示。
4. 动态标准选股会把 0 分和明显不达标的股票塞进 Top 列表。

## 代码改动

### 1. 规则状态互斥与自愈

- 在 `core/storage.py` 新增：
  - `load_positions()`
  - `load_account()`
  - `build_portfolio_snapshot()`
  - `reconcile_rule_stores()`
  - `load_rule_state()`
  - `save_rule_state()`
- `reconcile_rule_stores()` 现在会按业务语义做冲突裁决：
  - 活跃规则优先于验证池副本
  - 较新的淘汰记录可以覆盖更旧的活跃/验证状态
  - 同一 `rule_id` 在 3 套存储中只保留 1 份有效状态
- `scripts/rule_validator.py` 改为统一走 `load_rule_state()` / `save_rule_state()`。
- `web/dashboard_v3.py` 改为读取“已对齐”的规则状态，避免面板继续显示冲突统计。
- 已对当前运行态规则数据执行一次落盘清理，重复状态已清除。

### 2. 每日绩效汇报改成真实数据

- `scripts/daily_performance_report.py` 不再返回硬编码模拟值。
- 当前绩效口径改为：
  - `CIO`: 当前资产快照 + 账户历史收益
  - `Quant`: 已验证预测的胜率、方向对齐收益、置信度校准相关性
  - `Trader`: 批准提案执行率、交易摩擦率、卖出择时胜率
  - `Risk`: 风险触发卖出的有效性、止损执行率、漏报次数
  - `Research`: 最新研究信息条数、累计预测准确率、Research 提案采用率
  - `Learning`: 最近 30 天学习日志、规则有效率、学习贡献分
- 报表头部新增口径说明：
  - `当前资产快照 + 累计闭环预测/交易/学习数据`

### 3. 持仓汇报统一接主账本

- `scripts/feishu_notifier.py` 的持仓汇报改为统一读取 `build_portfolio_snapshot()`。
- 空仓时不再提示“请在 config/positions.json 中添加持仓信息”，而是输出真实空仓状态和现金。
- `scripts/price_report.py` 不再自己重复算一套持仓/盈亏，改为直接复用 `send_portfolio_report()`。

### 4. 动态标准选股加阈值

- `scripts/selector.py` 新增 `MIN_TOP_CANDIDATE_SCORE = 20`。
- `top()` 输出和飞书通知现在只推送综合评分 `>= 20` 的候选股。
- 当没有达标候选时，会明确提示“未筛出综合评分达到阈值的候选股”。

### 5. 连接管理补强

- `core/storage.py` 新增 `ManagedConnection`，修复仓库里大量 `with sqlite3.connect(...)` 风格导致的连接未自动关闭问题。

## 验证

执行通过：

```bash
python3 -m py_compile core/storage.py scripts/rule_validator.py scripts/daily_performance_report.py scripts/feishu_notifier.py scripts/price_report.py scripts/selector.py web/dashboard_v3.py
python3 -m unittest tests.test_rule_storage tests.test_feishu_notifier tests.test_daily_performance_report tests.test_selector
python3 scripts/daily_performance_report.py
python3 - <<'PY'
from scripts.feishu_notifier import generate_portfolio_report, format_report
portfolio = generate_portfolio_report('close')
title, content, level = format_report('close', portfolio)
print(title)
print(level)
print(content)
PY
```

结果确认：

- 规则冲突已清理，`dir_fall_below_ma20` / `dir_rsi_oversold` 不再同时出现在多套状态中。
- 空仓持仓汇报现在显示真实现金和空仓状态，不再报配置缺失。
- 动态标准选股不会再把 `0/100` 的股票塞进 Top 列表。
- 每日绩效汇报已改成真实数据口径，并成功发送到飞书。

## 后续建议

1. 把 `daily_performance_report.py` 中仍属“代理指标”的风险/学习评分进一步落到标准化表结构，避免长期依赖文件推导。
2. 给 `selector.py` 再补一层行业分散约束，避免高分结果过度集中在单一主题。
3. 后续如果继续整理 `trade_history.json` 到 SQLite，可再把 Trader/Risk 指标完全收口到数据库。
