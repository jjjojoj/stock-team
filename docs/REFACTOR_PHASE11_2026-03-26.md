# Phase 11 - Managed Stability And Semi-Automatic Operations

Date: 2026-03-26

## Goal

在 Phase 10 已完成“真实数据清理”的基础上，进一步把主链路补成更适合 OpenClaw 长期半自动托管的形态：

- 运行要有护栏
- 学习要有限制
- 基本面要有统一访问层
- 自动任务要尽量避免空数据、重入和小样本误调

## What Changed

### 1. 新增统一运行护栏层

- 文件: `config/runtime_guardrails.json`
- 文件: `core/runtime_guardrails.py`

新增能力：

- 任务锁：避免同一个 cron 任务重入
- 只读模式：为后续异常时降级预留统一开关
- 数据新鲜度检查：对 `daily_search / predictions / fundamental snapshot / stock_pool` 做统一评估
- 午盘学习参数：把最小样本、连续错误门槛、调参步长、回滚窗口都集中配置

结果：

- `selection / research / prediction_generate / trade_buy / trade_sell` 现在都有统一 guardrail 入口
- 后续 OpenClaw 接手时，不需要各脚本分别猜测“当前可不可以继续跑”

### 2. 午盘学习改成“受控调参 + 自动回滚”

- 文件: `scripts/midday_review.py`

新增行为：

- 未达到最小验证样本，不自动调参
- 错误样本未形成明显方向偏差，不自动调参
- 需要连续多次同向偏差，才允许小步修改 `confidence_threshold`
- 调整后会记录基线准确率和评估窗口
- 若后续数轮午盘表现显著恶化，自动回滚到旧阈值
- 学习记录仍会进入 `learning/memory.md` 和月度学习日志，但“记录”与“改参数”现在明确分离

结果：

- 系统仍然具备自我纠错能力
- 但不会因为一次午盘误判或几条小样本错误，就把长期阈值带偏

### 3. 新增共享基本面访问层

- 文件: `core/fundamentals.py`

读取顺序：

1. 实时行情快照（通过项目 venv 子进程调用 AKShare）
2. 本地缓存 `data/live_fundamentals_cache.json`
3. 维护快照 `config/fundamental_data.md`
4. watchlist / legacy 静态字段兜底

结果：

- 研究和选股不再各自维护一套基本面入口
- 即使实时接口失败，也能优雅回退，不会直接把整个任务打挂

### 4. 研究、选股、预测、交易接入 guardrails

- 文件: `scripts/daily_stock_research.py`
- 文件: `scripts/selector.py`
- 文件: `scripts/ai_predictor.py`
- 文件: `scripts/auto_trader_v3.py`

更新内容：

- 研究链在运行前检查股票池/基本面快照状态
- 选股链统一通过共享基本面层拿基础数据
- 预测生成在观察池和持仓都为空时直接阻断，不再捏造默认股票池
- 交易链在自动买入前检查观察池、活跃预测、预测新鲜度和现金状态
- 买卖任务都加了重入锁

结果：

- OpenClaw 以后长期托管时，默认会更保守、更可审计
- “没数据还硬跑”“两个 cron 打架”“空仓下仍生成伪目标池”这类问题都被明显压低

### 5. 修复跨 Python 版本的 adapter 路径风险

- 文件: `adapters/akshare_adapter.py`
- 文件: `adapters/baostock_adapter.py`

之前状态：

- 适配器硬编码 `venv/lib/python3.14/site-packages`
- 当脚本实际跑在别的解释器版本下时，可能把不兼容的二进制包塞进当前进程

现在状态：

- 只会尝试注入与当前解释器版本匹配的 venv `site-packages`

结果：

- 避免了“能 import 但运行时炸 ABI”的隐性不稳定问题

## Validation

执行通过：

- `python3 -m py_compile core/fundamentals.py core/runtime_guardrails.py scripts/ai_predictor.py scripts/auto_trader_v3.py scripts/daily_stock_research.py scripts/midday_review.py scripts/selector.py adapters/akshare_adapter.py adapters/baostock_adapter.py`
- `python3 -m unittest tests.test_runtime_guardrails tests.test_midday_review tests.test_fundamentals tests.test_ai_predictor tests.test_real_data_paths tests.test_rule_storage tests.test_feishu_notifier tests.test_daily_performance_report tests.test_selector tests.test_enhanced_cron_handler tests.test_dashboard_v3`

新增测试覆盖：

- `tests/test_runtime_guardrails.py`
- `tests/test_midday_review.py`
- `tests/test_fundamentals.py`
- `tests/test_ai_predictor.py`

## Operational Meaning

当前系统相较于 Phase 10，更接近“适合 OpenClaw 半自动托管”的状态：

- 真数据链路：Phase 10 已经打通
- 调度与通知：之前已收口
- 运行护栏：本轮补上
- 自我学习：本轮从启发式直接调参，升级成“受控学习”

更准确地说：

- 自我纠错：有
- 自我学习：有，而且这次更稳了
- 自我进化：开始更可信，但仍建议保留人工监督

推荐托管模式：

- 日常 cron 自动运行
- 低风险学习自动执行
- 重大参数漂移、连续失败、强制只读切换时，由 OpenClaw 主动上报人工确认
