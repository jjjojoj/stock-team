#!/usr/bin/env python3
"""
新闻提炼器 - 为交易服务
不罗列新闻，只提炼对交易有价值的信息
"""

import json
from datetime import datetime
import os

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

def analyze_market_events():
    """分析市场事件 - 提炼关键信息"""
    
    # 今日关键事件（基于已抓取的新闻）
    events = {
        "date": "2026-03-03",
        "update_time": datetime.now().strftime('%H:%M'),
        
        # 对持仓的影响
        "position_impact": [
            {
                "stock": "贵研铂业",
                "code": "sh.600459",
                "event": "美伊冲突持续",
                "impact": "中性偏多",
                "reason": "战争持续 → 避险需求 → 但白银跳水压制贵金属",
                "action": "观察",
                "key_data": "铂钯期货价格未明显上涨"
            },
            {
                "stock": "宝地矿业",
                "code": "sh.601121",
                "event": "铁矿价格稳定",
                "impact": "中性",
                "reason": "无重大催化剂",
                "action": "持有",
                "key_data": "铁矿价格处于周期底部"
            }
        ],
        
        # 商品价格动态
        "commodity_update": {
            "白银": {
                "change": "-6%",
                "impact": "压制贵金属板块",
                "note": "白银跳水，铂钯承压"
            },
            "天然气": {
                "change": "+50%",
                "impact": "利好能源",
                "note": "卡塔尔停产"
            },
            "铂钯": {
                "change": "持平",
                "impact": "无明显变化",
                "note": "战争预期未传导到价格"
            }
        },
        
        # 行业对比
        "industry_ranking": [
            {"industry": "黄金", "change": "+3.24%", "note": "最强"},
            {"industry": "铜", "change": "+1.57%", "note": ""},
            {"industry": "铂族金属", "change": "+0.42%", "note": "贵研铂业所在"},
            {"industry": "化工", "change": "+0.40%", "note": ""},
            {"industry": "铁矿", "change": "+0.10%", "note": "宝地矿业所在"},
            {"industry": "稀土", "change": "-1.06%", "note": "最弱"}
        ],
        
        # 关键结论
        "key_insights": [
            "⚠️ 白银跳水 -6%，贵金属整体承压",
            "⚠️ 贵研铂业预测失败：战争利好未传导到铂钯价格",
            "✅ 黄金板块最强（+3.24%），避险资金流向黄金而非铂钯",
            "📊 贵研铂业在6个行业中排第3，中等偏上"
        ],
        
        # 操作建议
        "action_suggestions": [
            "贵研铂业：止损线 ¥24.17，当前 ¥26.27，距离止损 8%",
            "宝地矿业：持有观望，等待铁矿周期反转",
            "总体策略：控制仓位，关注铂钯期货走势"
        ]
    }
    
    return events

def generate_trade_digest():
    """生成交易摘要"""
    events = analyze_market_events()
    
    # 生成Markdown格式
    md = f"""# 交易摘要 - {events['date']} {events['update_time']}

## 📊 持仓影响分析

| 股票 | 事件 | 影响 | 操作 |
|------|------|------|------|
"""
    
    for pos in events['position_impact']:
        md += f"| {pos['stock']} | {pos['event']} | {pos['impact']} | {pos['action']} |\n"
    
    md += f"""
## 💰 商品价格动态

| 商品 | 涨跌 | 影响 | 备注 |
|------|------|------|------|
"""
    
    for commodity, data in events['commodity_update'].items():
        md += f"| {commodity} | {data['change']} | {data['impact']} | {data['note']} |\n"
    
    md += f"""
## 📈 行业对比

| 排名 | 行业 | 涨跌 | 备注 |
|------|------|------|------|
"""
    
    for i, ind in enumerate(events['industry_ranking'], 1):
        md += f"| {i} | {ind['industry']} | {ind['change']} | {ind['note']} |\n"
    
    md += f"""
## 💡 关键结论

"""
    for insight in events['key_insights']:
        md += f"- {insight}\n"
    
    md += f"""
## 🎯 操作建议

"""
    for suggestion in events['action_suggestions']:
        md += f"- {suggestion}\n"
    
    # 保存
    output_path = os.path.join(PROJECT_ROOT, "data", "news", "trade_digest.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # 同时保存JSON
    json_path = os.path.join(PROJECT_ROOT, "data", "news", "trade_digest.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    
    print("✅ 交易摘要已生成")
    print(f"📄 Markdown: {output_path}")
    print(f"📊 JSON: {json_path}")
    
    return events

if __name__ == '__main__':
    generate_trade_digest()
