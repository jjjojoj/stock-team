# China Stock Trading Team

基于投资框架的 A 股智能选股与交易系统

**版本**: v2.1  
**更新时间**: 2026-03-10

---

## 🚀 快速开始

```bash
# 进入项目目录
cd ~/.openclaw/workspace/china-stock-team
source venv/bin/activate

# 选股扫描
python3 scripts/selector.py top 5

# 生成研究报告
python3 scripts/research_generator.py sh.600459

# 查看迭代记录
python3 scripts/iteration_logger.py list

# 学习复盘
python3 scripts/learning_engine.py review
```

---

## 📦 核心模块

### 1. 多数据源适配器 ✅

**路径**: `adapters/`

**功能**:
- 🔄 Baostock + AKShare 自动切换
- 🔀 故障自动恢复
- 📊 统一 API 接口

**使用方法**:
```python
from adapters import get_data_manager

dm = get_data_manager()
price = dm.get_realtime_price('sh.600519')
tech = dm.get_technical_indicators('sh.600519')
```

---

### 2. 知识库系统 ✅

**路径**: `knowledge/`

**功能**:
- 📚 向量存储 + 语义搜索
- 🧠 教训/规则/决策/预测分类
- 🔍 相似情况检索

**使用方法**:
```python
from knowledge import get_knowledge_base

kb = get_knowledge_base()
kb.add_lesson(content="追高买入导致亏损", metadata={"stock": "sh.600519"})
results = kb.search("茅台 追高", top_k=5)
```

---

### 3. 新闻搜索 ✅

**路径**: `adapters/news_adapter.py`

**数据源**:
- 新浪财经（免费）
- 东方财富（免费）
- 腾讯财经（免费）

**使用方法**:
```python
from adapters import get_stock_news

news = await get_stock_news("贵州茅台", limit=5)
```

---

## 🛠 核心脚本

| 脚本 | 功能 | 示例 |
|------|------|------|
| `selector.py` | 选股扫描 | `python3 scripts/selector.py top 5` |
| `auto_trader.py` | 自动交易 | `python3 scripts/auto_trader.py scan` |
| `learning_engine.py` | 学习复盘 | `python3 scripts/learning_engine.py review` |
| `research_generator.py` | 研究报告 | `python3 scripts/research_generator.py sh.600459` |
| `iteration_logger.py` | 迭代记录 | `python3 scripts/iteration_logger.py list` |

---

## 📁 文件结构

```
china-stock-team/
├── adapters/              # 数据源适配器
│   ├── base.py
│   ├── baostock_adapter.py
│   ├── akshare_adapter.py
│   ├── manager.py
│   └── news_adapter.py
├── knowledge/             # 知识库
│   ├── knowledge_base.py
│   └── vectors/
├── scripts/               # 核心脚本
│   ├── selector.py
│   ├── auto_trader.py
│   ├── learning_engine.py
│   ├── research_generator.py
│   └── iteration_logger.py
├── agents/                # Agent 定义
│   ├── cio/SOUL.md
│   ├── quant/SOUL.md
│   ├── researcher/SOUL.md
│   ├── risk/SOUL.md
│   └── trader/SOUL.md
├── config/                # 配置文件
│   ├── crontab.txt        # Cron 任务配置
│   └── api_config.json
├── learning/              # 学习记录
│   ├── iterations/        # 迭代记录
│   ├── memory.md          # 热层记忆
│   └── patterns.md        # 温层模式
├── data/                  # 数据文件
├── logs/                  # 日志
└── web/                   # Web 看板
```

---

## 🔄 迭代记录

所有系统更新都会记录到知识库和 `learning/iterations/` 目录。

```bash
# 查看迭代历史
python3 scripts/iteration_logger.py list

# 记录新迭代
python3 scripts/iteration_logger.py record \
  --type "策略更新" \
  --desc "描述" \
  --before "之前" \
  --after "之后" \
  --reason "原因"
```

---

## ⚙️ Cron 任务

**配置文件**: `config/crontab.txt`

**安装方法**:
```bash
crontab -e
# 粘贴 config/crontab.txt 中的内容
```

**主要任务**:
- 09:00 - 开盘前新闻搜索
- 15:00 - 收盘后扫描
- 21:00 - 学习复盘

---

## 📊 核心功能

### 1. 多维度分析系统 ✅

**文档**：`docs/multi_dimension_analysis.md`

