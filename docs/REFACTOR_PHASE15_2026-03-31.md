# REFACTOR PHASE 15 - Proposal Pipeline & Agent Handoffs

日期：2026-03-31

## 本轮目标

把股票团队从“多角色脚本集合”继续推进到“围绕统一提案状态机协作的多 agent 一人公司”。

这轮不是继续堆新脚本，而是把真正的协作主线收口到 `proposal` 流水线，并且把之前那笔验证性模拟买入正式撤回，恢复到新的 20 万模拟基线。

## 本轮完成内容

### 1. 撤回验证性模拟买入，回到新账本基线

已确认当前账本基线为：

- 总资产：`¥200,000`
- 可用现金：`¥200,000`
- 持仓：`0`
- 模拟订单：`0`
- 模拟成交：`0`

说明：

- 2026-03-31 的那笔“验证交易链是否可成交”的模拟买单已经撤回
- 当前系统应视为“从 2026-03-31 重新开始记录模拟盘”
- 旧账本已归档到 `data/ledger_archives/`

### 2. 新增统一 proposal pipeline 层

新增：

- `core/proposals.py`

核心能力：

- 创建/刷新 Research 提案
- 记录 Quant 验证结果
- 记录 Risk 评估
- 记录 CIO 审批结果
- 记录 Trader 执行结果
- 汇总提案状态统计与最近交接记录

当前正式状态流：

`pending -> quant_validated -> risk_checked -> approved -> executed`

终止状态：

- `rejected`
- `cancelled`

### 3. Research 现在会正式提交提案

更新：

- `scripts/daily_stock_research.py`

改动：

- 研究日报不再只是“写 watchlist + 发飞书”
- 现在会同步创建/刷新 `Research` 提案
- 提案中会带上：
  - 研究评分
  - 目标价 / 止损价
  - 行业
  - 研究理由
  - 基本面来源

另外补回了：

- `StockResearcher` 类

这样旧的协调器和新主链终于对齐，不再是“文档里有 Research agent，代码里没有真正 agent facade”。

### 4. Quant 现在会把预测挂回提案

更新：

- `scripts/ai_predictor.py`

改动：

- 量化预测生成后，会尝试把预测结果同步到对应的开放提案
- 同步内容包括：
  - 方向
  - 置信度
  - 目标价
  - 使用规则
  - 技术评分
  - RSI / MACD / KDJ 简化状态

重要修复：

- 如果提案已经进入 `risk_checked / approved / executed`
- Quant 重跑不会把提案状态倒退回 `quant_validated`

### 5. Trader 现在只执行正式审批链

更新：

- `scripts/auto_trader_v3.py`

买入主链已从：

- `watchlist + active predictions -> 直接买入`

切换为：

- `proposal pipeline -> 风控评估 -> CIO 审批 -> Trader 执行`

现在的买入逻辑：

1. 仅读取 `quant_validated / risk_checked / approved` 提案
2. 对 `quant_validated` 提案补风控评估
3. CIO 根据研究评分、量化置信度、风险结果和预期收益空间审批
4. 只有 `approved` 提案才会真正进入模拟执行层
5. 成交后把 proposal 标记为 `executed`

补充修复：

- 若买入信号已完成风控，则不会重复写风控评估
- 成交后会尝试把 `trades.proposal_id` 回填到对应订单

### 6. Dashboard 补上多 agent 交接可视化

更新：

- `web/dashboard_v3.py`

交易执行页新增：

- `pending / quant_validated / risk_checked / approved` 数量
- 多 agent 流水线摘要
- 最近交接记录（Research / Quant / Risk / CIO / Trader）

这意味着现在不只是“系统内部有状态流”，面板上也能直接看到这条协作链是不是在动。

### 7. 新增 proposal pipeline 命令入口

新增：

- `scripts/proposal_pipeline.py`

可用命令：

```bash
python3 scripts/proposal_pipeline.py status
python3 scripts/proposal_pipeline.py advance
```

用途：

- `status`：看当前 proposal 状态统计与最近交接
- `advance`：推进到当前可审批阶段，并输出已批准候选

### 8. Team Coordinator 与现状对齐

更新：

- `scripts/team_coordinator.py`

改动：

- 不再打印一套脱离真实账本的 CIO 虚拟决策
- 现在会基于真实 proposal pipeline 展示：
  - 研究提案
  - 量化验证
  - 当前状态流统计
  - 当前已批准候选

## 影响

本轮之后，股票团队更接近：

- 研究员负责生成提案
- 量化师负责验证提案
- 风控官负责打风险标签
- CIO 负责批准/驳回
- 交易员只执行已批准提案

也就是说：

- 角色不再只是“命名上的人格”
- 而是逐步变成“数据库里可审计的正式交接链”

## 验证

已通过：

```bash
python3 -m py_compile core/proposals.py scripts/daily_stock_research.py scripts/ai_predictor.py scripts/auto_trader_v3.py scripts/team_coordinator.py scripts/proposal_pipeline.py web/dashboard_v3.py
python3 -m unittest tests.test_proposals tests.test_auto_trader_v3 tests.test_dashboard_v3 tests.test_real_data_paths
python3 scripts/proposal_pipeline.py status
```

验证结果：

- proposal lifecycle 测试通过
- auto trader 现在会从正式 proposal pipeline 生成买入候选
- dashboard 交易页现在能返回 proposal pipeline 摘要
- 当前基线账本仍保持 `20 万 / 空仓 / 0 成交`

## 给后续接手者的约定

从这轮开始，若要判断“系统是不是多 agent 协作”，不要再只看：

- `TEAM_CHARTER.md`
- 各种 agent 的 `SOUL.md`

而应该优先看：

- `core/proposals.py`
- `database/stock_team.db` 的 `proposals / quant_analysis / risk_assessment / agent_logs`
- `scripts/auto_trader_v3.py` 的买入执行入口
- dashboard 交易页里的 proposal pipeline 状态

一句话总结：

这轮把股票团队从“多角色脚本系统”又往前推了一步，开始真正具备“可审计的多 agent 公司式交接链”。
