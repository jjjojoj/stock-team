# Phase 12 - Dashboard Autopilot Upgrade

Date: 2026-03-26

## Goal

把 Dashboard 从“状态展示面板”再往前推一步，变成更适合 OpenClaw 长期值守的托管驾驶舱。

重点不是增加更多图表，而是让系统直接回答：

- 现在是不是模拟托管模式
- 当前能不能放心全自动跑
- 哪些 guardrails 在报警
- 哪些关键输入已经过期

## What Changed

### 1. 监控页新增 Autopilot 摘要

- 文件: `web/dashboard_v3.py`

新增内容：

- 托管模式识别：当前默认识别为“模拟托管”
- 自动运行评级：`全自动模拟 / 受控自动 / 只读托管 / 需人工介入`
- Guardrail 事件计数
- 数据新鲜度统计

结果：

- 不需要翻日志，也能直接看到当前是不是适合继续全自动运行

### 2. 监控页新增 Guardrails 可视化

- 文件: `web/dashboard_v3.py`

新增展示：

- `force_read_only` 状态
- 当前 `confidence_threshold`
- 活跃学习调参次数
- 最近回滚信息
- 最近 Guardrail 事件列表

结果：

- Dashboard 已经能直接反映 Phase 11 的运行护栏，而不是只有后端逻辑存在

### 3. 新增关键输入新鲜度展示

- 文件: `web/dashboard_v3.py`

当前展示：

- `daily_search`
- `predictions`
- `fundamental_snapshot`
- `stock_pool`

每项都会标记：

- 新鲜
- 接近过期
- 已过期 / 缺失

结果：

- 以后判断“是不是该继续自动跑”，可以先看输入是否健康，而不是只看 cron 有没有报错

### 4. 自动托管检查与关键任务结合

- 文件: `web/dashboard_v3.py`

现在 Dashboard 会综合：

- guardrails 评估结果
- 关键 cron 任务状态
- 观察池 / 活跃预测 / 可用现金
- 最近 guardrail warnings / errors

结果：

- 面板对“自动买入是否适合继续”“是否需要人工介入”的判断更接近操作员视角

## Validation

执行通过：

- `python3 -m py_compile web/dashboard_v3.py tests/test_dashboard_v3.py`
- `python3 -m unittest tests.test_dashboard_v3 tests.test_enhanced_cron_handler`

新增验证：

- `tests/test_dashboard_v3.py` 现在会检查 monitoring snapshot 是否包含 autopilot / guardrails 摘要

## Bottom Line

这轮之后，Dashboard 的定位更准确了：

- 以前：展示系统发生了什么
- 现在：展示系统现在适不适合继续全自动模拟托管
