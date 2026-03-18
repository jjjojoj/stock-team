#!/usr/bin/env python3
"""
Tier 4 收集器 - 石头级信息源（反向指标）
来源：散户情绪指数、市场热度
处理方式：不进入验证池，直接作为反向指标
用途：
- 情绪极度乐观 → 卖出信号
- 情绪极度悲观 → 买入信号
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any

from .base_collector import BaseCollector


class Tier4Collector(BaseCollector):
    """石头级信息源收集器（Tier 4 - 反向指标）"""

    def __init__(self):
        super().__init__()
        self.tier_config = self.config.get("tier4", {})
        self.sentiment_keywords = {
            "positive": ["利好", "涨停", "牛股", "大涨", "主力进场", "起飞", "暴涨", "满仓", "抄底"],
            "negative": ["利空", "跌停", "垃圾", "大跌", "主力出货", "暴跌", "清仓", "割肉", "崩盘"]
        }

    def collect_all(self) -> List[Dict[str, Any]]:
        """
        收集所有 Tier 4 信息源内容（情绪指标）

        Returns:
            情绪指标列表（不进入验证池，直接使用）
        """
        items = []

        # 1. 收集散户情绪
        if self._source_enabled("散户情绪"):
            sentiment_items = self.collect_retail_sentiment()
            items.extend(sentiment_items)

        # 2. 收集市场热度
        if self._source_enabled("市场热度"):
            heat_items = self.collect_market_heat()
            items.extend(heat_items)

        return items

    def _source_enabled(self, source_name: str) -> bool:
        """检查信息源是否启用"""
        if not self.tier_config.get("enabled", True):
            return False

        for source in self.tier_config.get("sources", []):
            if source.get("name") == source_name:
                return source.get("enabled", True)

        return False

    def collect_retail_sentiment(self, symbol: str = "000792") -> List[Dict[str, Any]]:
        """
        收集散户情绪

        Args:
            symbol: 股票代码（默认盐湖股份 000792）

        Returns:
            情绪指标列表
        """
        self.log(f"Collecting retail sentiment for {symbol}...")
        items = []

        # 获取散户情绪配置
        sentiment_config = self._get_source_config("散户情绪")

        # 如果配置了 API，则获取
        if sentiment_config.get("type") == "api":
            try:
                api_items = self._fetch_from_guba_api(symbol)
                items.extend(api_items)
            except Exception as e:
                self.log(f"Error fetching retail sentiment: {e}")
                # 使用模拟数据作为后备
                items.extend(self._get_mock_retail_sentiment(symbol))

        # 否则使用模拟数据
        else:
            items.extend(self._get_mock_retail_sentiment(symbol))

        self.log(f"Collected {len(items)} retail sentiment items")
        return items

    def _fetch_from_guba_api(self, symbol: str) -> List[Dict[str, Any]]:
        """
        从东方财富股吧 API 获取散户情绪

        Args:
            symbol: 股票代码

        Returns:
            情绪指标列表
        """
        # TODO: 实现实际的 API 调用
        # url = f"https://guba.eastmoney.com/list,{symbol}.html"
        # response = requests.get(url)
        # html = response.text
        # 提取帖子标题
        # 情绪分析
        return self._get_mock_retail_sentiment(symbol)

    def _analyze_sentiment_from_text(self, text: str) -> Dict[str, Any]:
        """
        从文本分析情绪

        Args:
            text: 待分析的文本

        Returns:
            情绪分析结果
        """
        positive_count = sum(1 for kw in self.sentiment_keywords["positive"] if kw in text)
        negative_count = sum(1 for kw in self.sentiment_keywords["negative"] if kw in text)

        total = positive_count + negative_count

        if total == 0:
            return {
                "sentiment": "中性",
                "score": 0.0,
                "positive_count": 0,
                "negative_count": 0
            }

        sentiment_score = (positive_count - negative_count) / total

        if sentiment_score > 0.5:
            sentiment = "极度乐观"
            signal = "卖出"  # 反向信号
        elif sentiment_score > 0.2:
            sentiment = "乐观"
            signal = "谨慎"
        elif sentiment_score < -0.5:
            sentiment = "极度悲观"
            signal = "买入"  # 反向信号
        elif sentiment_score < -0.2:
            sentiment = "悲观"
            signal = "关注"
        else:
            sentiment = "中性"
            signal = "观望"

        return {
            "sentiment": sentiment,
            "score": sentiment_score,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "signal": signal
        }

    def _get_mock_retail_sentiment(self, symbol: str) -> List[Dict[str, Any]]:
        """获取模拟散户情绪数据（用于测试）"""
        return [
            {
                "type": "sentiment",
                "symbol": symbol,
                "source": "eastmoney_guba",
                "sentiment": "极度乐观",
                "score": 0.7,
                "positive_count": 15,
                "negative_count": 2,
                "signal": "卖出",
                "analysis": "股吧情绪极度乐观，散户普遍看涨，可能是反向卖出信号",
                "timestamp": datetime.now().isoformat()
            },
            {
                "type": "sentiment",
                "symbol": symbol,
                "source": "eastmoney_guba",
                "sentiment": "极度悲观",
                "score": -0.6,
                "positive_count": 3,
                "negative_count": 12,
                "signal": "买入",
                "analysis": "股吧情绪极度悲观，散户恐慌，可能是反向买入信号",
                "timestamp": datetime.now().isoformat()
            },
            {
                "type": "sentiment",
                "symbol": symbol,
                "source": "eastmoney_guba",
                "sentiment": "中性",
                "score": 0.1,
                "positive_count": 5,
                "negative_count": 4,
                "signal": "观望",
                "analysis": "股吧情绪中性，多空平衡",
                "timestamp": datetime.now().isoformat()
            }
        ]

    def collect_market_heat(self) -> List[Dict[str, Any]]:
        """
        收集市场热度指数

        Returns:
            市场热度指标列表
        """
        self.log("Collecting market heat...")
        items = []

        # 获取市场热度配置
        heat_config = self._get_source_config("市场热度")

        # 如果配置了 API，则获取
        if heat_config.get("type") == "api":
            try:
                # 收集百度指数
                baidu_items = self._fetch_from_baidu_index()
                items.extend(baidu_items)

                # 收集新开户数
                account_items = self._fetch_from_account_data()
                items.extend(account_items)

                # 收集融资余额
                margin_items = self._fetch_from_margin_data()
                items.extend(margin_items)
            except Exception as e:
                self.log(f"Error fetching market heat: {e}")
                # 使用模拟数据作为后备
                items.extend(self._get_mock_market_heat())

        # 否则使用模拟数据
        else:
            items.extend(self._get_mock_market_heat())

        self.log(f"Collected {len(items)} market heat items")
        return items

    def _fetch_from_baidu_index(self) -> List[Dict[str, Any]]:
        """
        从百度指数获取搜索热度

        Returns:
            搜索热度指标列表
        """
        # TODO: 实现实际的 API 调用
        # 百度指数 API
        return []

    def _fetch_from_account_data(self) -> List[Dict[str, Any]]:
        """
        获取新开户数数据

        Returns:
            新开户数指标列表
        """
        # TODO: 实现实际的 API 调用
        return []

    def _fetch_from_margin_data(self) -> List[Dict[str, Any]]:
        """
        获取融资余额数据

        Returns:
            融资余额指标列表
        """
        # TODO: 实现实际的 API 调用
        return self._get_mock_market_heat()

    def _get_mock_market_heat(self) -> List[Dict[str, Any]]:
        """获取模拟市场热度数据（用于测试）"""
        return [
            {
                "type": "market_heat",
                "source": "baidu_index",
                "keyword": "股票",
                "index": 8500,
                "change": "+15%",
                "heat_level": "高",
                "signal": "谨慎",
                "analysis": "搜索热度大幅上升，市场情绪过热",
                "timestamp": datetime.now().isoformat()
            },
            {
                "type": "market_heat",
                "source": "new_accounts",
                "count": 150000,
                "change": "+25%",
                "heat_level": "极高",
                "signal": "卖出",
                "analysis": "新开户数激增，散户大量入场，可能是顶",
                "timestamp": datetime.now().isoformat()
            },
            {
                "type": "market_heat",
                "source": "margin_balance",
                "balance": "1.8万亿",
                "change": "+10%",
                "heat_level": "高",
                "signal": "谨慎",
                "analysis": "融资余额持续上升，杠杆资金活跃",
                "timestamp": datetime.now().isoformat()
            }
        ]

    def process_sentiment_signals(self, sentiment_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        处理情绪信号，生成交易建议

        Args:
            sentiment_data: 情绪数据列表

        Returns:
            交易建议字典 {symbol: signal}
        """
        signals = {}

        for item in sentiment_data:
            if item.get("type") == "sentiment":
                symbol = item.get("symbol")
                signal = item.get("signal")
                if symbol and signal:
                    signals[symbol] = signal

        return signals

    def get_sentiment_summary(self, sentiment_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成情绪汇总

        Args:
            sentiment_data: 情绪数据列表

        Returns:
            情绪汇总字典
        """
        if not sentiment_data:
            return {
                "overall_sentiment": "中性",
                "signal": "观望",
                "count": 0
            }

        # 计算平均情绪分数
        scores = [item.get("score", 0) for item in sentiment_data if "score" in item]
        avg_score = sum(scores) / len(scores) if scores else 0

        # 判断整体情绪
        if avg_score > 0.5:
            overall = "极度乐观"
            signal = "卖出"
        elif avg_score > 0.2:
            overall = "乐观"
            signal = "谨慎"
        elif avg_score < -0.5:
            overall = "极度悲观"
            signal = "买入"
        elif avg_score < -0.2:
            overall = "悲观"
            signal = "关注"
        else:
            overall = "中性"
            signal = "观望"

        return {
            "overall_sentiment": overall,
            "signal": signal,
            "avg_score": avg_score,
            "count": len(sentiment_data),
            "timestamp": datetime.now().isoformat()
        }

    def _get_source_config(self, source_name: str) -> Dict[str, Any]:
        """获取指定信息源的配置"""
        for source in self.tier_config.get("sources", []):
            if source.get("name") == source_name:
                return source
        return {}
