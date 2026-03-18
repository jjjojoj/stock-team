#!/usr/bin/env python3
"""
知识库统一收集器
从多个信息源收集内容，分级处理
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from .tier1_collector import Tier1Collector
from .tier2_collector import Tier2Collector
from .tier3_collector import Tier3Collector
from .tier4_collector import Tier4Collector


class KnowledgeCollector:
    """知识库统一收集器"""

    def __init__(self):
        """初始化收集器"""
        self.tier1 = Tier1Collector()
        self.tier2 = Tier2Collector()
        self.tier3 = Tier3Collector()
        self.tier4 = Tier4Collector()

        self.stats = {
            "tier1": {},
            "tier2": {},
            "tier3": {},
            "tier4": {},
            "total": {
                "collected": 0,
                "added": 0,
                "skipped": 0
            }
        }

    def log(self, message: str) -> None:
        """记录日志"""
        print(f"[KnowledgeCollector] {message}")

    def collect_tier1(self) -> Dict[str, int]:
        """
        收集 Tier 1 信息源（黄金级）
        """
        self.log("=" * 50)
        self.log("Collecting Tier 1 (Gold) - Direct Admission")
        self.log("=" * 50)

        stats = self.tier1.collect_and_add()
        self.stats["tier1"] = stats

        self.log(f"Tier 1 collected: {stats.get('total_collected', 0)}")
        self.log(f"Tier 1 added: {stats.get('total_added', 0)}")
        self.log(f"Tier 1 skipped: {stats.get('total_skipped', 0)}")

        return stats

    def collect_tier2(self) -> Dict[str, int]:
        """
        收集 Tier 2 信息源（白银级）
        """
        self.log("=" * 50)
        self.log("Collecting Tier 2 (Silver) - Needs Verification")
        self.log("=" * 50)

        stats = self.tier2.collect_and_add()
        self.stats["tier2"] = stats

        self.log(f"Tier 2 collected: {stats.get('total_collected', 0)}")
        self.log(f"Tier 2 added: {stats.get('total_added', 0)}")
        self.log(f"Tier 2 skipped: {stats.get('total_skipped', 0)}")

        return stats

    def collect_tier3(self) -> Dict[str, int]:
        """
        收集 Tier 3 信息源（青铜级）
        """
        self.log("=" * 50)
        self.log("Collecting Tier 3 (Bronze) - Strict Verification")
        self.log("=" * 50)

        stats = self.tier3.collect_and_add()
        self.stats["tier3"] = stats

        self.log(f"Tier 3 collected: {stats.get('total_collected', 0)}")
        self.log(f"Tier 3 added: {stats.get('total_added', 0)}")
        self.log(f"Tier 3 skipped: {stats.get('total_skipped', 0)}")

        return stats

    def collect_tier4(self) -> List[Dict[str, Any]]:
        """
        收集 Tier 4 信息源（石头级 - 反向指标）
        """
        self.log("=" * 50)
        self.log("Collecting Tier 4 (Stone) - Reverse Indicator")
        self.log("=" * 50)

        items = self.tier4.collect_all()
        self.stats["tier4"]["collected"] = len(items)

        self.log(f"Tier 4 collected: {len(items)} sentiment indicators")

        # 处理情绪信号
        sentiment_data = [item for item in items if item.get("type") == "sentiment"]
        signals = self.tier4.process_sentiment_signals(sentiment_data)
        summary = self.tier4.get_sentiment_summary(sentiment_data)

        if signals:
            self.log(f"Sentiment signals: {signals}")
        if summary:
            self.log(f"Sentiment summary: {summary['overall_sentiment']} - {summary['signal']}")

        return items

    def collect_all(self) -> Dict[str, Any]:
        """
        收集所有信息源
        """
        self.log("Starting knowledge collection from all sources...")

        # 收集各 Tier
        self.collect_tier1()
        self.collect_tier2()
        self.collect_tier3()
        self.collect_tier4()

        # 计算总计
        total_collected = (
            self.stats["tier1"].get("total_collected", 0) +
            self.stats["tier2"].get("total_collected", 0) +
            self.stats["tier3"].get("total_collected", 0) +
            self.stats["tier4"].get("collected", 0)
        )

        total_added = (
            self.stats["tier1"].get("total_added", 0) +
            self.stats["tier2"].get("total_added", 0) +
            self.stats["tier3"].get("total_added", 0)
        )

        total_skipped = (
            self.stats["tier1"].get("total_skipped", 0) +
            self.stats["tier2"].get("total_skipped", 0) +
            self.stats["tier3"].get("total_skipped", 0)
        )

        self.stats["total"] = {
            "collected": total_collected,
            "added": total_added,
            "skipped": total_skipped
        }

        self.log("=" * 50)
        self.log("Collection Summary")
        self.log("=" * 50)
        self.log(f"Total collected: {total_collected}")
        self.log(f"Total added to pool: {total_added}")
        self.log(f"Total skipped (duplicates): {total_skipped}")
        self.log(f"Last run: {datetime.now().isoformat()}")

        return self.stats

    def run_daily(self) -> Dict[str, Any]:
        """
        每日任务
        1. 收集 Tier 1（每天）
        2. 更新 Tier 4（情绪指数）
        """
        self.log("Running daily collection task...")

        # 每日收集 Tier 1
        self.collect_tier1()

        # 更新 Tier 4 情绪指标
        self.collect_tier4()

        # 只收集 Tier 3（如果有触发关键词）
        self.collect_tier3()

        return self.stats

    def run_weekly(self) -> Dict[str, Any]:
        """
        每周任务
        1. 收集 Tier 2（年报、研报）
        2. 清理过期验证规则
        """
        self.log("Running weekly collection task...")

        # 每周收集 Tier 2
        self.collect_tier2()

        # 收集 Tier 1（确保不遗漏）
        self.collect_tier1()

        # 收集 Tier 4 情绪指标
        self.collect_tier4()

        return self.stats

    def save_stats(self) -> None:
        """保存统计信息"""
        stats_path = Path(__file__).parent.parent.parent / "learning" / "collector_stats.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump({
                "stats": self.stats,
                "last_run": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

        self.log(f"Stats saved to {stats_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="知识库统一收集器")
    parser.add_argument(
        "--tier",
        type=str,
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="指定收集的 Tier 等级"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["daily", "weekly", "full"],
        default="full",
        help="运行模式"
    )
    parser.add_argument(
        "--save-stats",
        action="store_true",
        help="保存统计信息"
    )

    args = parser.parse_args()

    # 创建收集器
    collector = KnowledgeCollector()

    # 根据参数运行
    if args.mode == "daily":
        stats = collector.run_daily()
    elif args.mode == "weekly":
        stats = collector.run_weekly()
    else:
        if args.tier == "1":
            collector.collect_tier1()
        elif args.tier == "2":
            collector.collect_tier2()
        elif args.tier == "3":
            collector.collect_tier3()
        elif args.tier == "4":
            collector.collect_tier4()
        else:
            stats = collector.collect_all()

    # 保存统计信息
    if args.save_stats:
        collector.save_stats()


if __name__ == "__main__":
    main()
