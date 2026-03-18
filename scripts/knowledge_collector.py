#!/usr/bin/env python3
"""
知识库统一收集器 - 入口脚本
从多个信息源收集内容，分级处理
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from collectors.knowledge_collector import KnowledgeCollector


def main():
    """主函数"""
    import argparse

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
        print("=" * 60)
        print("运行模式：每日收集（Tier 1 + Tier 4 + Tier 3）")
        print("=" * 60)
        stats = collector.run_daily()
    elif args.mode == "weekly":
        print("=" * 60)
        print("运行模式：每周收集（Tier 2 + Tier 1 + Tier 4）")
        print("=" * 60)
        stats = collector.run_weekly()
    else:
        if args.tier == "1":
            print("=" * 60)
            print("收集 Tier 1（黄金级）")
            print("=" * 60)
            collector.collect_tier1()
        elif args.tier == "2":
            print("=" * 60)
            print("收集 Tier 2（白银级）")
            print("=" * 60)
            collector.collect_tier2()
        elif args.tier == "3":
            print("=" * 60)
            print("收集 Tier 3（青铜级）")
            print("=" * 60)
            collector.collect_tier3()
        elif args.tier == "4":
            print("=" * 60)
            print("收集 Tier 4（石头级 - 反向指标）")
            print("=" * 60)
            collector.collect_tier4()
        else:
            print("=" * 60)
            print("运行模式：完整收集（所有 Tier）")
            print("=" * 60)
            stats = collector.collect_all()

    # 保存统计信息
    if args.save_stats:
        collector.save_stats()

    print("\n" + "=" * 60)
    print("收集完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
