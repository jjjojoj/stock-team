# 知识库扩展方案 - 信息源分级系统

**版本**: v1.0  
**日期**: 2026-03-15  
**目标**: 吸纳更多内容源，同时保证质量

---

## 🎯 核心理念

**质量 vs 数量**：
- 书籍 = 黄金级（最优质，经过大众筛选）
- 专业机构 = 白银级（研究报告、年报）
- KOL/博主 = 青铜级（有价值但需验证）
- 散户情绪 = 石头级（反向指标，需谨慎）

**验证池**：所有来源的内容 → 验证池 → 验证通过 → 规则库

---

## 📊 信息源分级系统

### Tier 1：黄金级（直接采纳）

**来源**：
- 📚 **投资经典书籍**（当前已有 3 本）
  - 《股票作手回忆录》
  - 《聪明的投资者》
  - 《笑傲股市》
- 📰 **权威财经媒体**
  - 财新网、第一财经、证券时报
  - Reuters、Bloomberg（财经）
- 📊 **券商研报**
  - 中信证券、中金公司、国泰君安
  - 通过 API 获取（如 Eastmoney 研报中心）

**处理方式**：
- **直接进入验证池**（跳过质量检查）
- **置信度初始值**：0.8（高）
- **验证通过标准**：3 次实战 + 50% 胜率

**实现**：
```python
class Tier1Collector:
    """黄金级信息源收集器"""
    
    def collect_research_reports(self):
        """收集券商研报"""
        # 东方财富研报 API
        url = "https://reportapi.eastmoney.com/report/list"
        # 提取关键观点 → 验证池
    
    def collect_authoritative_news(self):
        """收集权威媒体新闻"""
        # 财新网 RSS
        # Reuters API
        # 提取投资建议 → 验证池
```

---

### Tier 2：白银级（需要验证）

**来源**：
- 📈 **上市公司年报/季报**
  - 巨潮资讯网 API
  - 提取业绩指引、行业趋势
- 🎥 **官方财经频道**
  - CCTV 财经
  - 第一财经电视
- 💼 **基金经理访谈**
  - 雪球、且慢等平台

**处理方式**：
- **进入验证池**
- **置信度初始值**：0.6（中）
- **验证通过标准**：5 次实战 + 60% 胜率

**实现**：
```python
class Tier2Collector:
    """白银级信息源收集器"""
    
    def collect_annual_reports(self, symbol):
        """收集年报"""
        # 巨潮资讯网 API
        url = f"https://www.cninfo.com.cn/new/hisAnnouncement"
        # 提取关键信息 → 验证池
    
    def collect_fund_manager_views(self):
        """收集基金经理观点"""
        # 雪球 API
        # 且慢 API
        # 提取投资逻辑 → 验证池
```

---

### Tier 3：青铜级（严格验证）

**来源**：
- 🎬 **抖音财经博主**
  - 通过关键词搜索
  - 提取投资建议
- 📱 **微博大V**
  - 财经类 KOL
  - 股票分析师
- 💬 **雪球/东方财富论坛**
  - 高赞帖子
  - 热门讨论

**处理方式**：
- **进入验证池**
- **置信度初始值**：0.3（低）
- **验证通过标准**：10 次实战 + 70% 胜率
- **必须加标签**：`source_quality: bronze`

**实现**：
```python
class Tier3Collector:
    """青铜级信息源收集器"""
    
    def collect_douyin_finance(self, keywords):
        """收集抖音财经内容"""
        # 抖音搜索 API（需要爬虫）
        # 提取视频文案中的投资建议
        # 添加到验证池（标签：bronze）
    
    def collect_weibo_kol(self, keywords):
        """收集微博 KOL 观点"""
        # 微博搜索 API
        # 提取投资建议
        # 添加到验证池（标签：bronze）
    
    def collect_forum_hot_posts(self):
        """收集论坛热帖"""
        # 雪球热帖
        # 东方财富股吧
        # 提取投资逻辑
        # 添加到验证池（标签：bronze）
```

---

