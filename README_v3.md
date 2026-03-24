# AI 股票团队 - 统一标准文档 v3.1

**版本**: v3.1  
**更新时间**: 2026-03-25  
**状态**: ✅ 当前最新版本

---

## 🎯 系统架构（v3.0）

### 核心 Cron 任务（7个）

| 任务 | 时间 | 脚本 | 状态 | 功能 |
|------|------|------|------|------|
| **早盘预测** | 09:00 | `ai_predictor.py` | ✅ 启用 | 分析持仓和自选股，生成今日预测 |
| **午盘更新** | 13:00 | `ai_predictor.py --update` | ✅ 启用 | 根据午盘走势调整预测 |
| **盘后复盘** | 15:30 | `daily_review_closed_loop.py` | ✅ 启用 | 验证今日预测，记录对错 |
| **规则验证/晋升** | 16:00 | `rule_validator.py validate` | ✅ 启用 | 统一验证规则库与验证池，自动晋升/淘汰 |
| **深度学习** | 20:00 | `daily_book_learning.py` | ✅ 启用 | 从投资书籍中提取规则 |
| **新闻监控** | 09:30, 11:00, 14:00 | `news_monitor.py check` | ⚠️ 禁用 | 监控重要新闻（待实现 check 命令）|
| **每周总结** | 周日 20:00 | `weekly_summary.py` | ✅ 启用 | 总结本周表现 |

**调度器状态**：
- 唯一控制面：`OpenClaw cron`
- 查看状态：`python3 scripts/scheduler.py status`
- 查看任务：`python3 scripts/scheduler.py list --json`
- 立即执行：`python3 scripts/scheduler.py run <job_id>`

**验证/观察相关 API**：
- `GET /api/rules`
- `GET /api/validation-pool`
- `GET /api/watchlist`
- `GET /api/validation-summary`

---

## 📊 数据源统一标准（v3.0）

### 1. SQLite 数据库

**路径**: `database/stock_team.db`

**核心表（11个）**：

| 表名 | 用途 | 关键字段 | 更新频率 |
|------|------|----------|----------|
| `positions` | 持仓记录 | symbol, shares, cost_price, current_price | 实时 |
| `account` | 账户信息 | total_asset, cash, market_value | 每日 |
| `proposals` | 交易提案 | symbol, direction, thesis, status | 按需 |
| `quant_analysis` | 量化分析 | symbol, ma5/10/20/60, macd, kdj, rsi | 按需 |
| `risk_assessment` | 风险评估 | symbol, risk_level, suggested_position | 按需 |
| `trades` | 交易记录 | symbol, direction, shares, price | 按需 |
| `watchlist` | 监控列表 | symbol, name, reason, target_price | 按需 |
| `agent_logs` | Agent 日志 | agent, event_type, event_data | 实时 |
| `market_cache` | 市场缓存 | symbol, price, change_pct, pe, pb | 每日 |
| `triggers` | 触发器 | name, condition_type, action_agent | 按需 |
| `backtest_results` | 回测结果 | symbol, strategy, return_pct | 按需 |

**数据标准**：
- ✅ 所有金额使用 **REAL** 类型（单位：元）
- ✅ 所有百分比使用 **REAL** 类型（0-100）
- ✅ 所有时间使用 **TIMESTAMP** 类型（ISO 8601）
- ✅ JSON 字段使用 **JSON** 类型

---

### 2. JSON 数据文件

#### learning/ 目录（12个文件）

**核心文件**：

| 文件名 | 用途 | 核心字段 | 更新频率 |
|--------|------|----------|----------|
| `accuracy_stats.json` | 预测准确率 | total_predictions, correct, partial, wrong, by_rule | 每日 |
| `prediction_rules.json` | 规则库镜像 | SQLite `prediction_rules` 表的 JSON 兼容导出 | 按需 |
| `rule_validation_pool.json` | 验证池镜像 | SQLite `rule_validation_pool` 表的 JSON 兼容导出 | 按需 |
| `book_knowledge.json` | 书籍学习 | book_001/002/003（title, author, key_points） | 每日 |
| `knowledge_base.json` | 知识库 | items（type, source, title, content） | 按需 |
| `daily_learning_log.json` | 学习日志 | 日志数组（timestamp, type, content） | 每日 |
| `team_health.json` | 团队健康 | weekly_reports, issues, improvements | 每周 |
| `experience_library.json` | 经验库 | 经验对象 | 按需 |
| `rule_evolution_history.json` | 规则演进 | 历史记录 | 按需 |
| `rejected_rules.json` | 拒绝规则 | 被拒绝的规则 | 按需 |
| `rule_stats.json` | 规则统计 | 统计数据 | 每日 |
| `book_learning_progress.json` | 学习进度 | 进度记录 | 每日 |

