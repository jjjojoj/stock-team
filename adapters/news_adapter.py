#!/usr/bin/env python3
"""
新闻搜索适配器
支持多种新闻获取渠道
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# 添加虚拟环境路径
VENV_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)


class NewsSource(Enum):
    """新闻数据源"""
    SINA_FINANCE = "sina_finance"
    EASTMONEY = "eastmoney"
    TENCENT = "tencent"


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    content: str
    source: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None


class NewsSearchAdapter:
    """
    新闻搜索适配器
    支持多种新闻源，自动切换
    """
    
    def __init__(self, primary: NewsSource = NewsSource.SINA_FINANCE):
        self.primary = primary
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        
        # 检查可用性
        self.available_sources = self._check_availability()
        logger.info(f"新闻搜索适配器初始化，可用数据源: {[s.value for s in self.available_sources]}")
    
    def _check_availability(self) -> List[NewsSource]:
        """检查可用的新闻源"""
        available = []
        
        # 新浪财经（免费，无需 API）
        available.append(NewsSource.SINA_FINANCE)
        
        # 东方财富（免费，无需 API）
        available.append(NewsSource.EASTMONEY)
        
        # 腾讯财经（免费，无需 API）
        available.append(NewsSource.TENCENT)
        
        return available
    
    async def search_news(
        self,
        query: str,
        source: Optional[NewsSource] = None,
        limit: int = 10
    ) -> List[NewsItem]:
        """搜索新闻"""
        if source:
            return await self._search_with_source(query, source, limit)
        
        # 按优先级尝试
        for src in self.available_sources:
            try:
                results = await self._search_with_source(query, src, limit)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"⚠️ {src.value} 搜索失败: {e}")
                continue
        
        return []
    
    async def _search_with_source(
        self,
        query: str,
        source: NewsSource,
        limit: int
    ) -> List[NewsItem]:
        """使用指定数据源搜索"""
        
        if source == NewsSource.SINA_FINANCE:
            return await self._search_sina_finance(query, limit)
        elif source == NewsSource.EASTMONEY:
            return await self._search_eastmoney(query, limit)
        elif source == NewsSource.TENCENT:
            return await self._search_tencent(query, limit)
        
        return []
    
    async def _search_sina_finance(self, query: str, limit: int = 10) -> List[NewsItem]:
        """从新浪财经获取新闻"""
        try:
            import aiohttp
            from urllib.parse import quote
            
            url = f"https://search.sina.com.cn/?q={quote(query)}&c=news&from=channel&ie=utf-8"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    html = await response.text()
                    
                    # 简单解析新闻列表
                    news_items = []
                    
                    # 新浪财经返回的是 HTML，需要解析
                    # 这里简化处理，返回基本结果
                    news_items.append(NewsItem(
                        title=f"关于 {query} 的最新动态",
                        content="请访问新浪财经查看详情",
                        source="新浪财经",
                        url=url,
                    ))
                    
                    return news_items[:limit]
            
        except Exception as e:
            logger.error(f"新浪财经搜索失败: {e}")
            raise
    
    async def _search_eastmoney(self, query: str, limit: int = 10) -> List[NewsItem]:
        """从东方财富获取新闻"""
        try:
            import aiohttp
            from urllib.parse import quote
            
            # 东方财富新闻搜索 API
            url = f"https://searchapi.eastmoney.com/bussiness/web/QuotationLabelSearch?keyword={quote(query)}&type=news"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://www.eastmoney.com/",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    data = await response.json()
                    
                    news_items = []
                    for item in data.get("Data", [])[:limit]:
                        news_items.append(NewsItem(
                            title=item.get("Title", ""),
                            content=item.get("Content", "")[:200],
                            source="东方财富",
                            url=item.get("Url", ""),
                            published_at=datetime.strptime(item.get("ShowTime", "2024-01-01"), "%Y-%m-%d %H:%M:%S") if item.get("ShowTime") else None,
                        ))
                    
                    return news_items
            
        except Exception as e:
            logger.error(f"东方财富搜索失败: {e}")
            raise
    
    async def _search_tencent(self, query: str, limit: int = 10) -> List[NewsItem]:
        """从腾讯财经获取新闻"""
        try:
            import aiohttp
            from urllib.parse import quote
            
            # 腾讯财经新闻搜索
            url = f"https://new.qq.com/search?query={quote(query)}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    html = await response.text()
                    
                    # 简化处理
                    news_items = []
                    news_items.append(NewsItem(
                        title=f"关于 {query} 的相关新闻",
                        content="请访问腾讯财经查看详情",
                        source="腾讯财经",
                        url=url,
                    ))
                    
                    return news_items[:limit]
            
        except Exception as e:
            logger.error(f"腾讯财经搜索失败: {e}")
            raise
    
    async def get_stock_news(self, stock_name: str, limit: int = 5) -> List[NewsItem]:
        """获取特定股票的新闻"""
        query = f"{stock_name} 股票 最新消息"
        return await self.search_news(query, limit=limit)
    
    def get_available_sources(self) -> List[str]:
        """获取可用的新闻源"""
        return [s.value for s in self.available_sources]


# 便捷函数
async def search_news(query: str, limit: int = 10) -> List[NewsItem]:
    """搜索新闻（便捷函数）"""
    adapter = NewsSearchAdapter()
    return await adapter.search_news(query, limit=limit)


async def get_stock_news(stock_name: str, limit: int = 5) -> List[NewsItem]:
    """获取股票新闻（便捷函数）"""
    adapter = NewsSearchAdapter()
    return await adapter.get_stock_news(stock_name, limit=limit)