### Tier 4：石头级（反向指标）

**来源**：
- 😰 **散户情绪指数**
  - 股吧情绪分析
  - 恐惧贪婪指数
- 📊 **市场热度**
  - 搜索指数（百度指数）
  - 新开户数
  - 融资余额变化

**处理方式**：
- **不进入验证池**（直接作为反向指标）
- **用途**：
  - 情绪极度乐观 → 卖出信号
  - 情绪极度悲观 → 买入信号

**实现**：
```python
class Tier4Collector:
    """石头级信息源收集器（反向指标）"""
    
    def collect_retail_sentiment(self, symbol):
        """收集散户情绪"""
        # 股吧情绪分析
        # 返回：极度悲观/悲观/中性/乐观/极度乐观
    
    def collect_market_heat(self):
        """收集市场热度"""
        # 百度指数
        # 新开户数
        # 融资余额
        # 返回：市场热度指数
```

---

## 🔄 统一收集器

**入口脚本**：`scripts/knowledge_collector.py`

```python
#!/usr/bin/env python3
"""
知识库统一收集器
从多个信息源收集内容，分级处理
"""

class KnowledgeCollector:
    def __init__(self):
        self.tier1 = Tier1Collector()
        self.tier2 = Tier2Collector()
        self.tier3 = Tier3Collector()
        self.tier4 = Tier4Collector()
        self.validator = RuleValidator()
    
    def collect_all(self):
        """收集所有信息源"""
        # Tier 1：每天收集
        tier1_items = self.tier1.collect_all()
        
        # Tier 2：每周收集
        tier2_items = self.tier2.collect_all()
        
        # Tier 3：按需收集（触发关键词）
        tier3_items = self.tier3.collect_all()
        
        # Tier 4：实时监控
        tier4_data = self.tier4.collect_all()
        
        # 添加到验证池
        for item in tier1_items + tier2_items + tier3_items:
            self.validator.add_to_pool(item)
        
        # Tier 4 直接使用
        self.process_sentiment(tier4_data)
    
    def run_daily(self):
        """每日任务"""
        # 1. 收集 Tier 1
        # 2. 更新 Tier 4（情绪指数）
        pass
    
    def run_weekly(self):
        """每周任务"""
        # 1. 收集 Tier 2（年报、研报）
        # 2. 清理过期验证规则
        pass
```

---

## 📐 验证池扩展

**新增字段**：

```json
{
  "rule_id": "bronze_20260315_001",
  "rule": "抖音博主建议：盐湖提锂技术突破，利好盐湖股份",
  "testable_form": "盐湖股份在提锂技术新闻后3日内上涨",
  "category": "technique_breakthrough",
  "source": "抖音@财经大V",
  "source_tier": "bronze",
  "source_url": "https://douyin.com/xxx",
  "status": "validating",
  "confidence": 0.3,
  "confidence_threshold": 0.7,
  "live_test": {
    "samples": 0,
    "success_rate": 0.0,
    "required_samples": 10,
    "required_success_rate": 0.7
  },
  "created_at": "2026-03-15T02:30:00",
  "tags": ["bronze", "social_media", "kbit_technology"]
}
```

---

## 🚀 实现步骤

### Phase 1：基础设施（1-2天）

1. **创建收集器框架**
   - `scripts/collectors/tier1_collector.py`
   - `scripts/collectors/tier2_collector.py`
   - `scripts/collectors/tier3_collector.py`
   - `scripts/collectors/tier4_collector.py`

2. **扩展验证池 schema**
   - 添加 `source_tier` 字段
   - 添加 `confidence_threshold` 字段
   - 添加 `tags` 字段

3. **修改验证逻辑**
   - 不同 Tier 不同验证标准
   - Tier 1：3次 + 50%
   - Tier 2：5次 + 60%
   - Tier 3：10次 + 70%

---

### Phase 2：信息源接入（3-5天）

**Tier 1（优先）**：
- ✅ 书籍（已完成）
- ⏳ 券商研报（东方财富 API）
- ⏳ 权威媒体 RSS