**分析维度**：
- 🌍 **国际形势**（25%）：战争、制裁、贸易战、汇率
- 📊 **经济周期**（20%）：GDP、CPI、PMI、失业率
- 📜 **政策环境**（20%）：财政、货币、产业、监管
- 😰 **市场情绪**（15%）：成交量、涨跌停、资金流向
- 🏭 **行业周期**（10%）：商品价格、库存、产能
- 💰 **流动性**（10%）：M2、利率、信用利差

**使用方法**：
```bash
# 查看风险评级报告
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/risk_assessment.py report
```

---

### 2. 新闻监控系统 ✅

**工具**：`scripts/news_monitor.py`

**功能**：
- 📰 多源新闻聚合
- 🔍 自动事件分类
- 📈 影响分析（受益/受损板块）
- 💡 操作建议

**支持的事件类型**：
- 战争/冲突
- 制裁/贸易战
- 政策变化
- 经济数据
- 行业动态
- 公司新闻

**使用方法**：
```bash
# 测试新闻分析（美伊战争）
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/news_monitor.py test

# 分析自定义新闻
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/news_monitor.py analyze "美国对伊朗发动军事打击"
```

**案例：美伊战争分析**：
```
✅ 受益板块：军工、黄金、石油、战略金属、稀土
✅ 受益股票：中航沈飞、北方稀土、紫金矿业、中国石油
❌ 受损板块：物流、航空、旅游
❌ 受损股票：中远海控、中国国航
```

---

### 3. 风险评级系统 ✅

**工具**：`scripts/risk_assessment.py`

**风险等级**：
| 等级 | 分数 | 操作建议 |
|-----|------|---------|
| 🟢 极低 | 0-20 | 满仓操作 |
| 🟢 低 | 20-40 | 积极建仓 |
| 🟡 中 | 40-60 | 观望为主 |
| 🟠 高 | 60-80 | 减仓避险 |
| 🔴 极高 | 80-100 | 空仓 |

**当前市场风险**：
- 🟡 综合评分：47.5/100
- 🔴 高风险因子：国际形势（75/100）
- 💡 操作建议：仓位 40-60%，精选个股

---

### 4. 实时盯盘工具 ✅

**工具**：`scripts/realtime_monitor.py`

**功能**：
- 💼 持仓监控（盈亏、目标价、止损）
- 👀 自选股监控
- ⚠️ 异动预警（涨跌幅、成交量、破位）
- 🔄 持续监控（每15分钟刷新）

**使用方法**：
```bash
# 监控持仓
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/realtime_monitor.py positions

# 监控自选股
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/realtime_monitor.py watchlist

# 持续监控（每15分钟）
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/realtime_monitor.py continuous
```

**预警类型**：
- 📈 涨跌幅超过 3%
- 📊 成交量超过 1.5 倍
- 🎯 到达目标价
- ⚠️ 触发止损
- 📈 创新高/新低

---

### 5. 选股系统 ✅

**工具**：`scripts/selector_v3.py`

**筛选条件**：
- **硬筛选**（必须满足）：
  - 实控人：央企/省国资委/市国资委
  - 市值 < 200亿

- **软筛选**（加分项）：
  - PB < 2.5（估值）
  - ROE > 10%（盈利能力）
  - 净利润增长 > 20%（成长性）
  - 股息率 > 1%（分红）
  - 技术评分 > 60（技术面）

**使用方法**：
```bash
# 扫描股票池
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/selector_v3.py scan

# 显示最值得关注的 5 只股票
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/selector_v3.py top 5
```

**当前筛选结果**：
| 排名 | 股票 | 综合评分 | 技术评分 |
|-----|------|---------|---------|
| 1 | 宝地矿业 | 100/100 | 85/100 |
| 1 | 贵研铂业 | 95/100 | 70/100 |
| 3 | 中色股份 | 75/100 | 80/100 |

---

### 6. 商品价格跟踪 ✅

**工具**：`scripts/commodity_tracker.py`

**跟踪商品**：
- 铜（LME + 上期所）
- 铝（LME + 上期所）
- 锂（SMM 上海有色网）
- 稀土（北方稀土挂牌价）

**周期位置判断**：
- 🟢 底部（0-20%）：历史低位，买入机会
- 🟢 低位（20-40%）：相对低位，可分批建仓
- 🟡 中位（40-60%）：价格适中，观望为主
- 🟠 高位（60-80%）：价格偏高，谨慎操作
- 🔴 顶部（80-100%）：历史高位，考虑减仓

