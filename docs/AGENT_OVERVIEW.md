# 股票团队Agent全景图

**最后更新**: 2026-03-12 23:59
**总脚本数**: 72个
**Agent/智能体数**: 4个核心Agent + 多个工作模块

---

## 🤖 核心Agent（4个）

### 1. 搜集官Agent（collector_agent.py）
**职责**：爬取网络资源存入知识库
**运行时间**：每日 20:30
**数据源**：
- 📚 投资书籍（豆瓣、京东、微信读书）
- 📝 论坛帖子（雪球、东方财富、知乎）
- 💡 炒股思路（贴吧、公众号）
- 🗞️ 财经文章（华尔街见闻、财新网）
**输出**：知识库素材（knowledge_base.json）

---

### 2. 学习官Agent（learner_agent.py）
**职责**：阅读知识库，转化成可测试规则
**运行时间**：每日 21:00
**工作流程**：
1. 扫描知识库新内容
2. AI阅读理解
3. 提取核心观点
4. 转化可测试规则
5. 存入验证池
**输出**：验证池规则（rule_validation_pool.json）

---

### 3. 经验学习器（experience_learner.py）
**职责**：从实战中提取经验
**运行时间**：每日 15:45
**工作内容**：
- 📊 分析持仓股票走势
- 👀 跟踪观察池表现
- 📝 复盘预测历史
- 🧪 提取成功/失败模式
- 📝 生成实战规则
**输出**：经验规则（experience_library.json）

---

### 4. 团队优化器（team_optimizer.py）
**职责**：每周评估团队健康，优化系统
**运行时间**：每周日 21:00
**工作内容**：
- 📊 收集团队指标
- 🔍 检测系统问题
- 🌐 联网学习开源社区
- 💡 生成改进建议
- 🔧 自动实施优化
**输出**：团队健康报告（team_health.json）

---

## 🛠️ 工作模块（按功能分类）

### 【预测与决策】
- **ai_predictor.py** - AI预测生成器
- **prediction_engine.py** - 预测引擎（自我进化）
- **auto_trader.py** - 自动交易系统 v2
- **auto_trader_v3.py** - 自动交易系统 v3（含卖出逻辑）
- **event_trader.py** - 事件驱动交易
- **position_manager.py** - 仓位管理

### 【规则管理】
- **daily_book_learning.py** - 书籍学习（提取知识点）
- **rule_validation.py** - 规则验证
- **rule_validator.py** - 规则验证器（增强版）
- **rule_evolution.py** - 规则进化
- **rule_promotion.py** - 规则晋升/淘汰
- **daily_review_closed_loop.py** - 闭环复盘

### 【市场监控】
- **market_style_monitor.py** - 市场风格监控
- **a_share_risk_monitor.py** - A股特殊风险监控
- **circuit_breaker.py** - 熔断机制
- **data_quality_monitor.py** - 数据质量监控
- **api_health_monitor.py** - API健康监控
- **sentiment_analyzer.py** - 情绪分析

### 【复盘与学习】
- **daily_learning.py** - 每日复盘学习
- **weekly_learning.py** - 每周深度学习
- **market_review_v2.py** - 收盘复盘（三层架构）
- **midday_review.py** - 午盘复盘

### 【研究与分析】
- **daily_stock_research.py** - 每日深度研究
- **stock_pool_manager.py** - 股票池管理
- **backtester.py** - 回测系统
- **overfitting_test.py** - 过拟合测试

### 【系统调度】
- **scheduler.py** - 24小时调度器 v2.0
- **intraday_monitor.py** - 盘中监控（30分钟）

---

## 🔄 完整工作流程

### 每日流程

```
09:00 - 早盘预测生成
         └─ ai_predictor.py（使用规则库）

09:30-15:00 - 盘中监控（每30分钟）
         └─ intraday_monitor.py

15:30 - 盘后复盘（闭环核心）
         └─ daily_review_closed_loop.py
         └─ 验证预测
         └─ 更新规则库样本/胜率

15:45 - 经验学习
         └─ experience_learner.py ⭐
         └─ 分析持仓/观察池
         └─ 提取成功/失败模式
         └─ 生成实战规则

16:00 - 规则晋升/淘汰
         └─ rule_promotion.py

20:00 - 深度学习（读书）
         └─ daily_book_learning.py

20:30 - 搜集官工作
         └─ collector_agent.py ⭐
         └─ 爬取网络资源
         └─ 存入知识库

21:00 - 学习官工作
         └─ learner_agent.py ⭐
         └─ 阅读知识库
         └─ 转化可测试规则
         └─ 存入验证池
```

### 每周流程

```
周日 20:00 - 周总结
         └─ weekly_summary.py

周日 21:00 - 团队优化评估
         └─ team_optimizer.py ⭐
         └─ 收集指标
         └─ 检测问题
         └─ 联网学习
         └─ 自动改进
```

---

## 📊 Agent协作关系

```
【知识收集层】
搜集官Agent → 知识库
    ↓
【知识转化层】
学习官Agent → 验证池
    ↓
【实战验证层】
预测系统 → 使用规则 → 预测
    ↓
经验学习器 → 提取经验 → 验证池
    ↓
【系统优化层】
团队优化器 → 评估改进 → 整个系统
```

---

## 🎯 Agent能力对比

| Agent | 输入 | 输出 | 频率 | 智能程度 |
|-------|------|------|------|---------|
| 搜集官 | 网络资源 | 知识库素材 | 每日 | 🤖 爬虫+去重 |
| 学习官 | 知识库 | 可测试规则 | 每日 | 🧠 AI理解+转化 |
| 经验学习器 | 实战数据 | 实战规则 | 每日 | 📊 模式识别 |
| 团队优化器 | 系统指标 | 优化方案 | 每周 | 🎯 诊断+改进 |

---

## 🚀 未来扩展方向

### 计划中的Agent

1. **新闻监控Agent**（news_monitor_agent.py）
   - 实时监控财经新闻
   - 自动触发预测更新

2. **风险预警Agent**（risk_alert_agent.py）
   - 监控持仓风险
   - 自动发送警报

3. **策略回测Agent**（backtest_agent.py）
   - 自动回测新规则
   - 筛选高胜率策略

4. **社区学习Agent**（community_agent.py）
   - 爬取量化社区
   - 学习优秀策略

---

## 📝 总结

**核心Agent**：4个
**工作模块**：68个
**总脚本**：72个

**关键特点**：
1. ✅ 分工明确，职责清晰
2. ✅ 协作流畅，数据互通
3. ✅ 持续进化，自我优化
4. ✅ 完整闭环，不断进步

---

*股票团队是一个完整的AI组织！*