**数据标准**：
- ✅ 所有 JSON 使用 **UTF-8** 编码
- ✅ 所有时间戳使用 **ISO 8601** 格式
- ✅ 所有 ID 使用 **snake_case** 命名
- ✅ 所有状态使用 **英文小写**（pending, validated, rejected）

---

#### data/ 目录（27个文件）

**核心文件**：

| 文件名 | 用途 | 更新频率 |
|--------|------|----------|
| `predictions.json` | 预测记录 | 每日 |
| `alerts.json` | 警报记录 | 实时 |
| `market_data_*.json` | 市场数据 | 每日 |
| `stock_info_*.json` | 股票信息 | 按需 |

---

### 3. 配置文件

#### config/ 目录

| 文件名 | 用途 | 核心内容 |
|--------|------|----------|
| `positions.json` | 持仓配置 | 当前持仓 |
| `watchlist.json` | 自选股镜像 | SQLite `watchlist` 表的 JSON 兼容导出 |
| `api_config.json` | API 配置 | 所有 API key |
| `strategy.md` | 策略文档 | 投资策略 |

---

## 🤖 Agents 团队（6个）

| Agent | 角色 | 职责 | KPI |
|--------|------|------|-----|
| **CIO** | 首席投资官 | 最终决策、仓位控制、风险管理 | 月收益 ≥5%, 回撤 ≤15%, 夏普 ≥1.5 |
| **Quant** | 量化分析师 | 选股模型、因子监控、策略回测 | 胜率 ≥60%, 月收益 ≥8% |
| **Trader** | 交易员 | 执行交易、择时优化、滑点控制 | 成交率 ≥95%, 滑点 ≤0.5% |
| **Risk** | 风控官 | 风险监控、止损执行、合规审查 | 预警准确 ≥80%, 止损执行 100% |
| **Researcher** | 研究员 | 行业研究、公司调研、信息收集 | 报告准确 ≥70% |
| **Learning** | 学习系统 | 书籍学习、实战总结、规则提取 | 规则通过 ≥50% |

---

## 📚 规则系统（v3.0）

### 规则库结构

```json
{
  "direction_rules": {
    "rule_id": {
      "condition": "条件描述",
      "prediction": "预测内容",
      "confidence_boost": 5,
      "source": "来源",
      "samples": 0,
      "success_rate": 0.0,
      "created_at": "ISO 8601"
    }
  },
  "magnitude_rules": {...},
  "timing_rules": {...},
  "confidence_rules": {...}
}
```

**当前规则数量**：
- 方向规则：6 条
- 幅度规则：3 条
- 时机规则：4 条
- 置信度规则：3 条
- **总计**：16 条已建立规则

### 验证池结构

```json
{
  "rule_id": {
    "rule": "规则内容",
    "testable_form": "可验证形式",
    "category": "分类",
    "source": "来源（书籍/实战）",
    "source_book": "书名（如果是书籍）",
    "status": "validating/verified/rejected",
    "confidence": 0.5,
    "live_test": {
      "samples": 0,
      "success_rate": 0.0
    },
    "created_at": "ISO 8601",
    "auto_generated": false,
    "experience_based": false
  }
}
```

**当前验证池**：15+ 条待验证规则

---

## 🔧 关键脚本说明（v3.0）

### 1. 调度器

**路径**: `scripts/scheduler.py`

**功能**：
- 管理 7 个 Cron 任务
- 记录执行状态
- 自动重启失败任务

**命令**：
```bash
python3 scripts/scheduler.py start   # 启动
python3 scripts/scheduler.py stop    # 停止
python3 scripts/scheduler.py status  # 状态
```