**当前商品周期**：
| 商品 | 价格 | 周期位置 | 建议 |
|-----|------|---------|------|
| 铜 | ¥74,500/吨 | 🟠 高位 (87.8%) | 谨慎操作 |
| 铝 | ¥18,600/吨 | 🟠 高位 (57.3%) | 谨慎操作 |
| 锂 | ¥98,000/吨 | 🟢 低位 (10.4%) | ✅ 可分批建仓 |
| 稀土 | ¥425,000/吨 | 🟡 中位 (28.1%) | 观望为主 |

---

### 7. 每日自动扫描 ✅

**工具**：`scripts/daily_scan.py`

**Cron Job**：已配置，每日 15:00（收盘后）自动运行

**功能**：
- 扫描股票池
- 获取商品价格
- 发送飞书通知

---

### 8. 深度研究报告 ✅

**工具**：`scripts/research_generator.py`

**模板**：`templates/stock_research.md`

**报告内容**：
1. 股票基本信息
2. 资源禀赋（储量/产量/成本）
3. 财务分析（盈利能力/估值/分红）
4. 行业周期分析
5. 技术面分析
6. 投资建议（评分/操作/风险）
7. 跟踪计划

**使用方法**：
```bash
# 生成研究报告
~/.openclaw/workspace/china-stock-team/venv/bin/python3 scripts/research_generator.py sh.600459
```

**输出位置**：`research/{股票名称}_{日期}.md`

---

## 投资框架

### 核心原则

```
专注商品 · 立足周期 · 低位买入 · 长期持有
```

### 选股八条（寒武纪）

1. ✅ 买央企/省国资委/市国资委
2. ✅ 不买民企
3. ✅ 主仓≥70%
4. ✅ 最多3只股
5. ✅ 低位满仓满融，中位满仓，高位空仓
6. ✅ 回调不加仓
7. ✅ 单只股票最多20%
8. ✅ 单个行业最多40%

### 资源股特别原则（Mr Dang）

- 15PE 可接受
- 20PE 谨慎
- 30PE 跑路
- PB < 2.5 优先
- 股息率 > 1% 加分

---

## 风控规则

- **单只股票**：最多 20%
- **单个行业**：最多 40%
- **总仓位**：最多 80%
- **止损**：-8%
- **止盈**：+30-40%

---

## 股票池

### 有色金属（重点关注）

| 细分 | 股票 | 实控人 |
|-----|------|--------|
| 铜 | 西部矿业 | 青海国资委 |
| 铜 | 江西铜业 | 江西国资委 |
| 铜 | 云南铜业 | 央企 |
| 铝 | 中国铝业 | 央企 |
| 铝 | 云铝股份 | 央企 |
| 锂 | 盐湖股份 | 青海国资委 |
| 稀土 | 北方稀土 | 央企 |
| 稀土 | 五矿稀土 | 央企 |
| 其他 | 贵研铂业 | 央企 |
| 其他 | 中色股份 | 央企 |
| 其他 | 宝地矿业 | 新疆国资委 |

### 芯片（关注）

| 细分 | 股票 | 实控人 |
|-----|------|--------|
| 制造 | 中芯国际 | 央企 |
| 制造 | 华润微 | 央企 |
| 设备 | 中微公司 | 国资 |
| 设备 | 芯源微 | 国资 |

---

---

### 9. 多数据源适配器 ✅ 【2026-03-10 新增】

**文档**：`docs/ADAPTERS_GUIDE.md`

**功能**：
- 🔄 自动选择最优数据源
- 🔀 故障自动切换
- 📊 统一 API 接口
- 🩺 健康检查

**已集成数据源**：
| 数据源 | 类型 | 状态 | 特点 |
|--------|------|------|------|
| Baostock | 主力 | ✅ | 稳定可靠，支持前复权 |
| AKShare | 备用 | ✅ | 数据丰富，支持实时行情 |

**使用方法**：
```python
from adapters import get_data_manager

dm = get_data_manager()

# 获取实时价格（自动切换数据源）
price = dm.get_realtime_price('sh.600519')
print(f"价格: ¥{price.price}")

# 计算技术指标
tech = dm.get_technical_indicators('sh.600519')
print(f"RSI: {tech.rsi_14}")
print(f"MACD: {tech.macd}")
```

---

### 10. 新闻搜索适配器 ✅ 【2026-03-10 新增】

