# AI 股票团队 - 数据统一标准 v3.1

**版本**: v3.1  
**更新时间**: 2026-03-15 00:00  
**状态**: ✅ 当前唯一标准

---

## 🎯 核心原则

**单一数据源**：所有数据统一存储在 `database/stock_team.db`

**禁止**：
- ❌ 创建新的数据库
- ❌ 在多个地方存储相同数据
- ❌ 不经过同步直接修改 JSON 文件

---

## 📊 数据源层级

### 主数据源（唯一真实）

| 数据库 | 路径 | 用途 | 更新方式 |
|--------|------|------|----------|
| **stock_team.db** | `database/stock_team.db` | 所有核心数据 | Cron 任务自动更新 |

### 辅助配置（只读）

| 文件 | 路径 | 用途 | 说明 |
|------|------|------|------|
| **positions.json** | `config/positions.json` | 初始持仓配置 | 买入时手动更新 |
| **watchlist.json** | `config/watchlist.json` | 自选股 JSON 镜像（主数据在 SQLite `watchlist`） | 兼容导出 |

### 历史记录（只写）

| 目录 | 用途 | 说明 |
|------|------|------|
| `data/predictions.json` | 预测历史 | 自动追加 |
| `learning/*.json` | 学习记录 | 自动追加 |
| `logs/*.log` | 运行日志 | 自动生成 |

---

## 🔄 数据同步规则

### 自动同步（Cron 任务）

| 任务 | 时间 | 更新内容 |
|------|------|----------|
| **早盘预测** | 09:00 | 更新 positions, account |
| **午盘更新** | 13:00 | 更新实时价格 |
| **盘后复盘** | 15:30 | 验证预测，更新准确率 |
| **规则晋升** | 16:00 | 更新 prediction_rules |
| **深度学习** | 20:00 | 更新 rule_validation_pool |

### 手动同步（买入/卖出）

**买入流程**：
1. 修改 `config/positions.json`（添加新持仓）
2. 运行同步脚本：`python3 scripts/sync_positions.py`
3. 验证：访问 http://127.0.0.1:8082/api/overview

**卖出流程**：
1. 修改 `config/positions.json`（移除持仓）
2. 运行同步脚本：`python3 scripts/sync_positions.py`
3. 更新 account 表（减少持仓数）

---

## 📐 数据库表结构标准

### 核心表（11个）

| 表名 | 用途 | 更新频率 | 关键字段 |
|------|------|---------|---------|
| **positions** | 持仓记录 | 实时 | symbol, shares, cost_price, current_price |
| **account** | 账户信息 | 每日 | total_asset, cash, market_value, total_profit |
| **proposals** | 交易提案 | 按需 | symbol, direction, thesis, status |
| **trades** | 交易记录 | 按需 | symbol, direction, shares, price |
| **watchlist** | 监控列表 | 按需 | symbol, name, reason |
| **quant_analysis** | 量化分析 | 按需 | symbol, ma5/10/20/60, macd, rsi |
| **risk_assessment** | 风险评估 | 按需 | symbol, risk_level, suggested_position |
| **agent_logs** | Agent日志 | 实时 | agent, event_type, event_data |
| **market_cache** | 市场缓存 | 每日 | symbol, price, change_pct |
| **triggers** | 触发器 | 按需 | name, condition_type, action_agent |
| **backtest_results** | 回测结果 | 按需 | symbol, strategy, return_pct |

---

## 🔧 仪表盘配置

### 数据读取

**唯一数据源**：`database/stock_team.db`

**API 端点**：
```
GET /api/overview      # 概览数据（从 stock_team.db 读取）
GET /api/agents        # Agent 数据（硬编码）
GET /api/cron          # Cron 任务（从 OpenClaw cron 实时读取）
GET /api/rules         # 规则库（从 SQLite `prediction_rules` / JSON 镜像读取）
GET /api/validation-pool # 验证池（从 SQLite `rule_validation_pool` / JSON 镜像读取）
GET /api/knowledge     # 知识库（从 learning/knowledge_base.json 读取）
```

**实时股价**：
- API：`http://qt.gtimg.cn/q={symbol}`
- 格式：`sz.000792`（不是 `000792.SZ`）

---

## 📝 版本管理规范

### 修改流程

**任何数据结构修改**：
1. 先更新本文档（`DATA_STANDARD.md`）
2. 创建迁移脚本（`scripts/migrate_v3_to_v4.py`）
3. 备份数据库（`cp stock_team.db stock_team.db.backup`）
4. 执行迁移
5. 更新仪表盘代码（`web/dashboard_claude.py`）
6. 测试验证

**禁止**：
- ❌ 直接修改数据库结构（不经文档）
- ❌ 修改表字段名（破坏兼容性）
- ❌ 创建重复表（如 positions_v2）

---

## 🚨 常见问题

### Q1: 推送消息和仪表盘数据不一致？

**原因**：数据源不统一

**解决**：
1. 检查 `config/positions.json`
2. 运行同步脚本：`python3 scripts/sync_positions.py`
3. 验证仪表盘：http://127.0.0.1:8082/api/overview

### Q2: 数据库多久没更新了？

**检查**：
```bash
sqlite3 database/stock_team.db "SELECT MAX(updated_at) FROM positions;"
sqlite3 database/stock_team.db "SELECT MAX(date) FROM account;"
```

**解决**：
- Scheduler/Cron 异常 → 用 `python3 scripts/scheduler.py status` 或 `openclaw cron list --json` 排查
- Cron 任务失败 → 检查日志：`logs/morning_prediction_*.log`

### Q3: 如何添加新持仓？

**步骤**：
1. 修改 `config/positions.json`：
   ```json
   {
       "sz.000792": {
           "name": "盐湖股份",
           "shares": 800,
           "cost_price": 36.85,
           "status": "holding"
       }
   }
   ```
2. 运行同步：`python3 scripts/sync_positions.py`
3. 验证：访问 http://127.0.0.1:8082/api/overview

---

## 📚 相关文档

- **数据标准**：`DATA_STANDARD.md`（本文档）
- **版本历史**：`README_v3.md`
- **API 文档**：`docs/API_DOCUMENTATION.md`
- **迁移脚本**：`scripts/sync_positions.py`

---

## 🎯 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-02-14 | 初始版本 |
| v2.0 | 2026-02-28 | 添加学习系统 |
| v3.0 | 2026-03-10 | 添加新闻监控 |
| **v3.1** | **2026-03-15** | **数据统一，建立唯一标准** |

---

**这是当前唯一标准文档。所有旧版本已废弃。**

*最后更新：2026-03-15 00:00*