---

### 2. AI 预测器

**路径**: `scripts/ai_predictor.py`

**功能**：
- 早盘预测（09:00）
- 午盘更新（13:00）
- 生成买卖信号

**命令**：
```bash
python3 scripts/ai_predictor.py              # 早盘预测
python3 scripts/ai_predictor.py --update     # 午盘更新
```

---

### 3. 盘后复盘

**路径**: `scripts/daily_review_closed_loop.py`

**功能**：
- 验证今日预测
- 记录对错
- 学习提升

**命令**：
```bash
python3 scripts/daily_review_closed_loop.py
```

---

### 4. 规则晋升

**路径**: `scripts/rule_promotion.py`

**功能**：
- 检查验证池
- 晋升成熟规则（样本 ≥ 3，胜率 ≥ 50%）

**命令**：
```bash
python3 scripts/rule_promotion.py
```

---

### 5. 深度学习

**路径**: `scripts/daily_book_learning.py`

**功能**：
- 读取投资书籍
- 提取可验证规则
- 添加到验证池

**命令**：
```bash
python3 scripts/daily_book_learning.py
```

---

## 📊 监控面板（v1.0）

**路径**: `web/dashboard_claude.py`

**端口**: 8082

**访问**: http://127.0.0.1:8082/

**功能**：
- 6 个 Tab 页面（概览/Agents/规则/验证/知识/日志）
- 8 个 API 端点
- 实时数据刷新（30秒）
- 响应式设计

**启动**：
```bash
cd ~/.openclaw/workspace/china-stock-team/web
python3 dashboard_claude.py
```

---

## ⚠️ 已废弃功能

### 新闻监控（待修复）

**问题**：`news_monitor.py` 不支持 `check` 命令

**临时方案**：已禁用

**TODO**：实现 `check` 命令（自动抓取新闻并分析）

---

## 📝 数据流转图

```
┌─────────────────┐
│   Scheduler     │
│  (scheduler.py) │
└────────┬────────┘
         │
         ├─ 09:00 ─→ ai_predictor.py ─→ predictions.json
         │                                ↓
         ├─ 13:00 ─→ ai_predictor.py ─→ predictions.json
         │                                ↓
         ├─ 15:30 ─→ daily_review_closed_loop.py
         │              ↓
         │         验证预测 ─→ accuracy_stats.json
         │              ↓
         │         提取规则 ─→ rule_validation_pool.json
         │
         ├─ 16:00 ─→ rule_promotion.py
         │              ↓
         │         晋升规则 ─→ prediction_rules.json
         │
         └─ 20:00 ─→ daily_book_learning.py
                        ↓
                   学习书籍 ─→ book_knowledge.json
                        ↓
                   提取规则 ─→ rule_validation_pool.json
```

---

## 🔍 故障排查

### 1. Scheduler 未运行

```bash
# 检查状态
cat .scheduler.state

# 检查 PID
ps aux | grep scheduler

# 重启
python3 scripts/scheduler.py restart
```

### 2. 数据不一致

```bash
# 检查数据库
sqlite3 database/stock_team.db "SELECT * FROM positions;"

# 检查 JSON
cat learning/accuracy_stats.json | python3 -m json.tool

# 验证数据源
python3 scripts/validate_data.py
```

### 3. 预测失败

```bash
# 查看日志
tail -100 logs/morning_prediction_*.log

# 手动运行
python3 scripts/ai_predictor.py
```

---

## 📚 相关文档

- **旧版 README**：`README.md`（v2.1，已过时）
- **团队章程**：`TEAM_CHARTER.md`
- **实时交易**：`REAL_TRADING_ENV.md`
- **框架说明**：`learning/FRAMEWORK.md`
- **API 配置**：`~/.openclaw/workspace/docs/API_CONFIG.md`

---

## 🎯 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-02-14 | 初始版本 |
| v2.0 | 2026-02-28 | 添加学习系统 |
| v2.1 | 2026-03-10 | 添加新闻监控 |
| **v3.0** | **2026-03-14** | **统一标准，清理混乱数据** |

---

**这是当前唯一标准文档。所有旧版本已废弃。**

*最后更新：2026-03-14 20:20*
