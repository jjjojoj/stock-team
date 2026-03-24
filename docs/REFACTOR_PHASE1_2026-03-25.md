# 重构记录 - Phase 1

**日期**: 2026-03-25  
**分支**: `codex/refactor-phase1-core-data`

## 本阶段目标

第一阶段聚焦 4 个高优先级目标：

1. 抽离公共路径和同步逻辑，减少硬编码路径。
2. 统一预测生命周期和验证结果结构。
3. 让预测和持仓更稳定地同步到 `stock_team.db`。
4. 为本轮核心改动补最小可用测试。

---

## 新增模块

### `core/predictions.py`

新增预测生命周期公共逻辑：

- 统一 `timeframe -> due_at`
- 统一 `result` 结构
- 兼容旧格式 `incorrect/correct/partial`
- 统一 `rules_used` / `matched_rules`
- 提供 `apply_prediction_verdict()` 等通用方法

### `core/storage.py`

新增共享存储层：

- 统一项目路径常量
- 统一 JSON 读写
- 提供 `sync_predictions_to_db()`
- 提供 `sync_positions_and_account_to_db()`

### `core/__init__.py`

导出常用 helper，方便脚本侧复用。

---

## 主要修改

### 1. 预测系统重构

修改文件：

- `scripts/prediction_system.py`
- `scripts/daily_review_closed_loop.py`
- `scripts/rule_validator.py`

关键变化：

- `PredictionSystem.make_prediction()` 改为通过公共构造器创建预测。
- 活跃预测加载时统一做 normalize，兼容旧数据。
- 到期验证改为按 `timeframe/due_at` 执行，不再混用多套标准。
- 验证结果统一为：
  - `correct`
  - `partial`
  - `wrong`
  - `pending`
  - `expired`
- 预测保存时自动同步数据库，Dashboard 与 JSON 的偏差显著降低。
- `RuleValidator` 改为同时兼容 `rules_used` 和旧版 `matched_rules`。

### 2. 持仓与账户同步重构

修改文件：

- `scripts/auto_trader_v3.py`
- `scripts/sync_positions.py`

关键变化：

- 抽出共享同步逻辑，去掉重复的 DB 同步代码。
- 账户汇总改为按 `current_price` 计算市值，而不是继续按成本价估值。
- 同步时同时刷新 `positions` 和 `account` 表。
- 修复单日亏损风控判断里只累计正值的问题，改为正确累计亏损。

### 3. 路径硬编码收敛

修改文件：

- `scripts/ai_predictor.py`
- `scripts/price_report.py`
- `web/dashboard_v3.py`

关键变化：

- 主入口脚本改为基于 `Path(__file__).resolve()` 推导项目根目录。
- Dashboard 不再写死 `/Users/joe/.../stock_team.db`。
- 价格汇报脚本切到动态 webhook 读取，并修正发送时固定用旧变量的问题。

### 4. 测试补充

新增文件：

- `tests/test_prediction_utils.py`
- `tests/test_storage_sync.py`

覆盖内容：

- 预测 `due_at` 计算
- 预测 verdict 状态归一化
- 预测同步到数据库
- 持仓/账户同步到数据库

---

## 验证记录

执行命令：

```bash
python3 -m compileall core scripts/prediction_system.py scripts/daily_review_closed_loop.py scripts/rule_validator.py scripts/auto_trader_v3.py scripts/sync_positions.py scripts/ai_predictor.py scripts/price_report.py web/dashboard_v3.py

python3 -m unittest tests.test_prediction_utils tests.test_storage_sync
```

结果：

- `compileall` 通过
- `5` 个单元测试全部通过

---

## 这轮未完成的内容

以下内容保留到下一阶段：

1. 完整把 `watchlist/rules/validation_pool` 迁到数据库主写。
2. 合并 `rule_validation.py` 与 `rule_validator.py` 两套规则验证入口。
3. 让 OpenClaw cron 成为唯一调度控制面，并正式退役旧 `scheduler.py`。
4. 收敛历史 Dashboard 入口（`web_dashboard.py` / 模板版 / v3 版）。

---

## 本阶段收益

- 预测“何时验证、如何记结果”终于统一了。
- Dashboard 的预测表和持仓/账户表开始稳定吃到最新同步数据。
- 新机器或新目录运行时，核心入口不再强依赖固定绝对路径。
- 后续继续做 DB 单一真源重构时，已经有公共层可以接着扩展。