**功能**：
- 📰 多源新闻搜索
- 🔄 自动故障切换
- 🎯 股票相关新闻

**新闻数据源**：
| 数据源 | 类型 | 费用 | 状态 |
|--------|------|------|------|
| Google Gemini Search | 主力 | 免费 1500次/天 | ✅ |
| Perplexity | 备用 | 需要 API Key | ✅ |
| 新浪财经 | 备用 | 免费 | ✅ |

**使用方法**：
```python
from adapters import get_stock_news

# 获取股票新闻
news = await get_stock_news("贵州茅台", limit=5)
for item in news:
    print(f"标题: {item.title}")
    print(f"来源: {item.source}")
```

---

### 11. 知识库系统 ✅ 【2026-03-10 新增】

**功能**：
- 📚 存储学习内容（教训、规则、决策）
- 🔍 语义搜索相关案例
- 🧠 向量化存储

**知识类型**：
- `lesson` - 教训（失败案例）
- `rule` - 规则（交易规则）
- `decision` - 决策记录
- `prediction` - 预测记录

**使用方法**：
```python
from knowledge import get_knowledge_base

kb = get_knowledge_base()

# 添加教训
kb.add_lesson(
    content="追高买入导致亏损，应该等待回调",
    stock="sh.600519",
    result="failure"
)

# 搜索相似情况
results = kb.search_similar_situations("茅台 追高")
for item, score in results:
    print(f"教训: {item.content}")
    print(f"相似度: {score}")
```

---

## 文件结构

```
china-stock-team/
├── adapters/                  # 【新增】数据源适配器
│   ├── base.py               # 基类和数据类型
│   ├── akshare_adapter.py    # AKShare 适配器
│   ├── baostock_adapter.py   # Baostock 适配器
│   ├── manager.py            # 数据源管理器
│   └── news_adapter.py       # 新闻搜索适配器
├── knowledge/                 # 【新增】知识库系统
│   ├── knowledge_base.py     # 知识库实现
│   └── vectors/              # 向量存储目录
├── config/
│   ├── stock_pool.md          # 股票池配置
│   └── fundamental_data.md    # 基本面数据
├── scripts/
│   ├── selector_v3.py         # 选股工具（完整版）
│   ├── commodity_tracker.py   # 商品价格跟踪
│   ├── daily_scan.py          # 每日扫描任务
│   ├── research_generator.py  # 研究报告生成器
│   ├── stock_tools.py         # 技术指标计算
│   └── executor.py            # 系统操作
├── web/                       # Web 仪表盘
│   ├── dashboard_v3.py        # v3.0 看板（借鉴 ValueCell UI）
│   └── dashboard.py           # v2.0 看板
├── templates/
│   └── stock_research.md      # 研究报告模板
├── research/                  # 研究报告输出
├── logs/                      # 日志文件
├── database/
│   └── stock_team.db          # SQLite 数据库
├── venv/                      # Python 虚拟环境
└── README.md                  # 本文件
```

---

## 数据更新

### 自动更新（Cron）

- **每日 15:00**：股票扫描 + 商品价格 + 飞书通知

### 手动更新

- **基本面数据**：每季度财报发布后更新 `config/fundamental_data.md`
- **商品价格**：每日更新 `scripts/commodity_tracker.py` 中的 `CURRENT_PRICES`
- **股票池**：根据市场情况调整 `config/stock_pool.md`

---

## 下一步

### 已完成 ✅

1. ✅ 选股工具（基本面 + 技术面）
2. ✅ 商品价格跟踪
3. ✅ 每日自动扫描
4. ✅ 深度研究报告模板

### 待实现 🚧

1. 🚧 实时价格监控（每 15 分钟）
2. 🚧 持仓监控（止盈止损提醒）
3. 🚧 飞书通知集成（实际发送消息）
4. 🚧 回测系统（验证策略有效性）

---

**更新时间**：2026-03-10
**版本**：v1.1

## 更新日志

### v1.1 (2026-03-10)
- ✅ 新增多数据源适配器（Baostock + AKShare）
- ✅ 新增新闻搜索适配器（Google Gemini + 新浪财经）
- ✅ 新增知识库系统（向量存储 + 语义搜索）
- ✅ 新增 Web 仪表盘 v3.0（借鉴 ValueCell UI）
- ✅ 新增股票分析报告生成器

### v1.0 (2026-03-02)
- 初始版本
- 选股工具、商品跟踪、每日扫描
