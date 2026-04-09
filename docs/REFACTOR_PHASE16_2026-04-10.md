# Refactor Phase 16 - 2026-04-10

## 背景

2026-04-07 到 2026-04-09 期间，股票团队持续产出飞书日报，但交易账本保持 `0 持仓 / 0 成交`。排查后确认问题不在 Dashboard 本身，而在交易供给链断裂：

1. `ai_predictor.py` 仍按“同标的存在 active prediction 就跳过”的旧逻辑运行，导致 4 月 2 日生成的一批周级预测持续占用 active 槽位，后续交易日没有真正刷新预测。
2. `selector.py` 只负责发飞书 Top 候选消息，没有把候选正式写回 watchlist 和 proposal pipeline。
3. Dashboard 虽然正确显示没有成交，但没有直接说明“为什么没成交”，运维时需要人工进数据库排查。

## 本次改动

### 1. 预测改成按交易日刷新

文件：

- `scripts/ai_predictor.py`

改动：

- 新增 `_prepare_prediction_slot()`，同一只股票每天最多保留 1 条当日 active prediction。
- 当发现同标的旧 active prediction 时，会先归档为 `expired` 历史记录，再生成今日新预测。
- 同交易日重复运行时仍会跳过，避免早盘 cron 重复堆叠预测。

效果：

- 不再反复消费 4 月 2 日那批旧预测。
- 交易链和午盘即时验证都能看到“今日新预测”。

### 2. 选股结果正式进入观察池和提案流水线

文件：

- `scripts/selector.py`
- `core/proposals.py`

改动：

- `selector top` 现在会把达标候选同步到 watchlist。
- 同步时会生成标准化 watchlist entry，包括 `reason / target_price / stop_loss / score / source=selector`。
- 同时为候选创建或刷新正式 proposal，来源代理标记为 `Selector`。
- 新增 `create_or_update_selection_proposal()` 统一处理 selector 提案。

效果：

- 动态选股不再只是“发消息”，而是正式给交易链供料。
- Dashboard 和 Trader 可以看见 selector 的正式候选。

### 3. Dashboard 新增“今日未交易原因”诊断

文件：

- `web/dashboard_v3.py`

改动：

- `get_trading_snapshot()` 现在会返回 `prediction_activity` 和 `trade_readiness`。
- 新增交易页诊断 Banner，直接展示：
  - proposal pipeline 卡在哪一层
  - 今日有没有生成新预测
  - 当前活跃预测数量
  - 最近一批预测创建时间

效果：

- 当今日没有成交时，Dashboard 不再只显示空表，而是直接解释：
  - 是没有 proposal
  - 还是 proposal 卡在 pending / quant / risk / approved
  - 还是今日预测没有刷新

### 4. CIO 审批阈值改为“保守但不僵死”

文件：

- `scripts/auto_trader_v3.py`

改动：

- 新增 `PIPELINE_CONFIG`
- CIO 最低量化置信度从硬编码 `70%` 调整为 `65%`
- 允许在没有 research score 时回退读取 selection score
- 仍然保留：
  - 风控必须通过
  - 分析评分必须 >= 50
  - 上行空间必须 >= 5%

效果：

- 系统不再因为一个过硬的固定阈值长期完全不出手。
- 同时仍保持模拟盘的保守风格，不会因为低质量信号频繁成交。

## 验证

执行通过：

```bash
python3 -m py_compile \
  scripts/ai_predictor.py \
  scripts/selector.py \
  scripts/auto_trader_v3.py \
  web/dashboard_v3.py \
  core/proposals.py \
  tests/test_ai_predictor.py \
  tests/test_selector.py \
  tests/test_auto_trader_v3.py \
  tests/test_dashboard_v3.py \
  tests/test_proposals.py

python3 -m unittest \
  tests.test_ai_predictor \
  tests.test_selector \
  tests.test_auto_trader_v3 \
  tests.test_dashboard_v3 \
  tests.test_proposals
```

额外烟测：

- `selector.top(3)` 已能筛出当前候选并同步到 watchlist / proposal pipeline。
- `AIPredictor.generate_prediction('sh.600111')` 已能把 `Research` 提案推进到 `quant_validated`。

## 当前结论

- 现在的“无交易”已经可以被系统自己解释，而不是只能靠人工查库。
- 交易链已经从“Research 提案但无人接手”，推进到“Quant 可接手、Dashboard 可解释阻塞点”。
- 是否真实成交，后续仍取决于当天 proposal 质量、置信度和风控条件，而不是纯粹卡在系统断链。
