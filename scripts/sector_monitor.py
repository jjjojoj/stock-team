#!/usr/bin/env python3
"""
行业热点监控脚本
功能：
1. 扫描各板块涨跌幅
2. 监控资金流向
3. 检测行业异动
4. 地缘政治事件 → 行业映射
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import akshare as ak
except ImportError:
    print("错误: 需要安装 akshare: pip install akshare")
    sys.exit(1)

DATA_DIR = Path(__file__).parent.parent / "data"
SECTOR_FILE = DATA_DIR / "sector_monitor.json"

# 地缘政治事件 → 行业映射
GEOPOLITICAL_MAPPING = {
    "war_middle_east": {
        "name": "中东冲突",
        "benefit_sectors": ["石油开采", "天然气", "油服", "黄金", "军工"],
        "hurt_sectors": ["航空", "航运", "旅游"],
        "keywords": ["中东", "伊朗", "以色列", "胡塞", "红海", "轰炸", "战争"]
    },
    "war_russia_ukraine": {
        "name": "俄乌冲突",
        "benefit_sectors": ["石油", "天然气", "粮食", "化肥", "黄金"],
        "hurt_sectors": [],
        "keywords": ["俄罗斯", "乌克兰", "北约"]
    },
    "trade_war": {
        "name": "贸易战",
        "benefit_sectors": ["农业", "国产替代", "稀土", "半导体"],
        "hurt_sectors": ["出口制造"],
        "keywords": ["关税", "制裁", "贸易战", "脱钩"]
    },
    "pandemic": {
        "name": "疫情",
        "benefit_sectors": ["医药", "疫苗", "核酸检测", "在线办公", "生鲜电商"],
        "hurt_sectors": ["旅游", "餐饮", "航空", "影院"],
        "keywords": ["疫情", "病毒", "封控", "感染"]
    }
}

# 行业 → 代表性股票映射
SECTOR_STOCKS = {
    "石油开采": ["sh.600028", "sz.000552", "sh.601857"],  # 中国石化、泰山石油、中国石油
    "天然气": ["sh.603393", "sz.000591", "sh.600256"],  # 新天然气、太阳能、广汇能源
    "油服": ["sh.600871", "sz.002353", "sh.601808"],  # 石油工程、杰瑞股份、中海油服
    "黄金": ["sh.600547", "sz.002155", "sh.601899"],  # 山东黄金、辰州矿业、紫金矿业
    "军工": ["sh.600893", "sz.000768", "sh.600150"],  # 航发动力、中航飞机、中国船舶
    "电气设备": ["sz.300750", "sh.600410", "sz.002129"],  # 宁德时代、华仪电气、中环股份
    "新能源": ["sz.300274", "sh.601012", "sz.002594"],  # 阳光电源、隆基绿能、比亚迪
}

def get_sector_performance():
    """获取板块涨跌幅数据"""
    try:
        # 获取行业板块数据
        df = ak.stock_board_industry_name_em()
        
        sectors = []
        for _, row in df.head(50).iterrows():  # 取前50个板块
            sectors.append({
                "name": row["板块名称"],
                "change_pct": float(row.get("涨跌幅", 0)),
                "leading_stock": row.get("领涨股票", ""),
                "amount": float(row.get("总市值", 0)),
            })
        
        # 按涨跌幅排序
        sectors.sort(key=lambda x: x["change_pct"], reverse=True)
        
        return sectors
    except Exception as e:
        print(f"获取板块数据失败: {e}")
        return []

def detect_hot_sectors(sectors, threshold=3.0):
    """检测热点板块（涨幅超过阈值）"""
    hot = []
    for sector in sectors:
        if sector["change_pct"] >= threshold:
            hot.append({
                "name": sector["name"],
                "change_pct": sector["change_pct"],
                "leading_stock": sector["leading_stock"],
                "related_stocks": SECTOR_STOCKS.get(sector["name"], [])
            })
    return hot

def check_geopolitical_events(news_text):
    """检查新闻中是否包含地缘政治事件"""
    events_detected = []
    
    for event_type, event_info in GEOPOLITICAL_MAPPING.items():
        for keyword in event_info["keywords"]:
            if keyword in news_text:
                events_detected.append({
                    "type": event_type,
                    "name": event_info["name"],
                    "benefit_sectors": event_info["benefit_sectors"],
                    "hurt_sectors": event_info["hurt_sectors"],
                    "matched_keyword": keyword
                })
                break
    
    return events_detected

def scan(args):
    """扫描行业热点"""
    print("正在扫描行业板块...")
    
    # 1. 获取板块数据
    sectors = get_sector_performance()
    
    if not sectors:
        print("无法获取板块数据")
        return
    
    # 2. 检测热点板块
    hot_sectors = detect_hot_sectors(sectors)
    
    # 3. 保存结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "hot_sectors": hot_sectors,
        "all_sectors": sectors[:20],  # 保存前20个板块
    }
    
    with open(SECTOR_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 4. 输出报告
    print("\n" + "="*60)
    print("📊 行业热点扫描报告")
    print("="*60)
    
    if hot_sectors:
        print(f"\n🔥 今日热点板块（涨幅 > 3%）: {len(hot_sectors)} 个\n")
        for i, sector in enumerate(hot_sectors, 1):
            print(f"{i}. {sector['name']}: +{sector['change_pct']:.2f}%")
            print(f"   领涨股: {sector['leading_stock']}")
            if sector['related_stocks']:
                print(f"   相关股票: {', '.join(sector['related_stocks'][:3])}")
            print()
    else:
        print("\n今日无明显热点板块（涨幅 < 3%）")
    
    # 显示跌幅最大的板块
    print("\n📉 跌幅最大板块:")
    for sector in sectors[-5:]:
        print(f"  {sector['name']}: {sector['change_pct']:.2f}%")
    
    return result

def check_events(args):
    """检查地缘政治事件"""
    # 读取最新新闻缓存
    news_cache_file = DATA_DIR / "news_cache.json"
    
    if not news_cache_file.exists():
        print("没有新闻缓存数据")
        return
    
    with open(news_cache_file, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    
    all_news_text = " ".join([
        n.get("title", "") + " " + n.get("summary", "")
        for n in news_data.get("news", [])[-50:]
    ])
    
    events = check_geopolitical_events(all_news_text)
    
    if events:
        print("\n🚨 检测到地缘政治事件:")
        for event in events:
            print(f"\n事件: {event['name']}")
            print(f"关键词: {event['matched_keyword']}")
            print(f"受益板块: {', '.join(event['benefit_sectors'])}")
            if event['hurt_sectors']:
                print(f"受损板块: {', '.join(event['hurt_sectors'])}")
            
            # 推荐相关股票
            print("\n推荐关注:")
            for sector in event['benefit_sectors']:
                stocks = SECTOR_STOCKS.get(sector, [])
                if stocks:
                    print(f"  {sector}: {', '.join(stocks[:3])}")
    else:
        print("未检测到地缘政治事件")
    
    return events

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python sector_monitor.py scan     - 扫描行业热点")
        print("  python sector_monitor.py events   - 检查地缘政治事件")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "scan":
        scan(sys.argv[2:])
    elif command == "events":
        check_events(sys.argv[2:])
    else:
        print(f"未知命令: {command}")

if __name__ == "__main__":
    main()
