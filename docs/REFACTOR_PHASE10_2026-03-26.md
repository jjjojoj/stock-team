# Phase 10 - Real Data Audit And Closed-Loop Check

Date: 2026-03-26

## Goal

继续清理活跃股票 cron 链路里仍然存在的旧文件依赖、占位统计和伪造默认值，并给出当前系统是否已经达到“真正闭环、自我学习、自我纠错、自我进化”的现实评估。

## What Changed

### 1. Dashboard cron 统计改为真实运行数据

- 文件: `web/enhanced_cron_handler.py`
- 文件: `web/dashboard_v3.py`
- 现在 cron 面板直接使用 OpenClaw 的真实 `lastDurationMs` 和 `consecutiveErrors`
- 去掉了原先基于任务类型推测平均耗时、假定历史运行成功的逻辑

结果:
- Dashboard 中的 `run_count / success_count / error_count / avg_duration_ms` 现在都只反映真实状态，不再用估算值填充。

### 2. 下午更新改为读取主账本

- 文件: `scripts/afternoon_update.py`
- `portfolio / positions / predictions` 现在统一通过共享存储层和规范化预测结构读取
- 资产统计使用 `build_portfolio_snapshot()`

结果:
- 午后更新不再依赖 `config/portfolio.json` 和 `config/positions.json` 的旧口径。

### 3. 深度研究去掉硬编码候选与默认基本面

- 文件: `scripts/daily_stock_research.py`
- 研究对象改为从 `config/stock_pool.md` 解析
- 基本面改为从 `config/fundamental_data.md` 读取
- 去掉了之前的硬编码优先股列表和固定 PE/PB/市值默认值

结果:
- 研究链路现在基于维护中的真实股票池和基本面快照，而不是脚本里写死的样例候选。

### 4. A 股风险监控补上真实政策风险检测

- 文件: `scripts/a_share_risk_monitor.py`
- 政策风险改为从最新 `data/daily_search/*.json` 读取可搜索新闻
- 影响标的改为结合主账本持仓和观察池识别
- 新增标题/来源双重过滤，避免把普通研报误报成监管风险

结果:
- 风险监控从“占位实现”变成真实扫描，但保留了更保守的触发条件，优先减少误报。

### 5. 自动交易价格链路优先真实行情

- 文件: `scripts/auto_trader_v3.py`
- 修复硬编码 `python3.14` 虚拟环境路径
- 在 adapters 不可用时先走腾讯实时行情，再最后才回退模拟价格

结果:
- 当前机器上交易链路已经能拿到真实行情，不再默认落到模拟价格。

### 6. 新闻监控改为主账本 + 真实搜索结果回退

- 文件: `scripts/news_trigger.py`
- 持仓来源改为主账本
- 预测加载改为规范化结构，并保存后同步数据库
- 当 `news_cache.json` 没有数据时，回退到最新 `daily_search` 结果
- 收紧新闻评分，只分析标题和正文前 240 字，并移除“铜/铝/黄金/锂/稀土”这类会造成泛滥误报的行业名加分

结果:
- 新闻流现在优先真实数据，同时不再把普通行业文章当成强事件强行修改预测。

### 7. 其他活跃 cron 的旧口径收口

- 文件: `scripts/daily_web_search.py`
- 文件: `scripts/market_review_v2.py`
- 文件: `scripts/midday_review.py`
- 文件: `scripts/circuit_breaker.py`

结果:
- `daily_web_search.py` 改为读取主账本持仓
- `market_review_v2.py` 的持仓分析改为读取组合快照
- `midday_review.py` 改为读取规范化预测结构
- `circuit_breaker.py` 去掉了拿不到数据时伪造 `15.0` 恐慌值的逻辑

## Validation

执行通过:

- `python3 -m py_compile scripts/news_trigger.py scripts/daily_web_search.py scripts/market_review_v2.py scripts/midday_review.py scripts/circuit_breaker.py scripts/a_share_risk_monitor.py scripts/auto_trader_v3.py scripts/daily_stock_research.py scripts/afternoon_update.py web/enhanced_cron_handler.py web/dashboard_v3.py tests/test_real_data_paths.py`
- `python3 -m unittest tests.test_real_data_paths tests.test_rule_storage tests.test_feishu_notifier tests.test_daily_performance_report tests.test_selector tests.test_enhanced_cron_handler tests.test_dashboard_v3`

补充烟测:

- `AShareRiskMonitor.check_policy_risk()` 当前误报样本已压到 0
- `NewsMonitor.check_news_impact()` 在当前 2026-03-25 搜索结果集上不再把普通投研文章误判成高影响事件
- `MarketReview()._analyze_positions()` 可直接读取主账本快照

## Closed-Loop Assessment

### 已经做到的部分

- 预测会在到期后被验证，并回写准确率、规则权重和验证池样本
- 规则验证池可以晋升、淘汰，并同步到规则库与 Dashboard
- 交易、持仓、观察池、复盘、通知基本已经围绕 SQLite 主账本收口
- 新闻、研究、复盘、规则验证、绩效汇报已经基本接上真实数据

### 还没完全做到的部分

- `midday_review.py` 仍然是启发式学习，不是统计显著性驱动的参数优化
- `daily_stock_research.py` 的基本面现在来自维护中的 markdown 快照，还不是实时基本面 API
- `daily_book_learning.py` 仍然基于内置书籍知识点列表，不是自动解析真实书籍内容
- 仓库外围仍有一些未纳入主 cron 链的旧模块保留模拟/示例逻辑，不应误判为已经全面实盘化

## Bottom Line

当前系统已经具备“主交易与复盘链路接近真闭环”的条件：

- 有真实数据输入
- 有执行结果记录
- 有复盘验证
- 有规则调整
- 有验证池晋升/淘汰

但它还不是完全自动、无需监督的“自我进化型投资公司”。

更准确的说法是：

- 自我纠错：已经有了
- 自我学习：已经有，但仍有一部分是启发式和半自动
- 自我进化：已经开始形成机制，但还没有达到完全自治
