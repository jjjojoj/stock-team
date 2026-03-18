#!/usr/bin/env python3
"""
新闻监控系统
多源新闻聚合 + 事件影响分析
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import re

# 新闻数据存储路径
NEWS_DB_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/data/news/")
EVENT_DB_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/data/events/")

# 事件影响映射
EVENT_IMPACT_MAP = {
    # 战争/冲突类
    "战争": {
        "positive": ["军工", "黄金", "石油", "战略金属", "稀土", "钨", "钼"],
        "negative": ["物流", "航空", "旅游", "出口"],
        "keywords": ["战争", "军事打击", "冲突", "开战", "入侵"],
        "duration": "1-3个月",
        "severity": "高",
    },
    "制裁": {
        "positive": ["国产替代", "半导体", "稀土"],
        "negative": ["出口", "科技"],
        "keywords": ["制裁", "封锁", "禁运"],
        "duration": "长期",
        "severity": "高",
    },
    
    # 政策类
    "降息": {
        "positive": ["房地产", "基建", "高负债企业"],
        "negative": ["银行"],
        "keywords": ["降息", "利率下调", "LPR下调"],
        "duration": "3-6个月",
        "severity": "中",
    },
    "新能源政策": {
        "positive": ["光伏", "锂电", "风电", "新能源车"],
        "negative": ["火电", "煤炭"],
        "keywords": ["新能源", "光伏", "锂电", "碳中和", "双碳"],
        "duration": "长期",
        "severity": "高",
    },
    "半导体政策": {
        "positive": ["芯片设计", "芯片制造", "半导体设备", "半导体材料"],
        "negative": [],
        "keywords": ["半导体", "芯片", "集成电路", "国产替代"],
        "duration": "长期",
        "severity": "高",
    },
    
    # 经济数据类
    "通胀超预期": {
        "positive": ["黄金", "资源股"],
        "negative": ["成长股", "科技股"],
        "keywords": ["CPI超预期", "通胀", "物价上涨"],
        "duration": "短期",
        "severity": "中",
    },
    
    # 行业类
    "商品涨价": {
        "positive": ["资源股", "有色"],
        "negative": ["制造业"],
        "keywords": ["涨价", "价格上调", "提价"],
        "duration": "中期",
        "severity": "中",
    },
    
    # 公司类
    "业绩暴雷": {
        "positive": [],
        "negative": ["相关股票"],
        "keywords": ["业绩下滑", "亏损", "商誉减值", "业绩预警"],
        "duration": "短期",
        "severity": "高",
    },
}

# 股票-行业映射
STOCK_INDUSTRY_MAP = {
    # 军工
    "中航沈飞": "军工",
    "中航西飞": "军工",
    "航天电子": "军工",
    
    # 战略金属
    "北方稀土": "稀土",
    "五矿稀土": "稀土",
    "厦门钨业": "钨",
    "金钼股份": "钼",
    "贵研铂业": "铂族金属",
    
    # 黄金
    "紫金矿业": "黄金",
    "山东黄金": "黄金",
    "中金黄金": "黄金",
    
    # 石油
    "中国石油": "石油",
    "中国石化": "石油",
    "中国海油": "石油",
    
    # 物流
    "中远海控": "物流",
    "顺丰控股": "物流",
    
    # 航空
    "中国国航": "航空",
    "南方航空": "航空",
    "东方航空": "航空",
    
    # 半导体
    "中芯国际": "芯片制造",
    "华润微": "芯片制造",
    "中微公司": "半导体设备",
    "北方华创": "半导体设备",
    
    # 新能源
    "隆基绿能": "光伏",
    "通威股份": "光伏",
    "宁德时代": "锂电",
    "比亚迪": "新能源车",
}

def ensure_data_dirs():
    """确保数据目录存在"""
    os.makedirs(NEWS_DB_PATH, exist_ok=True)
    os.makedirs(EVENT_DB_PATH, exist_ok=True)

def classify_news(title: str, content: str = "") -> Dict:
    """
    分类新闻并判断影响
    """
    text = f"{title} {content}".lower()
    
    # 匹配事件类型
    for event_type, event_info in EVENT_IMPACT_MAP.items():
        keywords = event_info["keywords"]
        
        # 检查是否包含关键词
        if any(kw in text for kw in keywords):
            return {
                "event_type": event_type,
                "positive_sectors": event_info["positive"],
                "negative_sectors": event_info["negative"],
                "duration": event_info["duration"],
                "severity": event_info["severity"],
                "matched_keywords": [kw for kw in keywords if kw in text],
            }
    
    return {
        "event_type": "未知",
        "positive_sectors": [],
        "negative_sectors": [],
        "duration": "未知",
        "severity": "低",
        "matched_keywords": [],
    }

def get_affected_stocks(sectors: List[str]) -> List[str]:
    """
    根据受影响行业获取相关股票
    """
    stocks = []
    
    for stock, industry in STOCK_INDUSTRY_MAP.items():
        if industry in sectors:
            stocks.append(stock)
    
    return stocks

def analyze_news_impact(title: str, content: str = "", source: str = "未知") -> Dict:
    """
    分析新闻影响
    """
    # 分类新闻
    classification = classify_news(title, content)
    
    # 获取受影响股票
    positive_stocks = get_affected_stocks(classification["positive_sectors"])
    negative_stocks = get_affected_stocks(classification["negative_sectors"])
    
    return {
        "title": title,
        "content": content[:500],  # 截取前500字符
        "source": source,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "event_type": classification["event_type"],
        "severity": classification["severity"],
        "duration": classification["duration"],
        "positive_sectors": classification["positive_sectors"],
        "negative_sectors": classification["negative_sectors"],
        "positive_stocks": positive_stocks,
        "negative_stocks": negative_stocks,
        "matched_keywords": classification["matched_keywords"],
    }

def save_news_analysis(analysis: Dict):
    """
    保存新闻分析结果
    """
    ensure_data_dirs()
    
    # 保存到日期文件
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"news_analysis_{date_str}.json"
    filepath = os.path.join(NEWS_DB_PATH, filename)
    
    # 读取现有数据
    data = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    
    # 添加新数据
    data.append(analysis)
    
    # 保存
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 新闻分析已保存: {filepath}")

def format_impact_report(analysis: Dict) -> str:
    """
    格式化影响报告
    """
    report = []
    report.append("=" * 70)
    report.append("📰 新闻影响分析")
    report.append("=" * 70)
    report.append(f"标题: {analysis['title']}")
    report.append(f"来源: {analysis['source']}")
    report.append(f"时间: {analysis['time']}")
    report.append(f"事件类型: {analysis['event_type']}")
    report.append(f"严重程度: {analysis['severity']}")
    report.append(f"持续时长: {analysis['duration']}")
    report.append(f"匹配关键词: {', '.join(analysis['matched_keywords'])}")
    
    if analysis['positive_sectors']:
        report.append("\n✅ 受益板块:")
        for sector in analysis['positive_sectors']:
            report.append(f"  - {sector}")
    
    if analysis['positive_stocks']:
        report.append("\n✅ 受益股票:")
        for stock in analysis['positive_stocks']:
            report.append(f"  - {stock}")
    
    if analysis['negative_sectors']:
        report.append("\n❌ 受损板块:")
        for sector in analysis['negative_sectors']:
            report.append(f"  - {sector}")
    
    if analysis['negative_stocks']:
        report.append("\n❌ 受损股票:")
        for stock in analysis['negative_stocks']:
            report.append(f"  - {stock}")
    
    report.append("=" * 70)
    
    return "\n".join(report)

def verify_war_news():
    """
    测试：美伊战争新闻分析
    """
    title = "美国对伊朗发动军事打击，中东局势紧张"
    content = """
    据路透社报道，美国于2月28日对伊朗发动了军事打击，目标是伊朗的核设施。
    这是继上个月美伊关系恶化后的首次军事行动。
    国际油价应声上涨，布伦特原油突破90美元/桶。
    黄金价格也出现大幅上涨，避险情绪升温。
    """
    
    analysis = analyze_news_impact(title, content, "路透社")
    report = format_impact_report(analysis)
    
    print(report)
    
    # 保存分析结果
    save_news_analysis(analysis)
    
    return analysis

def check_recent_news():
    """
    检查最近1小时的新闻
    分析新闻对持仓的影响
    生成简报
    """
    print("=" * 70)
    print("📰 新闻监控检查")
    print("=" * 70)

    # 检查最近1小时的新闻文件
    ensure_data_dirs()

    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)

    # 查找最近的新闻文件
    news_files = []
    for filename in os.listdir(NEWS_DB_PATH):
        if filename.startswith("news_analysis_") and filename.endswith(".json"):
            filepath = os.path.join(NEWS_DB_PATH, filename)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mtime >= one_hour_ago:
                news_files.append(filepath)

    if not news_files:
        print("✅ 最近1小时无新闻数据")
        return []

    # 读取和分析新闻
    recent_analyses = []
    for filepath in news_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                analyses = json.load(f)
                for analysis in analyses:
                    recent_analyses.append(analysis)
        except Exception as e:
            print(f"⚠️ 读取文件失败 {filepath}: {e}")

    # 按时间排序
    recent_analyses.sort(key=lambda x: x.get("time", ""), reverse=True)

    print(f"\n找到 {len(recent_analyses)} 条新闻")

    # 分析对持仓的影响
    positions_file = os.path.join(os.path.dirname(NEWS_DB_PATH), "..", "config", "positions.json")
    positions = []
    if os.path.exists(positions_file):
        with open(positions_file, 'r', encoding='utf-8') as f:
            positions_data = json.load(f)
            positions = list(positions_data.keys())

    # 生成影响报告
    impact_summary = {
        "positive_impact": [],
        "negative_impact": [],
        "neutral": [],
    }

    for analysis in recent_analyses:
        print(f"\n---")
        print(f"标题: {analysis['title']}")
        print(f"时间: {analysis['time']}")
        print(f"类型: {analysis['event_type']}")

        # 检查对持仓的影响
        affected_positions = []
        for pos in positions:
            pos_name = ""
            # 查找股票名称
            for stock_name, industry in STOCK_INDUSTRY_MAP.items():
                if pos in stock_name or pos == stock_name.split('.')[0]:
                    pos_name = stock_name
                    break

            if pos_name:
                if pos_name in analysis.get("positive_stocks", []):
                    affected_positions.append(f"✅ {pos_name} (受益)")
                elif pos_name in analysis.get("negative_stocks", []):
                    affected_positions.append(f"❌ {pos_name} (受损)")

        if affected_positions:
            print(f"持仓影响: {', '.join(affected_positions)}")

        # 分类汇总
        has_positive = any(pos in positions for pos in analysis.get("positive_stocks", []))
        has_negative = any(pos in positions for pos in analysis.get("negative_stocks", []))

        if has_positive:
            impact_summary["positive_impact"].append({
                "title": analysis['title'],
                "time": analysis['time'],
                "stocks": [s for s in analysis['positive_stocks'] if s in STOCK_INDUSTRY_MAP],
            })
        elif has_negative:
            impact_summary["negative_impact"].append({
                "title": analysis['title'],
                "time": analysis['time'],
                "stocks": [s for s in analysis['negative_stocks'] if s in STOCK_INDUSTRY_MAP],
            })
        else:
            impact_summary["neutral"].append({
                "title": analysis['title'],
                "time": analysis['time'],
            })

    # 生成简报
    print("\n" + "=" * 70)
    print("📋 新闻影响简报")
    print("=" * 70)

    if impact_summary["positive_impact"]:
        print(f"\n✅ 利好新闻 ({len(impact_summary['positive_impact'])}条):")
        for item in impact_summary["positive_impact"]:
            print(f"  - {item['title']}")
            print(f"    受益股票: {', '.join(item['stocks']) if item['stocks'] else '无持仓'}")

    if impact_summary["negative_impact"]:
        print(f"\n❌ 利空新闻 ({len(impact_summary['negative_impact'])}条):")
        for item in impact_summary["negative_impact"]:
            print(f"  - {item['title']}")
            print(f"    受损股票: {', '.join(item['stocks']) if item['stocks'] else '无持仓'}")

    if impact_summary["neutral"]:
        print(f"\n⚪ 其他新闻 ({len(impact_summary['neutral'])}条):")
        for item in impact_summary["neutral"][:3]:  # 只显示前3条
            print(f"  - {item['title']}")

    print("\n" + "=" * 70)

    # 尝试发送飞书通知
    try:
        from feishu_notifier import send_feishu_message

        notification_content = []
        if impact_summary["positive_impact"]:
            notification_content.append(f"✅ 利好 {len(impact_summary['positive_impact'])} 条")
            for item in impact_summary["positive_impact"][:2]:
                stocks = ', '.join([s for s in item['stocks'] if s in STOCK_INDUSTRY_MAP][:2])
                notification_content.append(f"  • {item['title'][:20]}... ({stocks})")

        if impact_summary["negative_impact"]:
            notification_content.append(f"\n❌ 利空 {len(impact_summary['negative_impact'])} 条")
            for item in impact_summary["negative_impact"][:2]:
                stocks = ', '.join([s for s in item['stocks'] if s in STOCK_INDUSTRY_MAP][:2])
                notification_content.append(f"  • {item['title'][:20]}... ({stocks})")

        if notification_content:
            send_feishu_message(
                title="📰 新闻监控简报",
                content='\n'.join(notification_content),
                level='info'
            )
    except Exception as e:
        print(f"⚠️ 飞书通知发送失败: {e}")

    return recent_analyses

def main():
    if len(sys.argv) < 2:
        print("用法: python3 news_monitor.py <命令>")
        print("命令:")
        print("  verify      测试新闻分析（美伊战争）")
        print("  analyze     分析新闻（需要传入标题和内容）")
        print("  check       检查最近1小时新闻并分析持仓影响")
        sys.exit(1)

    command = sys.argv[1]

    if command == "verify":
        verify_war_news()

    elif command == "analyze":
        if len(sys.argv) < 3:
            print("用法: python3 news_monitor.py analyze <标题>")
            sys.exit(1)

        title = sys.argv[2]
        content = sys.argv[3] if len(sys.argv) >= 4 else ""

        analysis = analyze_news_impact(title, content)
        report = format_impact_report(analysis)
        print(report)

    elif command == "check":
        check_recent_news()

    else:
        print("未知命令")
        sys.exit(1)

if __name__ == "__main__":
    main()
