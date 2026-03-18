#!/usr/bin/env python3
"""
Tier 1 收集器 - 黄金级信息源
来源：投资经典书籍、权威财经媒体、券商研报
置信度初始值：0.8
验证标准：3次实战 + 50%胜率
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from .base_collector import BaseCollector


class Tier1Collector(BaseCollector):
    """黄金级信息源收集器（Tier 1）"""

    def __init__(self):
        super().__init__()
        self.tier_config = self.config.get("tier1", {})
        self.confidence = 0.8

    def collect_all(self) -> List[Dict[str, Any]]:
        """
        收集所有 Tier 1 信息源内容

        Returns:
            收集到的信息条目列表
        """
        items = []

        # 1. 收集券商研报
        if self._source_enabled("券商研报"):
            research_items = self.collect_research_reports()
            items.extend(research_items)

        # 2. 收集权威媒体新闻
        if self._source_enabled("权威媒体"):
            news_items = self.collect_authoritative_news()
            items.extend(news_items)

        # 3. 收集书籍（已存在，这里可以添加新书）
        if self._source_enabled("书籍"):
            book_items = self.collect_books()
            items.extend(book_items)

        return items

    def _source_enabled(self, source_name: str) -> bool:
        """检查信息源是否启用"""
        if not self.tier_config.get("enabled", True):
            return False

        for source in self.tier_config.get("sources", []):
            if source.get("name") == source_name:
                return source.get("enabled", True)

        return False

    def collect_research_reports(self) -> List[Dict[str, Any]]:
        """
        收集券商研报

        Returns:
            研报信息条目列表
        """
        self.log("Collecting research reports...")
        items = []

        # 获取研报配置
        report_config = self._get_source_config("券商研报")

        # 如果配置了 API，则从 API 获取
        if report_config.get("type") == "api":
            try:
                api_items = self._fetch_from_eastmoney_api()
                items.extend(api_items)
            except Exception as e:
                self.log(f"Error fetching research reports: {e}")
                # 使用模拟数据作为后备
                items.extend(self._get_mock_research_reports())

        # 否则使用模拟数据
        else:
            items.extend(self._get_mock_research_reports())

        self.log(f"Collected {len(items)} research reports")
        return items

    def _fetch_from_eastmoney_api(self) -> List[Dict[str, Any]]:
        """
        从东方财富 API 获取研报

        Returns:
            研报信息条目列表
        """
        # TODO: 实现实际的 API 调用
        # url = "https://reportapi.eastmoney.com/report/list"
        # params = {
        #     "cb": "datatable",
        #     "industryCode": "*",
        #     "pageSize": 50,
        #     "rating": "买入",
        #     "beginTime": datetime.now().strftime("%Y-%m-%d")
        # }
        # response = requests.get(url, params=params)
        # data = response.json()

        # 目前返回模拟数据
        return self._get_mock_research_reports()

    def _get_mock_research_reports(self) -> List[Dict[str, Any]]:
        """获取模拟研报数据（用于测试）"""
        return [
            {
                "rule": "券商研报：盐湖股份Q1业绩超预期，锂价回升",
                "testable_form": "业绩超预期公告后3日内，股价上涨概率>55%",
                "category": "财报",
                "source": "eastmoney_research",
                "source_tier": "tier1",
                "source_url": "https://reportapi.eastmoney.com/detail/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["research", "earnings", "lithium"]
            },
            {
                "rule": "券商研报：稀土行业供需缺口扩大，价格有望上涨",
                "testable_form": "稀土供需缺口扩大消息发布后5日内，稀土板块上涨概率>60%",
                "category": "行业",
                "source": "eastmoney_research",
                "source_tier": "tier1",
                "source_url": "https://reportapi.eastmoney.com/detail/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["research", "industry", "rare_earth"]
            },
            {
                "rule": "券商研报：新能源汽车销量持续增长，利好锂电产业链",
                "testable_form": "新能源车销量数据发布后，锂电龙头股票上涨概率>55%",
                "category": "行业",
                "source": "eastmoney_research",
                "source_tier": "tier1",
                "source_url": "https://reportapi.eastmoney.com/detail/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["research", "industry", "ev"]
            }
        ]

    def collect_authoritative_news(self) -> List[Dict[str, Any]]:
        """
        收集权威媒体新闻

        Returns:
            新闻信息条目列表
        """
        self.log("Collecting authoritative news...")
        items = []

        # 获取新闻配置
        news_config = self._get_source_config("权威媒体")

        # 如果配置了 RSS 或 API，则获取
        if news_config.get("type") in ["rss", "api"]:
            try:
                # TODO: 实现实际的 RSS/API 调用
                api_items = self._fetch_from_news_api()
                items.extend(api_items)
            except Exception as e:
                self.log(f"Error fetching news: {e}")
                # 使用模拟数据作为后备
                items.extend(self._get_mock_authoritative_news())

        # 否则使用模拟数据
        else:
            items.extend(self._get_mock_authoritative_news())

        self.log(f"Collected {len(items)} news items")
        return items

    def _fetch_from_news_api(self) -> List[Dict[str, Any]]:
        """
        从新闻 API 获取权威媒体新闻

        Returns:
            新闻信息条目列表
        """
        # TODO: 实现实际的 API 调用
        # 财新网 RSS, Reuters API 等
        return self._get_mock_authoritative_news()

    def _get_mock_authoritative_news(self) -> List[Dict[str, Any]]:
        """获取模拟新闻数据（用于测试）"""
        return [
            {
                "rule": "财新网报道：央行降准0.5个百分点，释放流动性",
                "testable_form": "降准消息发布后5日内，大盘上涨概率>55%",
                "category": "宏观",
                "source": "caixin_news",
                "source_tier": "tier1",
                "source_url": "https://www.caixin.com/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["news", "macro", "monetary_policy"]
            },
            {
                "rule": "第一财经：证监会鼓励长期资金入市，提高市场稳定性",
                "testable_form": "长期资金入市政策发布后，大盘波动率下降",
                "category": "政策",
                "source": "yicai_news",
                "source_tier": "tier1",
                "source_url": "https://www.yicai.com/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["news", "policy", "market_stability"]
            },
            {
                "rule": "证券时报：券商行业迎来政策利好，两融标的扩容",
                "testable_form": "券商两融扩容政策发布后，券商板块上涨概率>55%",
                "category": "政策",
                "source": "securitiestimes_news",
                "source_tier": "tier1",
                "source_url": "https://www.stcn.com/xxx",
                "confidence": self.confidence,
                "confidence_threshold": 0.7,
                "tags": ["news", "policy", "brokerage"]
            }
        ]

    def collect_books(self) -> List[Dict[str, Any]]:
        """
        收集投资经典书籍内容

        Returns:
            书籍信息条目列表
        """
        self.log("Collecting books...")
        items = []

        # 加载已有的书籍知识
        book_knowledge_path = (
            Path(__file__).parent.parent.parent / "learning" / "book_knowledge.json"
        )

        if book_knowledge_path.exists():
            with open(book_knowledge_path, 'r', encoding='utf-8') as f:
                book_data = json.load(f)

            # 将书籍知识转换为验证池条目
            for book_id, book_info in book_data.items():
                for point in book_info.get("points", []):
                    item = {
                        "rule": f"{book_info['title']}：{point['point']}",
                        "testable_form": point.get("testable_form", ""),
                        "category": point.get("category", "投资"),
                        "source": f"book_{book_id}",
                        "source_book": book_info["title"],
                        "source_tier": "tier1",
                        "source_url": "",
                        "confidence": self.confidence,
                        "confidence_threshold": 0.7,
                        "tags": ["book", "classic", book_info.get("author", "")]
                    }
                    items.append(item)

        self.log(f"Collected {len(items)} book items")
        return items

    def _get_source_config(self, source_name: str) -> Dict[str, Any]:
        """获取指定信息源的配置"""
        for source in self.tier_config.get("sources", []):
            if source.get("name") == source_name:
                return source
        return {}
