#!/usr/bin/env python3
"""
事件驱动交易 - 飞书通知版
用于 cron 定时任务或手动触发
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from event_trader import EventTrader
from sector_monitor import check_geopolitical_events, GEOPOLITICAL_MAPPING

def auto_detect_and_trade():
    """
    自动检测地缘政治事件并生成买入建议
    用于定时任务
    """
    print("="*70)
    print(f"事件驱动交易扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # 1. 检查新闻缓存中的地缘政治事件
    news_cache_file = PROJECT_ROOT / "data" / "news_cache.json"
    
    if not news_cache_file.exists():
        print("没有新闻缓存数据")
        return None
    
    with open(news_cache_file, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    
    all_news_text = " ".join([
        n.get("title", "") + " " + n.get("summary", "")
        for n in news_data.get("news", [])[-50:]
    ])
    
    # 2. 检测事件
    detected_events = check_geopolitical_events(all_news_text)
    
    if not detected_events:
        print("未检测到地缘政治事件")
        return None
    
    # 3. 对每个检测到的事件生成买入建议
    trader = EventTrader()
    reports = []
    
    # 事件类型映射（sector_monitor → event_trader）
    event_type_map = {
        "war_middle_east": "war_middle_east",
        "war_russia_ukraine": "war_middle_east",  # 统一按战争处理
        "trade_war": "trade_war",
        "pandemic": "pandemic",
    }
    
    for event in detected_events:
        event_type = event_type_map.get(event["type"])
        if not event_type:
            print(f"未知事件类型: {event['type']}")
            continue
        
        # 确定严重程度（基于关键词）
        severity = "medium"
        if any(kw in all_news_text for kw in ["战争", "轰炸", "入侵", "开战"]):
            severity = "high"
        elif any(kw in all_news_text for kw in ["紧张", "对峙", "摩擦"]):
            severity = "low"
        
        # 检测事件
        detected = trader.detect_event(
            event_type,
            severity,
            "新闻监控",
            f"检测到关键词: {event['matched_keyword']}"
        )
        
        if detected:
            # 生成买入建议
            decision = trader.analyze_and_decide(detected["id"])
            if decision:
                report = trader.generate_report(detected["id"])
                reports.append(report)
    
    return reports


def manual_trigger(event_type: str, severity: str = "medium", details: str = ""):
    """
    手动触发事件交易
    
    Args:
        event_type: war_middle_east, trade_war, pandemic, rate_cut
        severity: low, medium, high
        details: 事件详情
    """
    trader = EventTrader()
    
    # 检测事件
    event = trader.detect_event(
        event_type,
        severity,
        "手动触发",
        details
    )
    
    if not event:
        return None
    
    # 生成买入建议
    decision = trader.analyze_and_decide(event["id"])
    if not decision:
        return None
    
    # 生成报告
    report = trader.generate_report(event["id"])
    
    return {
        "event_id": event["id"],
        "report": report
    }


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python event_trader_notify.py auto")
        print("    - 自动检测新闻中的事件并生成买入建议")
        print("")
        print("  python event_trader_notify.py manual <event_type> <severity> [details]")
        print("    - 手动触发事件")
        print("    - event_type: war_middle_east, trade_war, pandemic, rate_cut")
        print("    - severity: low, medium, high")
        print("")
        print("  python event_trader_notify.py report [event_id]")
        print("    - 查看买入建议报告")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "auto":
        reports = auto_detect_and_trade()
        if reports:
            for report in reports:
                print("\n" + "="*70)
                print(report)
        else:
            print("\n无买入建议")
    
    elif command == "manual":
        if len(sys.argv) < 4:
            print("错误: 需要参数 <event_type> <severity>")
            sys.exit(1)
        
        event_type = sys.argv[2]
        severity = sys.argv[3]
        details = sys.argv[4] if len(sys.argv) > 4 else "手动触发"
        
        result = manual_trigger(event_type, severity, details)
        if result:
            print("\n" + "="*70)
            print(result["report"])
            print(f"\n事件ID: {result['event_id']}")
        else:
            print("生成买入建议失败")
    
    elif command == "report":
        trader = EventTrader()
        event_id = sys.argv[2] if len(sys.argv) > 2 else None
        report = trader.generate_report(event_id)
        print(report)
    
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
