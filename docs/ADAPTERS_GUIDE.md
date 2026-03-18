# 多数据源适配器使用指南

## 概述

股票团队现在支持多数据源切换和故障切换，借鉴 ValueCell 的设计模式。

## 已集成的数据源

| 数据源 | 类型 | 状态 | 特点 |
|--------|------|------|------|
| Baostock | 主力 | ✅ | 稳定可靠，支持前复权 |
| AKShare | 备用 | ✅ | 数据丰富，支持实时行情 |

## 新闻数据源

| 数据源 | 类型 | 费用 | 特点 |
|--------|------|------|------|
| Google Gemini Search | 主力 | 免费 1500次/天 | 搜索质量好 |
| Perplexity | 备用 | 需要 API Key | AI 搜索 |
| 新浪财经 | 备用 | 免费 | 中文财经新闻 |

## 快速使用

### 1. 获取股票价格

```python
from adapters import get_data_manager

dm = get_data_manager()

# 获取实时价格（自动选择数据源）
price = dm.get_realtime_price('sh.600519')
print(f"价格: ¥{price.price}")

# 指定数据源
price = dm.get_realtime_price('sh.600519', prefer_source=DataSource.AKSHARE)
```

### 2. 获取历史数据

```python
from datetime import datetime, timedelta

end = datetime.now()
start = end - timedelta(days=60)

prices = dm.get_historical_prices('sh.600519', start, end)
for p in prices:
    print(f"{p.timestamp.date()}: ¥{p.close_price}")
```

### 3. 计算技术指标

```python
tech = dm.get_technical_indicators('sh.600519')
print(f"RSI: {tech.rsi_14}")
print(f"MACD: {tech.macd}")
print(f"布林带上轨: {tech.bb_upper}")
```

### 4. 搜索新闻

```python
from adapters import search_news, get_stock_news

# 搜索新闻
news = await search_news("贵州茅台 最新消息", limit=5)

# 获取股票新闻
news = await get_stock_news("贵州茅台", limit=5)
```

### 5. 知识库

```python
from knowledge import get_knowledge_base

kb = get_knowledge_base()

# 添加教训
kb.add_lesson(
    content="追高买入导致亏损，应该等待回调",
    stock="sh.600519",
    result="failure"
)

# 添加规则
kb.add_rule(
    rule_name="不追高",
    rule_content="涨幅超过3%不买入",
    category="risk_control"
)

# 搜索相似情况
results = kb.search_similar_situations("茅台 追高")
```

## 配置 Google Gemini Search（免费）

### 步骤 1：获取 API Key

1. 访问 https://makersuite.google.com/app/apikey
2. 登录 Google 账号
3. 点击 "Create API Key"
4. 复制 API Key

### 步骤 2：配置环境变量

```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
export GOOGLE_API_KEY="你的API Key"
```

### 步骤 3：验证

```python
import os
print(os.getenv("GOOGLE_API_KEY"))  # 应该显示你的 API Key
```

## 数据源健康检查

```python
from adapters import get_data_manager

dm = get_data_manager()
health = dm.health_check()

for source, status in health['sources'].items():
    emoji = "✅" if status['status'] == 'ok' else "❌"
    print(f"{emoji} {source}: {status['message']}")
```

## 故障切换机制

当主数据源失败时，系统会自动尝试备用数据源：

```python
# 自动故障切换
price = dm.get_realtime_price('sh.600519')
# 1. 先尝试 Baostock
# 2. 如果失败，尝试 AKShare
# 3. 返回第一个成功的结果
```

## 切换首选数据源

```python
from adapters import DataSource

dm = get_data_manager()

# 切换到 AKShare
dm.switch_primary(DataSource.AKSHARE)
```

## 与现有脚本的集成

### 更新 selector_v3.py

```python
# 旧代码
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus(...)

# 新代码
from adapters import get_data_manager

dm = get_data_manager()
prices = dm.get_historical_prices(symbol, start_date, end_date)
```

### 更新新闻监控

```python
# 旧代码
# 手动抓取新闻

# 新代码
from adapters import get_stock_news

news = await get_stock_news(stock_name)
for item in news:
    print(f"标题: {item.title}")
    print(f"内容: {item.content}")
```

## 文件结构

```
china-stock-team/
├── adapters/
│   ├── __init__.py
│   ├── base.py              # 基类和数据类型
│   ├── akshare_adapter.py   # AKShare 适配器
│   ├── baostock_adapter.py  # Baostock 适配器
│   ├── manager.py           # 数据源管理器
│   └── news_adapter.py      # 新闻搜索适配器
├── knowledge/
│   ├── __init__.py
│   ├── knowledge_base.py    # 知识库
│   └── vectors/             # 向量存储目录
│       └── stock_team.json
```

## 常见问题

### Q: AKShare 报错怎么办？

```bash
pip install akshare --upgrade
```

### Q: Google Gemini Search 报错？

检查 API Key 是否正确设置：
```python
import os
print(os.getenv("GOOGLE_API_KEY"))
```

### Q: 知识库数据存在哪里？

```
~/.openclaw/workspace/china-stock-team/knowledge/vectors/stock_team.json
```

---

更新时间：2026-03-10
