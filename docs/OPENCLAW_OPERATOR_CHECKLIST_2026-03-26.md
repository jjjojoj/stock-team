# OpenClaw Operator Checklist

日期：2026-03-26

## 适用目标

这份清单面向接手 `china-stock-team` 的 OpenClaw 操作员。

目标不是解释全部代码，而是回答 4 个最关键的问题：

1. 每天先看什么
2. 哪些状态算正常
3. 哪些情况应该只读/暂停/人工确认
4. 出问题时先查哪里

## 一、值守原则

- 真实运行状态优先看 `OpenClaw cron` 和 `8082 Dashboard`
- 数据一致性优先相信 `database/stock_team.db`
- 飞书是通知层，不是主真源
- 遇到数据过期、连续失败、关键参数漂移，不要硬跑，优先升级处理
- 自动执行可以继续，但重大偏差要主动上报，不要默默吞掉

## 二、每日巡检顺序

### 1. 先看调度状态

命令：

```bash
openclaw cron list --json
```

重点看：

- 是否有股票主链任务处于 `error`
- 是否存在连续失败的任务
- 是否有关键任务长时间未运行
- 是否有任务卡在 `running` 很久不释放

关键任务：

- `daily_web_search.py`
- `ai_predictor.py generate`
- `news_trigger.py check`
- `midday_review.py`
- `selector.py top 10`
- `auto_trader_v3.py`
- `daily_review_closed_loop.py`
- `rule_validator.py validate`

### 2. 再看 Dashboard

地址：

- `http://127.0.0.1:8082`
- `http://127.0.0.1:8082/cron`

重点页面：

- cron 状态
- 监控摘要
- 交易执行页（proposal pipeline / recent handoffs）
- 规则库 / 验证池
- watchlist
- news summary

正常状态应满足：

- 面板数据能正常返回
- cron 错误不是持续累积
- 规则库、验证池、观察池都能读到真实数据
- 新闻摘要不是空白或明显过期

### 3. 最后看护栏状态

关键文件：

- `config/runtime_guardrails.json`
- `data/runtime_guardrails_state.json`

重点检查：

- 最近是否持续出现 `warning / error` 事件
- 午盘学习是否连续触发调参
- 是否发生自动回滚
- 是否需要开启 `force_read_only`

## 三、快速健康检查

推荐顺序：

```bash
python3 -m unittest tests.test_runtime_guardrails tests.test_midday_review tests.test_fundamentals tests.test_ai_predictor tests.test_real_data_paths
python3 scripts/proposal_pipeline.py status
python3 scripts/rule_validator.py report
python3 scripts/ai_predictor.py brief
```

适用场景：

- 刚接手项目
- 刚改完脚本
- 发现通知内容异常
- 怀疑假数据回流

## 四、出现这些情况时，不要继续自动买入

### 直接升级为人工确认

- `trade_buy` 被 guardrails 阻断
- 预测数据超过新鲜度阈值
- 观察池为空但系统仍试图生成买入候选
- 自动交易价格只能落到模拟价
- 同一任务出现重入锁冲突并持续发生
- 规则验证、复盘、预测三者数据明显打架
- `pending / quant_validated / risk_checked / approved` 长时间堵在同一阶段

### 建议切换只读模式

操作文件：

- `config/runtime_guardrails.json`

建议动作：

- 将 `force_read_only` 改为 `true`
- 保持研究、复盘、规则验证继续运行
- 暂停自动买入，等待人工确认

适用情形：

- 连续两轮以上关键任务异常
- 数据新鲜度持续不达标
- 新闻流、预测流、持仓流出现明显错位
- 飞书通知内容与 Dashboard / DB 状态长期不一致

补充：

- 当前系统也可能因为关键任务连续失败而自动进入只读，这时优先先查 `data/runtime_guardrails_state.json`

## 五、出现这些情况时，可以继续自动运行

