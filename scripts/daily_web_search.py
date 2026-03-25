#!/usr/bin/env python3
"""
每日联网搜索脚本
在开盘前搜索最新市场信息
"""

import os
import sys
import json
import requests
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.storage import load_watchlist


class WebSearcher:
    def __init__(self):
        # 读取API密钥
        api_file = os.path.join(PROJECT_ROOT, "config", "api_keys.json")
        with open(api_file, 'r', encoding='utf-8') as f:
            keys = json.load(f)
        
        self.tavily_key = keys.get('tavily')
        self.newsapi_key = keys.get('newsapi')
    
    def tavily_search(self, query, max_results=5):
        """Tavily搜索"""
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get('results', [])
        except Exception as e:
            print(f"Tavily搜索失败: {e}")
        
        return []
    
    def search_market_overview(self):
        """搜索市场概况"""
        print("🔍 搜索市场概况...")
        
        queries = [
            "A股今日行情 央企改革",
            "稀土板块最新消息",
            "锂电板块投资机会",
            "有色金属价格走势"
        ]
        
        results = {}
        for query in queries:
            items = self.tavily_search(query, max_results=3)
            results[query] = items
            print(f"  ✅ {query}: {len(items)}条")
        
        return results
    
    def search_holdings(self):
        """搜索持仓股票最新信息"""
        print("\n🔍 搜索持仓股票...")
        
        # 读取持仓
        positions_file = os.path.join(PROJECT_ROOT, "config", "positions.json")
        with open(positions_file, 'r', encoding='utf-8') as f:
            positions = json.load(f)
        
        results = {}
        for code, pos in positions.items():
            name = pos['name']
            query = f"{name} 投资价值 最新消息 2026"
            items = self.tavily_search(query, max_results=3)
            results[name] = items
            print(f"  ✅ {name}: {len(items)}条")
        
        return results
    
    def search_watchlist(self):
        """搜索自选股最新信息"""
        print("\n🔍 搜索自选股...")

        watchlist = load_watchlist({})
        
        results = {}
        for code, info in list(watchlist.items())[:5]:  # 只搜索前5只
            name = info['name']
            query = f"{name} 投资机会 2026"
            items = self.tavily_search(query, max_results=2)
            results[name] = items
            print(f"  ✅ {name}: {len(items)}条")
        
        return results
    
    def save_results(self, market, holdings, watchlist):
        """保存搜索结果"""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'market_overview': market,
            'holdings': holdings,
            'watchlist': watchlist
        }
        
        # 保存到日期文件
        date_str = datetime.now().strftime('%Y%m%d')
        output_file = os.path.join(PROJECT_ROOT, "data", "daily_search", f"{date_str}.json")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 搜索结果已保存: {output_file}")
        
        return output_file
    
    def generate_summary(self, market, holdings, watchlist):
        """生成搜索摘要"""
        summary = []
        summary.append("=" * 60)
        summary.append("📊 每日搜索摘要")
        summary.append("=" * 60)
        summary.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        summary.append("")
        
        # 市场概况
        summary.append("【市场概况】")
        for query, items in market.items():
            if items:
                summary.append(f"  {query}:")
                for item in items[:2]:
                    title = item.get('title', 'N/A')
                    summary.append(f"    - {title}")
        summary.append("")
        
        # 持仓
        summary.append("【持仓股票】")
        for name, items in holdings.items():
            if items:
                summary.append(f"  {name}:")
                for item in items[:1]:
                    title = item.get('title', 'N/A')
                    summary.append(f"    - {title}")
        summary.append("")
        
        # 自选
        summary.append("【自选股】")
        for name, items in watchlist.items():
            if items:
                summary.append(f"  {name}:")
                for item in items[:1]:
                    title = item.get('title', 'N/A')
                    summary.append(f"    - {title}")
        
        return "\n".join(summary)


def main():
    searcher = WebSearcher()
    
    # 搜索
    market = searcher.search_market_overview()
    holdings = searcher.search_holdings()
    watchlist = searcher.search_watchlist()
    
    # 保存
    output_file = searcher.save_results(market, holdings, watchlist)
    
    # 生成摘要
    summary = searcher.generate_summary(market, holdings, watchlist)
    print("\n" + summary)
    
    # 保存摘要
    summary_file = os.path.join(PROJECT_ROOT, "data", "daily_search", "laverify_summary.txt")
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary)

    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
        from feishu_notifier import send_feishu_message

        send_feishu_message(
            title=f"🔎 开盘前联网搜索 - {datetime.now().strftime('%Y-%m-%d')}",
            content=summary,
            level="info",
        )
        print("✅ 飞书通知已发送")
    except Exception as exc:
        print(f"⚠️ 飞书通知发送失败: {exc}")


if __name__ == "__main__":
    main()
