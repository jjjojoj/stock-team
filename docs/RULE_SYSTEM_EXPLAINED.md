# 规则系统完整说明

**最后更新**: 2026-03-12 23:45

---

## 📚 三个核心概念

### 1️⃣ 知识库（Book Knowledge）

**来源**：从炒股书籍中提取的知识点

**示例**：
- 《股票作手回忆录》：价格总是沿最小阻力线运动
- 《聪明的投资者》：安全边际原则
- 《笑傲股市》：CAN SLIM选股法

**数量**：3个知识点（book_knowledge.json）

**状态**：理论阶段，未经市场验证

**下一步**：转化为可测试规则 → 进入验证池

---

### 2️⃣ 验证池（Validation Pool）

**来源**：
- 书籍知识点 → 转化为可测试规则（6个）
- 实战经验 → 提取规律（1个）

**示例**：
```
rule_book_001_1:
  规则: 价格总是沿最小阻力线运动
  可测试形式: 突破20日高点后，价格继续上涨概率>55%
  样本: 0/15
  胜率: 0%
  状态: 验证中

exp_avoid_稀土_20260312:
  规则: 避开稀土行业陷阱
  可测试形式: 避免稀土行业，平均亏损7.3%
  样本: 2/15
  胜率: 0%
  状态: 验证中
```

**数量**：7条待验证规则

**晋升标准**：
- 样本 ≥ 15个
- 胜率 ≥ 60%

**淘汰标准**：
- 样本 ≥ 15个
- 胜率 < 30%

---

### 3️⃣ 规则库（Rule Library）

**来源**：验证池晋升

**示例**：
```
event_rules:
  industry_cycle_up:
    条件: 行业处于周期低位
    预测: 板块上涨
    权重: 0.20
    胜率: 0%
    样本: 1

sentiment_rules:
  positive_news:
    条件: 正面新闻 > 3条
    预测: 上涨
    权重: 0.10
    胜率: 0%
    样本: 1
```

**数量**：10条已验证规则

**分类**：
- 技术规则（4条）：rsi_oversold, macd_golden_cross, break_ma20, volume_surge
- 基本面规则（2条）：low_pe, high_roe
- 事件规则（3条）：geopolitical_war, policy_support, industry_cycle_up
- 情绪规则（1条）：positive_news

**用途**：参与实际预测决策

---

## 🔄 完整流程

```
┌─────────────────────────────────────────────────────────┐
│                    规则进化流程                          │
└─────────────────────────────────────────────────────────┘

【第一阶段：学习】
📚 炒股书籍（3本）
  ↓ 提取知识点
📝 知识库（3个知识点）
  ↓ 转化为可测试形式

【第二阶段：验证】
🧪 验证池（7条规则）
  ↓ 每次预测记录效果
  ↓ 15样本 + 60%胜率
  
【第三阶段：应用】
✅ 规则库（10条规则）
  ↓ 参与预测决策
  ↓ 根据效果调整权重
  
【第四阶段：优化】
🔄 规则晋升/淘汰
  ↓ 每天16:00检查
  ↓ 持续优化

【闭环】
实战经验 → 提取规律 → 验证池 → 规则库
```

---

## 📊 当前状态

| 类型 | 数量 | 状态 | 文件 |
|------|------|------|------|
| 知识库 | 3个 | 理论阶段 | book_knowledge.json |
| 验证池 | 7条 | 等待验证 | rule_validation_pool.json |
| 规则库 | 10条 | 使用中 | prediction_rules.json |

---

## 🎯 如何使用

### 查看知识库
```bash
cat ~/.openclaw/workspace/china-stock-team/learning/book_knowledge.json
```

### 查看验证池
```bash
cat ~/.openclaw/workspace/china-stock-team/learning/rule_validation_pool.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for rule_id, rule in d.items():
    samples = rule['live_test']['samples']
    rate = rule['live_test']['success_rate']
    print(f'{rule_id}: 样本={samples}/15, 胜率={rate:.1%}')
"
```

### 查看规则库
```bash
curl -s http://localhost:8082/api/rules | python3 -c "
import sys, json
d = json.load(sys.stdin)
for category, rules in d.items():
    print(f'【{category}】')
    for rule_id, rule in rules.items():
        print(f'  {rule_id}: 权重={rule[\"weight\"]:.2f}, 样本={rule[\"samples\"]}')"
```

---

## 🔧 面板统计修复

**修复前**：
- 知识库: 13（错误，统计的是memory.md的checkbox）

**修复后**：
- 书籍知识点: 3个
- 验证池规则: 7条
- 规则库规则: 10条

---

## 📝 总结

**关键区别**：

1. **知识库** = 理论知识（书籍）
2. **验证池** = 待验证规则（理论→实践）
3. **规则库** = 已验证规则（实战使用）

**晋升路径**：
```
书籍 → 知识点 → 验证池 → 规则库 → 预测
```

**闭环机制**：
```
预测 → 验证 → 更新规则 → 改进预测
```

---

*最后更新: 2026-03-12 23:45*
