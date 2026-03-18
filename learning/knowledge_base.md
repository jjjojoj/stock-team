# 股票团队知识库

> 团队自主学习和决策的知识积累

---

## 一、选股框架

### 1. 基本面筛选（硬性指标）

```python
# 用户要求的硬性规则
state_owner = ["央企", "省属国企", "市属国企"]  # 只买国企
market_cap < 200亿  # 市值小于200亿
pb < 2.5  # 市净率优先<2.5

# 行业偏好
industries = ["稀土", "锂电", "铜", "铝", "铁矿", "黄金"]
```

### 2. 商品周期筛选

```python
# 周期位置判断
def get_cycle_score(commodity_price_pct):
    """
    商品价格历史分位 → 配置权重
    """
    if price_pct < 20:  # 低位
        return "优先配置", weight = 1.5
    elif price_pct < 50:  # 中低位
        return "正常配置", weight = 1.0
    elif price_pct < 80:  # 中高位
        return "谨慎配置", weight = 0.5
    else:  # 高位
        return "观望", weight = 0
```

**当前周期状态**（2026-03-03）：
- 锂：10.4%分位 → ✅ 优先配置
- 稀土：28.1%分位 → 正常配置
- 铜：87.8%分位 → ⚠️ 谨慎
- 铝：57.3%分位 → 谨慎

### 3. 技术面筛选

```python
# 技术指标
rsi < 70  # 不追超买
macd > 0  # 趋势向上
volume_ratio > 1.0  # 放量
```

---

## 二、交易策略

### 1. 买入时机

**条件**（必须同时满足）：
1. 商品周期 < 50%分位
2. RSI < 70（不追高）
3. 当日涨幅 < 5%（不追涨）
4. PB < 2.5
5. 国企背景

**建仓规则**：
```python
# 分批建仓
if confidence >= 70:
    position = 0.15  # 15%仓位
elif confidence >= 50:
    position = 0.10  # 10%仓位
else:
    position = 0.05  # 5%仓位试水
```

### 2. 卖出时机

**止损规则**：
```python
if pnl_pct < -3 and today_change < 0:
    # 亏损>3%且当日下跌 → 止损
    sell_all()
```

**止盈规则**：
```python
if price >= target_price:
    # 到达目标价 → 分批止盈
    sell(50%)  # 先卖一半
    # 剩余等趋势反转

if pnl_pct > 20 and rsi > 80:
    # 盈利>20%且超买 → 止盈
    sell_all()
```

### 3. 持仓管理

**仓位控制**：
- 单只股票 ≤ 20%资金
- 单个行业 ≤ 40%资金
- 总仓位 ≤ 80%（保留20%现金）

**再平衡**：
- 每周检查仓位比例
- 超限股票部分减仓
- 现金比例<15%时停止买入

---

## 三、风险管理

### 1. 止损线设置

```python
stop_loss = cost_price * 0.92  # -8%止损
```

**动态调整**：
- 盈利后上移止损线到成本价（保本）
- 盈利>10%后止损线=成本*1.05（保5%利润）

### 2. 黑天鹅应对

**识别信号**：
- 商品价格单日跌>5%
- 行业政策利空
- 公司财务造假

**应对措施**：
- 立即卖出相关持仓
- 转现金观望
- 等待市场稳定

---

## 四、选股流程

### 每日扫描

```python
# 1. 获取股票池
stock_pool = get_stock_pool()  # 国企+资源股

# 2. 基本面筛选
filtered = [
    s for s in stock_pool
    if s.market_cap < 200
    and s.pb < 2.5
    and s.state_owner
]

# 3. 商品周期筛选
for stock in filtered:
    commodity = get_commodity(stock.industry)
    if commodity.price_pct < 50:
        stock.priority = "high"
    elif commodity.price_pct < 80:
        stock.priority = "medium"
    else:
        stock.priority = "low"

# 4. 技术面筛选
buy_candidates = [
    s for s in filtered
    if s.rsi < 70
    and s.today_change < 5
]

# 5. 按优先级排序
buy_candidates.sort(key=lambda x: (
    -x.priority,
    -x.tech_score,
    x.pb  # PB低优先
))

return buy_candidates[:5]  # 返回前5只
```

---

## 五、学习记录

### 需要学习的内容

1. **技术分析**
   - MACD金叉/死叉
   - KDJ指标
   - 布林带
   - 成交量分析

2. **基本面分析**
   - 财报解读
   - ROE/ROA分析
   - 现金流分析
   - 负债率判断

3. **行业研究**
   - 稀土产业链
   - 锂电产业链
   - 铜铝周期
   - 黄金避险属性

4. **交易心理**
   - 不追涨杀跌
   - 控制情绪
   - 严格执行纪律

---

## 六、工具清单

### 已有工具
- ✅ 实时价格获取（腾讯API）
- ✅ 商品周期数据
- ✅ 技术指标（tvscreener）
- ✅ 新闻监控（Sina/NewsAPI）
- ✅ AI预测系统
- ✅ 自动调仓系统

### 待接入工具
- ❌ 财务数据API（akshare）
- ❌ 机构持仓数据
- ❌ 龙虎榜数据
- ❌ 融资融券数据

---

*最后更新：2026-03-03*
