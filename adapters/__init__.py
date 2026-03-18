"""
股票团队数据源适配器
支持多数据源切换和冗余
"""

from .base import BaseDataAdapter, AdapterCapability, DataSource, AssetPrice, Asset, TechnicalIndicators
from .akshare_adapter import AKShareAdapter
from .baostock_adapter import BaostockAdapter
from .manager import DataSourceManager, get_data_manager
from .news_adapter import NewsSearchAdapter, NewsItem, search_news, get_stock_news

__all__ = [
    "BaseDataAdapter",
    "AdapterCapability",
    "DataSource",
    "AssetPrice",
    "Asset",
    "TechnicalIndicators",
    "AKShareAdapter",
    "BaostockAdapter",
    "DataSourceManager",
    "get_data_manager",
    "NewsSearchAdapter",
    "NewsItem",
    "search_news",
    "get_stock_news",
]
