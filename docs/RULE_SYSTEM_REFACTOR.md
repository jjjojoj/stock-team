# 股票团队规则系统重构方案

**创建时间**: 2026-03-13 01:10
**核心洞察**: 用户指出规则库和预测规则是两个不同的系统

---

## 🎯 核心问题

**现状**：规则库既用于选股，也用于预测，混淆了两个系统

**应该是**：
1. **选股规则库** - 决定哪些股票值得买
2. **预测规则库** - 决定预测方向/准确率

---

## 📊 两个系统的区别

### 1️⃣ 选股规则库（Selection Rules）

**目标**：选择越来越优质的股票

**作用**：
- 哪些股票值得买入？
- 哪些股票应该排除？
- 评分筛选标准

**示例规则**：
```json
{
  "rule_id": "selection_001",
  "rule": "行业周期低位 + 市值200亿 + ROE>15%",
  "purpose": "选股",
  "success_rate": 0.65,
  "samples": 20
}
```

**更新机制**：
- 复盘选股效果 → 更新选股规则权重
- 成功案例 → 提取选股规律
- 失败案例 → 淘汰选股规则

---

### 2️⃣ 预测规则库（Prediction Rules）

**目标**：提高预测准确率

**作用**：
- 预测未来走势（up/down/neutral）
- 预测涨跌幅度
- 预测时间周期

**示例规则**：
```json
{
  "rule_id": "prediction_001",
  "rule": "RSI<30 + MACD金叉 → 未来5日上涨概率>60%",
  "purpose": "预测",
  "success_rate": 0.70,
  "samples": 15
}
```

**更新机制**：
- 复盘预测准确率 → 更新预测规则权重
- 预测成功 → 提取预测规律
- 预测失败 → 淘汰预测规则

---

## 🔄 复盘流程（改进后）

### 早盘复盘（11:30）

**输入**：
- 早盘预测（09:00生成）
- 2.5小时走势数据

**输出**：
1. **选股复盘**
   - 选的股票对不对？
   - 更新选股规则库

2. **预测复盘**
   - 预测方向对不对？
   - 更新预测规则库

3. **立即应用**
   - 下午预测使用新规则

---

### 午盘复盘（15:00）

**输入**：
- 午盘预测（13:00生成）
- 2小时走势数据

**输出**：
1. **选股复盘**
   - 选的股票对不对？
   - 更新选股规则库

2. **预测复盘**
   - 预测方向对不对？
   - 更新预测规则库

3. **立即应用**
   - 明日预测使用新规则

---

### 全日复盘（15:30）

**输入**：
- 全天预测
- 全天走势数据

**输出**：
1. **选股复盘**
   - 全天选股效果
   - 更新选股规则库

2. **预测复盘**
   - 全天预测准确率
   - 更新预测规则库

3. **长期优化**
   - 规则晋升/淘汰
   - 写入长期记忆

---

## 📁 文件结构（改进后）

```
learning/
├── selection_rules.json        # 选股规则库
│   ├── tech_rules              # 技术选股规则
│   ├── fundamental_rules       # 基本面选股规则
│   ├── event_rules             # 事件选股规则
│   └── industry_rules          # 行业选股规则
│
├── prediction_rules.json       # 预测规则库
│   ├── direction_rules         # 方向预测规则
│   ├── magnitude_rules         # 幅度预测规则
│   ├── timing_rules            # 时间预测规则
│   └── confidence_rules        # 置信度规则
│
├── selection_validation.json   # 选股验证池
└── prediction_validation.json  # 预测验证池
```

---

## 🚀 实施步骤

### 第1步：创建预测规则库

**新建文件**：`learning/prediction_rules.json`

**内容**：
```json
{
  "direction_rules": {
    "dir_rsi_oversold": {
      "condition": "RSI < 30",
      "prediction": "未来5日上涨概率>60%",
      "samples": 0,
      "success_rate": 0.0,
      "source": "技术分析"
    },
    "dir_macd_golden": {
      "condition": "MACD金叉 + 成交量放大",
      "prediction": "未来3日上涨概率>65%",
      "samples": 0,
      "success_rate": 0.0,
      "source": "技术分析"
    }
  },
  "magnitude_rules": {
    "mag_breakout": {
      "condition": "突破20日高点 + 放量",
      "prediction": "上涨幅度5-10%",
      "samples": 0,
      "success_rate": 0.0
    }
  },
  "timing_rules": {
    "time_earning": {
      "condition": "财报发布前3日",
      "prediction": "波动加大",
      "samples": 0,
      "success_rate": 0.0
    }
  }
}
```

---

### 第2步：增强复盘功能

**修改文件**：
1. `midday_review.py` - 早盘复盘
2. `daily_review_closed_loop.py` - 全日复盘

**新增功能**：
```python
def review_selection():
    """复盘选股效果"""
    # 1. 检查选的股票对不对
    # 2. 更新选股规则库
    # 3. 影响下次选股

def review_prediction():
    """复盘预测准确率"""
    # 1. 检查预测方向对不对
    # 2. 更新预测规则库
    # 3. 影响下次预测
```

---

### 第3步：增加复盘次数

**CRON配置**：
```bash
# 11:30 - 早盘复盘
30 11 * * 1-5 cd $PROJECT_ROOT && $VENV_PYTHON scripts/midday_review.py >> $LOG_DIR/cron_midday.log 2>&1

# 15:00 - 午盘复盘
0 15 * * 1-5 cd $PROJECT_ROOT && $VENV_PYTHON scripts/midday_review.py --afternoon >> $LOG_DIR/cron_afternoon.log 2>&1
```

---

### 第4步：清理重复脚本

**保留**：
- `ai_predictor.py` - 预测系统
- `selector.py` - 选股系统
- `midday_review.py` - 盘中复盘
- `daily_review_closed_loop.py` - 全日复盘

**删除/归档**：
- `daily_review_closed_loop_v2.py`
- `daily_review_system.py`
- `market_review_v2.py`
- `prediction_system.py`
- `prediction_workflow.py`

---

## 📊 预期效果

### 改进前

| 项目 | 值 |
|------|-----|
| 规则系统 | 1个（混淆）|
| 复盘次数 | 1次/天 |
| 学习周期 | 6.5小时 |
| 预测方法 | 不变 |

### 改进后

| 项目 | 值 | 改进 |
|------|-----|------|
| 规则系统 | 2个（分离）| +100% |
| 复盘次数 | 3次/天 | +200% |
| 学习周期 | 2小时 | -69% |
| 预测方法 | 持续优化 | ✅ |

---

## 🎯 关键改进点

### 1. 规则系统分离

**选股规则库**：
- 目标：选择优质股票
- 更新：复盘选股效果

**预测规则库**：
- 目标：提高预测准确率
- 更新：复盘预测准确率

### 2. 复盘直接影响

**早盘复盘（11:30）**：
- 选股复盘 → 更新选股规则库
- 预测复盘 → 更新预测规则库
- **立即应用到下午预测**

**午盘复盘（15:00）**：
- 选股复盘 → 更新选股规则库
- 预测复盘 → 更新预测规则库
- **立即应用到明日预测**

### 3. 学习周期缩短

**从6.5小时 → 2小时**
- 学习速度提升3倍
- 准确率提升更快

---

*创建时间：2026-03-13 01:10*