**Tier 2**：
- ⏳ 年报收集（巨潮资讯网）
- ⏳ 基金经理访谈（雪球）

**Tier 3**：
- ⏳ 微博 KOL（微博 API）
- ⏳ 抖音财经（爬虫）
- ⏳ 论坛热帖（雪球/东财）

**Tier 4**：
- ⏳ 散户情绪分析（股吧）
- ⏳ 市场热度指数

---

### Phase 3：自动化（1-2天）

1. **添加 Cron 任务**
   ```python
   "knowledge_collect_daily": {
       "times": ["06:00"],
       "script": "knowledge_collector.py --daily",
       "enabled": True
   },
   "knowledge_collect_weekly": {
       "times": ["周日 07:00"],
       "script": "knowledge_collector.py --weekly",
       "enabled": True
   }
   ```

2. **关键词触发**
   - 监控新闻中的关键词
   - 触发 Tier 3 收集

---

## 📊 数据流程图

```
┌─────────────────────────────────────────────────────────┐
│                   信息源分级系统                          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌───────────┬───────────┬───────────┬───────────┐
│  Tier 1   │  Tier 2   │  Tier 3   │  Tier 4   │
│  黄金级   │  白银级   │  青铜级   │  石头级   │
├───────────┼───────────┼───────────┼───────────┤
│ 书籍      │ 年报      │ 抖音      │ 散户情绪  │
│ 研报      │ 基金经理  │ 微博      │ 市场热度  │
│ 权威媒体  │ 官方频道  │ 论坛      │ 反向指标  │
└───────────┴───────────┴───────────┴───────────┘
       ↓             ↓             ↓             ↓
   直接采纳      需要验证      严格验证      反向使用
   (0.8)        (0.6)         (0.3)         (不进池)
       ↓             ↓             ↓             ↓
┌─────────────────────────────────────────────────────────┐
│                      验证池                              │
│  规则 → 实战验证 → 通过 → 规则库                          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                      规则库                              │
│  用于每日预测、风险评估、交易决策                          │
└─────────────────────────────────────────────────────────┘
```

---

## 💡 具体实现示例

### 1. 券商研报收集器

```python
# scripts/collectors/tier1_research_reports.py

import requests
from datetime import datetime

def collect_research_reports():
    """收集券商研报"""
    url = "https://reportapi.eastmoney.com/report/list"
    params = {
        "cb": "datatable",
        "industryCode": "*",  # 所有行业
        "pageSize": 50,
        "rating": "买入",  # 只收集"买入"评级
        "beginTime": datetime.now().strftime("%Y-%m-%d")
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    reports = []
    for item in data.get("data", []):
        report = {
            "title": item["title"],
            "stock": item["stockName"],
            "rating": item["emRatingName"],
            "reason": item["title"],  # 简化：用标题作为原因
            "source": "eastmoney_research",
            "source_tier": "gold",
            "confidence": 0.8,
            "date": item["publishDate"]
        }
        reports.append(report)
    
    return reports
```

### 2. 微博 KOL 收集器

```python
# scripts/collectors/tier3_weibo_kol.py

import requests

def collect_weibo_kol(keywords=["盐湖股份", "锂电", "稀土"]):
    """收集微博 KOL 观点"""
    # 微博搜索 API（需要登录）
    url = "https://m.weibo.cn/api/container/getIndex"
    
    items = []
    for keyword in keywords:
        params = {
            "containerid": f"100103type=1&q={keyword}",
            "page_type": "searchall"
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        for card in data.get("data", {}).get("cards", []):
            if card.get("card_type") == 9:  # 微博卡片
                mblog = card.get("mblog", {})
                
                # 过滤：只保留粉丝数 > 10万 的博主
                user = mblog.get("user", {})
                if user.get("followers_count", 0) < 100000:
                    continue
                
                item = {
                    "content": mblog.get("text"),
                    "author": user.get("screen_name"),
                    "followers": user.get("followers_count"),
                    "source": "weibo_kol",
                    "source_tier": "bronze",
                    "confidence": 0.3,
                    "url": f"https://m.weibo.cn/detail/{mblog.get('id')}"
                }
                items.append(item)
    
    return items
```

