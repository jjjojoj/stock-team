# Refactor Phase 3 - 2026-03-25

## 目标

第三阶段聚焦两件事：

1. 清理仍直接读写 `watchlist / prediction_rules / rule_validation_pool` JSON 的遗留脚本。
2. 让 dashboard 的验证/观察相关接口和页面，直接显示数据库主账本里的真实状态。

## 本次改动

### 1. 遗留脚本迁移

更新文件：

- `scripts/update_rule_samples.py`
- `scripts/event_analysis/auto_rule_generator.py`
- `scripts/daily_web_search.py`
- `scripts/market_review_v2.py`
- `scripts/news_trigger.py`
- `scripts/a_share_risk_monitor.py`
- `scripts/team_coordinator.py`
- `scripts/team_optimizer.py`
- `scripts/weekly_summary.py`
- `scripts/stock_pool_manager.py`

关键变化：

- `scripts/update_rule_samples.py`
  - 改为兼容壳，直接转发到统一规则验证器。
  - 不再维护独立的“样本更新”逻辑，避免重复累加样本。

- `scripts/event_analysis/auto_rule_generator.py`
  - 自动生成事件规则时，改用 `load_validation_pool()` / `save_validation_pool()`
  - 新生成规则会同步进入 SQLite `rule_validation_pool`，同时保留 JSON 镜像。

- `scripts/daily_web_search.py`
  - 读取观察池时改为通过 `load_watchlist()` 获取，避免绕开数据库主账本。

- `scripts/market_review_v2.py`
  - 复盘时查找观察池理由，改为兼容当前 `watchlist` 字典结构。
  - 避免旧代码按列表结构读取导致“找不到原因”。

- `scripts/news_trigger.py`
  - 新闻影响分析新增观察池股票名识别。
  - 不再只看持仓，观察池股票也会进入受影响集合。

- `scripts/a_share_risk_monitor.py`
  - 自选股加载改为通过 `load_watchlist()`。
  - 修复旧逻辑按 `{"stocks": [...]}` 结构读取的问题。

- `scripts/team_coordinator.py`
  - 启动时加载观察池改为通过 `load_watchlist()`。

- `scripts/team_optimizer.py`
  - 规则库与验证池改为通过 `load_rules()` / `load_validation_pool()` 读取。
  - 自动调权后保存改为 `save_rules()`，同步 SQLite 主账本。

- `scripts/weekly_summary.py`
  - 周总结读取规则库时改为走 `load_rules()`。

- `scripts/stock_pool_manager.py`
  - `list` 子命令改为走 `load_watchlist()`。

### 2. Dashboard 接入真实验证数据

更新文件：

- `web/dashboard_v3.py`

新增后端能力：

- 新增规则与观察池聚合函数：
  - `flatten_rule_library()`
  - `get_watchlist_items()`
  - `get_validation_pool_items()`
  - `get_validation_summary()`

- 新增 API：
  - `GET /api/rules`
  - `GET /api/validation-pool`
  - `GET /api/watchlist`
  - `GET /api/validation-summary`

验证页前端更新：

- `loadValidationData()` 不再显示硬编码占位数字。
- 现在会读取真实数据并显示：
  - 规则验证通过数
  - 淘汰规则数
  - 验证池待验证数
  - 学习知识点数量
  - 热/温/冷记忆分层
  - 规则库 Top 列表
  - 验证池候选列表
  - 样本内 / 样本外准确率估算

## 验证结果

已执行：

```bash
python3 -m compileall scripts/update_rule_samples.py scripts/event_analysis/auto_rule_generator.py scripts/daily_web_search.py scripts/market_review_v2.py scripts/news_trigger.py scripts/a_share_risk_monitor.py scripts/team_coordinator.py scripts/team_optimizer.py scripts/weekly_summary.py web/dashboard_v3.py

python3 - <<'PY'
from web.dashboard_v3 import handle_api_rules, handle_api_validation_pool, handle_api_watchlist, handle_api_validation_summary
print('rules', len(handle_api_rules().get('rules', [])))
print('pool', len(handle_api_validation_pool().get('rules', [])))
print('watchlist', len(handle_api_watchlist().get('watchlist', [])))
summary = handle_api_validation_summary()
print('summary', summary.get('passed_rules'), summary.get('failed_rules'), summary.get('pending_rules'))
PY

python3 -m unittest tests.test_prediction_utils tests.test_storage_sync tests.test_rule_storage
```

验证结果：

- 编译通过
- 新 API 可以返回真实数据
- 单元测试通过

## 当前状态

第三阶段完成后：

- 规则/验证池/观察池的主要在跑脚本，已基本接入共享存储层
- Dashboard 验证页不再是静态占位
- 观察池、规则库、验证池的状态可直接从 HTTP API 获取

## 剩余尾项

仍可继续优化的遗留点：

1. `scripts/web_dashboard.py`、`web/templates/dashboard*.py` 这些旧 dashboard 仍有 JSON 直读逻辑
2. `scripts/collectors/base_collector.py` 等边缘脚本还保留旧文件路径引用
3. 规则分类体系仍存在历史并存问题，尚未做最终统一
