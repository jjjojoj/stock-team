#!/usr/bin/env python3
"""
事件驱动分析模块

该模块提供事件驱动的股票分析功能，包括：
1. 新闻标签提取（使用Claude API进行智能分类）
2. 事件与K线数据关联分析
3. 用户框选区间分析
4. 事件影响学习与规则生成
5. 与预测系统的集成

主要类：
- NewsLabeler: 新闻标签提取器
- EventKlineMapper: 事件K线关联器
- RangeAnalyzer: 区间分析器
- PredictionIntegrator: 预测系统集成器

使用方法：
```python
from scripts.event_analysis import NewsLabeler, EventKlineMapper

# 创建新闻标签器
labeler = NewsLabeler()
result = labeler.label_news(news_id, title, content)

# 创建K线映射器
mapper = EventKlineMapper()
mapper.map_news_to_kline(news_id, stock_code)
```
"""

__version__ = "1.0.0"
__author__ = "China Stock Team"

from .news_labeler import NewsLabeler
from .event_kline_mapper import EventKlineMapper
from .range_analyzer import RangeAnalyzer
from .integration import PredictionIntegrator

__all__ = [
    "NewsLabeler",
    "EventKlineMapper",
    "RangeAnalyzer",
    "PredictionIntegrator",
]
