# Refactor Phase 2 - 2026-03-25

## 目标

第二阶段围绕 3 个问题落地：

1. 合并 `scripts/rule_validation.py` 与 `scripts/rule_validator.py`，收敛为单一规则验证入口。
2. 将 `watchlist / prediction_rules / rule_validation_pool` 进一步迁入 SQLite，并保留 JSON 兼容镜像。
3. 让 OpenClaw cron 成为唯一调度控制面，退役仓库内旧的本地 scheduler 逻辑。

## 本次改动

### 1. 存储层升级

更新文件：

- `core/storage.py`

新增/升级内容：

- 新增 `ensure_storage_tables()`，自动创建或升级以下 SQLite 表：
  - `watchlist`
  - `prediction_rules`
  - `rule_validation_pool`
  - `rejected_rules`
- 为既有 `watchlist` 表补充兼容列：
  - `priority`
  - `stop_loss`
  - `score`
  - `status`
  - `updated_at`
  - `metadata`
- 新增统一读写函数：
  - `load_watchlist()` / `save_watchlist()`
  - `load_rules()` / `save_rules()`
  - `load_validation_pool()` / `save_validation_pool()`
  - `load_rejected_rules()` / `save_rejected_rules()`
- 所有上述函数都采用同一策略：
  - SQLite 作为主账本
  - JSON 作为兼容镜像
  - 若 SQLite 为空，会自动从既有 JSON 引导迁移

### 2. 规则验证入口合并

更新文件：

- `scripts/rule_validator.py`
- `scripts/rule_validation.py`
- `scripts/rule_promotion.py`

具体变更：

- `scripts/rule_validator.py` 重写为统一验证器，单个类同时负责：
  - 规则库样本统计
  - 规则权重调整
  - 规则库淘汰
  - 验证池回测/实盘表现更新
  - 验证池自动晋升
  - 验证池淘汰归档
- 新增命令：
  - `python3 scripts/rule_validator.py validate`
  - `python3 scripts/rule_validator.py validate-library`
  - `python3 scripts/rule_validator.py validate-pool`
  - `python3 scripts/rule_validator.py report`
- `scripts/rule_validation.py` 改为兼容壳，直接转发到 `rule_validator.py`
- `scripts/rule_promotion.py` 改为兼容壳，内部复用统一验证器的验证池逻辑

设计取舍：

- 本轮没有强行统一仓库里所有“规则分类命名体系”。
- 验证池晋升后的规则默认进入 `validated_rules` 分类，避免直接冲撞现有 `direction_rules / magnitude_rules / timing_rules / confidence_rules` 体系。
- 这保证了第二阶段先解决“入口统一”和“状态统一”，不把现有预测链路冒进改坏。

### 3. 业务脚本接入共享存储层

更新文件：

- `scripts/daily_book_learning.py`
- `scripts/daily_stock_research.py`
- `scripts/ai_predictor.py`
- `scripts/stock_pool_manager.py`
- `scripts/rule_evolution.py`
- `scripts/lesson_applier.py`
- `scripts/prediction_engine.py`

接入结果：

- `daily_book_learning.py` 写入验证池时，会同步 SQLite `rule_validation_pool`
- `daily_stock_research.py` 加入观察池时，会同步 SQLite `watchlist`
- `ai_predictor.py` 读取规则库/观察池时，会优先读 SQLite 主账本
- `stock_pool_manager.py` 管理观察池时，会同步 SQLite `watchlist`
- `rule_evolution.py` / `lesson_applier.py` 更新规则库时，会同步 SQLite `prediction_rules`
- `prediction_engine.py` 的规则库和观察池写入也接入了共享存储层

### 4. 调度层收口

更新文件：

- `scripts/scheduler.py`
- `web/enhanced_cron_handler.py`
- `web/dashboard_v3.py`

具体变更：

- `scripts/scheduler.py` 不再维护本地 `SCHEDULE`、PID、状态文件。
- 新版本只做 OpenClaw cron 兼容适配：
  - `status`
  - `list [--json]`
  - `run <job_id>`
- 旧命令 `start/stop/restart/run_once` 现在只返回退役提示
- `web/enhanced_cron_handler.py` 新增真实任务解析：
  - 从 OpenClaw payload 中抽取 `script_key`
  - 给前端返回 `enabled`、`script_key` 等字段
- `web/dashboard_v3.py` 不再使用硬编码时间表推导“今日任务”
  - `get_scheduled_scripts()` 改为直接使用 OpenClaw 实时任务列表
  - `get_cron_status()` 改为直接从 OpenClaw cron 状态映射到卡片

## 验证结果

已执行：

```bash
python3 -m compileall core scripts/rule_validator.py scripts/rule_validation.py scripts/rule_promotion.py scripts/scheduler.py scripts/daily_book_learning.py scripts/daily_stock_research.py scripts/ai_predictor.py scripts/stock_pool_manager.py scripts/rule_evolution.py scripts/lesson_applier.py scripts/prediction_engine.py web/enhanced_cron_handler.py web/dashboard_v3.py

python3 scripts/rule_validator.py report

python3 scripts/scheduler.py status

python3 -m unittest tests.test_prediction_utils tests.test_storage_sync tests.test_rule_storage
```

结果：

- 编译通过
- 统一规则验证报告可运行
- OpenClaw cron 兼容调度器可运行
- 自动化测试通过

## 新增测试

新增文件：

- `tests/test_rule_storage.py`

覆盖内容：

- `watchlist` 的 SQLite/JSON 双写与回读
- `prediction_rules / rule_validation_pool / rejected_rules` 的 SQLite/JSON 双写与回读

## 当前状态

第二阶段完成后：

- 规则验证入口已统一
- 规则库/验证池/观察池已有 SQLite 主账本
- JSON 仍保留，避免旧脚本立刻失效
- 调度控制面正式切换为 OpenClaw cron

## 后续建议

第三阶段建议继续做：

1. 清理仍直接写 JSON 的遗留脚本（如自动规则生成、部分旧 dashboard、部分 review 脚本）
2. 为 `prediction_rules` 与 `rule_validation_pool` 增加 dashboard API 和页面展示
3. 逐步统一规则分类体系，减少 `tech_rules` 与 `direction_rules` 并存的历史包袱