- 只有单个非关键任务短时 warning
- AKShare 实时基本面失败，但系统已正常回退到缓存或快照
- 飞书卡片发送失败后成功回退文本
- 午盘学习只记录经验，没有触发调参
- 规则验证有新增淘汰或晋升，但三库状态保持互斥

## 六、按问题类型排查

### 1. 通知内容不对

先查：

- `scripts/feishu_notifier.py`
- 对应业务脚本
- Dashboard 同步接口

再看：

- 是否因为超长消息被截断
- 是否是旧历史任务状态没有刷新
- 是否是主账本与兼容 JSON 镜像刚同步中的短暂差异

### 2. 预测不生成或生成很少

先查：

- `scripts/ai_predictor.py`
- `config/watchlist.json`
- `database/stock_team.db`
- `data/runtime_guardrails_state.json`

重点看：

- 观察池是否为空
- 持仓是否为空
- 是否被 `prediction_generate` guardrails 阻断

### 3. 研究或选股结果明显失真

先查：

- `core/fundamentals.py`
- `config/fundamental_data.md`
- `data/live_fundamentals_cache.json`
- `config/stock_pool.md`

重点看：

- 实时基本面是否失败后正确回退
- 快照是否过旧
- watchlist / legacy 兜底是否错误覆盖了高优先级数据

### 4. 午盘学习开始频繁改参数

先查：

- `scripts/midday_review.py`
- `config/runtime_guardrails.json`
- `data/runtime_guardrails_state.json`

重点看：

- 是否真的满足最小样本门槛
- 是否是连续同向偏差
- 是否已进入自动回滚窗口

### 5. 模拟交易看起来在“执行”，但账本没有闭环

先查：

- `core/simulated_execution.py`
- `database/stock_team.db`
- `scripts/auto_trader_v3.py`
- Dashboard 交易执行页

重点看：

- `simulated_orders` 是否存在 `partial_filled / pending`
- 是否已经触发自动补记或超时撤单
- `trades.execution_order_id` 是否和订单账本对得上
- `proposals` 是否完成 `Research -> Quant -> Risk -> CIO -> Trader` 交接链

### 6. 迟迟没有发生交易

先查：

- `python3 scripts/proposal_pipeline.py status`
- `scripts/auto_trader_v3.py`
- 交易执行页中的 proposal pipeline 统计
- 交易执行页中的“今日未交易原因”

重点看：

- 是否已经有 `approved` 提案
- 提案是否停在 `quant_validated / risk_checked`
- CIO 是否因为置信度、研究评分或预期收益空间驳回
- 是否因空仓基线重置后尚未积累新的研究提案
- `ai_predictor` 是否真的在当日刷新了新预测，而不是反复复用旧 active prediction
- `selector` 是否已把当日 Top 候选同步进 watchlist 和 proposal pipeline
- 当前现金和持仓是否已经按成交结果回写

## 七、OpenClaw 应记住的升级规则

- 任务失败不等于系统崩溃，先区分“通知失败”和“业务失败”
- 发现假数据、默认值、硬编码回流，要优先视为高优先级问题
- 任何自动调参逻辑都不能绕过 `runtime_guardrails`
- 对交易相关异常，宁可保守停手，也不要凭猜测继续执行

## 八、最小交接集合

新接手时，至少阅读这些文件：

- `docs/STOCK_TEAM_HANDOFF_2026-03-25.md`
- `docs/REFACTOR_PHASE10_2026-03-26.md`
- `docs/REFACTOR_PHASE11_2026-03-26.md`
- `docs/REFACTOR_PHASE12_2026-03-26.md`
- `docs/REFACTOR_PHASE13_2026-03-26.md`
- `docs/REFACTOR_PHASE14_2026-03-26.md`
- `docs/REFACTOR_PHASE16_2026-04-10.md`
- `config/runtime_guardrails.json`
- `core/runtime_guardrails.py`
- `core/fundamentals.py`
- `core/simulated_execution.py`

一句话总结：

- 先看 cron
- 再看 Dashboard
- 再看 guardrails / self_healing / simulated_orders
- 异常时优先保守，不要硬跑自动买入