### 3. 散户情绪分析器

```python
# scripts/collectors/tier4_sentiment.py

import requests
import re

def analyze_guba_sentiment(symbol):
    """分析股吧散户情绪"""
    # 东方财富股吧
    url = f"https://guba.eastmoney.com/list,{symbol}.html"
    
    response = requests.get(url)
    html = response.text
    
    # 提取帖子标题
    titles = re.findall(r'<a href=".*?" title="(.*?)">', html)
    
    # 情绪分析
    positive_keywords = ["利好", "涨停", "牛股", "大涨", "主力进场"]
    negative_keywords = ["利空", "跌停", "垃圾", "大跌", "主力出货"]
    
    positive_count = sum(1 for t in titles 
                       for kw in positive_keywords if kw in t)
    negative_count = sum(1 for t in titles 
                       for kw in negative_keywords if kw in t)
    
    total = positive_count + negative_count
    if total == 0:
        return "neutral"
    
    sentiment_score = (positive_count - negative_count) / total
    
    if sentiment_score > 0.5:
        return "极度乐观"  # 反向信号：卖出
    elif sentiment_score > 0.2:
        return "乐观"
    elif sentiment_score < -0.5:
        return "极度悲观"  # 反向信号：买入
    elif sentiment_score < -0.2:
        return "悲观"
    else:
        return "中性"
```

---

## 🎯 预期效果

### 信息源数量

| Tier | 当前 | 目标（1个月后）| 目标（3个月后）|
|------|------|--------------|--------------|
| Tier 1 | 3（书籍）| 50（+研报/媒体）| 200 |
| Tier 2 | 0 | 30（+年报/基金）| 100 |
| Tier 3 | 0 | 100（+KOL/论坛）| 500 |
| Tier 4 | 0 | 实时监控 | 实时监控 |

### 验证池增长

| 时间 | 验证池规则 | 已验证规则 |
|------|-----------|-----------|
| 当前 | 16 条 | 0 条 |
| 1个月后 | 100 条 | 30 条 |
| 3个月后 | 500 条 | 150 条 |

---

## 📝 配置文件

**config/knowledge_sources.json**：

```json
{
  "tier1": {
    "enabled": true,
    "sources": [
      {
        "name": "券商研报",
        "type": "api",
        "url": "https://reportapi.eastmoney.com",
        "frequency": "daily"
      },
      {
        "name": "权威媒体",
        "type": "rss",
        "feeds": ["财新网", "第一财经", "证券时报"],
        "frequency": "daily"
      }
    ]
  },
  "tier2": {
    "enabled": true,
    "sources": [
      {
        "name": "年报",
        "type": "api",
        "url": "https://www.cninfo.com.cn",
        "frequency": "weekly"
      }
    ]
  },
  "tier3": {
    "enabled": true,
    "sources": [
      {
        "name": "微博KOL",
        "type": "api",
        "keywords": ["盐湖股份", "锂电", "稀土"],
        "frequency": "daily",
        "min_followers": 100000
      },
      {
        "name": "抖音财经",
        "type": "crawler",
        "keywords": ["盐湖提锂", "稀土"],
        "frequency": "daily"
      }
    ]
  },
  "tier4": {
    "enabled": true,
    "sources": [
      {
        "name": "散户情绪",
        "type": "analyzer",
        "frequency": "realtime"
      }
    ]
  }
}
```

---

## 🚀 下一步

1. **等待 Claude 审查结果**（正在运行）
2. **决定优先级**：
   - P0：修复项目 bug
   - P1：实现 Tier 1 收集器（券商研报）
   - P2：实现 Tier 2-4

3. **你希望先实现哪个 Tier？**
   - Tier 1（研报/媒体）- 最有价值
   - Tier 3（KOL/论坛）- 最有趣
   - Tier 4（情绪）- 最实用（反向指标）

告诉我你的优先级，我立即开始实现！
