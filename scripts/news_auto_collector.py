#!/usr/bin/env python3
"""
新闻自动获取模块
使用 News API / SerpApi / Tavily API 自动获取财经新闻
"""

import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

# 添加 requests 库检查
try:
    import requests
except ImportError:
    print("⚠️ 请安装 requests 库: pip install requests")
    requests = None

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from news_monitor import analyze_news_impact, save_news_analysis

# API 配置（已配置用户提供的API密钥）
NEWS_APIS = {
    "news_api": {
        "api_key": "0a456a5e7a7f4729bb9c745093678c2e",
        "base_url": "https://newsapi.org/v2",
        "enabled": True,
    },
    "tavily": {
        "api_key": "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",
        "base_url": "https://api.tavily.com/search",
        "enabled": True,
    },
    "exa": {
        "api_key": "4f49c5f3-c357-4e86-87e0-b82f2fc61c4c",
        "base_url": "https://api.exa.ai/search",
        "enabled": True,
    },
}

# 新闻关键词（关注的内容）
NEWS_KEYWORDS = [
    # 国际形势
    "战争", "冲突", "制裁", "军事", "中东",
    "美国 中国", "贸易战", "关税",
    
    # 宏观经济
    "GDP", "CPI", "PMI", "降息", "加息",
    "央行", "货币政策", "财政政策",
    
    # 行业相关
    "有色金属", "铜", "铝", "锂", "稀土",
    "半导体", "芯片", "新能源",
    "石油", "黄金",
    
    # 公司相关
    "央企", "国企改革", "并购",
]

# 关注的公司（股票池中的公司）
WATCHED_COMPANIES = [
    "贵研铂业", "宝地矿业", "中色股份",
    "西部矿业", "江西铜业", "云南铜业",
    "中国铝业", "云铝股份", "盐湖股份",
    "北方稀土", "五矿稀土",
    "中芯国际", "华润微",
]


class NewsAutoCollector:
    """新闻自动收集器"""
    
    def __init__(self):
        self.news_cache = []
        self.last_fetch_time = None
    
    def fetch_from_news_api(self, keywords: List[str] = None) -> List[Dict]:
        """
        从 News API 获取新闻
        https://newsapi.org/
        """
        config = NEWS_APIS["news_api"]
        
        if not config["enabled"] or not config["api_key"]:
            print("⚠️ News API 未配置或未启用")
            return []
        
        if keywords is None:
            keywords = NEWS_KEYWORDS
        
        news_list = []
        
        try:
            # News API 查询
            # 注意：免费版只能查英文，中文需要付费
            query = " OR ".join(keywords[:5])  # 取前5个关键词
            
            params = {
                "q": query,
                "apiKey": config["api_key"],
                "language": "zh",  # 中文
                "sortBy": "publishedAt",
                "pageSize": 20,
            }
            
            response = requests.get(
                f"{config['base_url']}/everything",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                for article in data.get("articles", []):
                    news_list.append({
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "source": article.get("source", {}).get("name", "News API"),
                        "url": article.get("url", ""),
                        "published_at": article.get("publishedAt", ""),
                        "api": "news_api",
                    })
            
            print(f"✅ News API 获取到 {len(news_list)} 条新闻")
            
        except Exception as e:
            print(f"❌ News API 请求失败: {e}")
        
        return news_list
    
    def fetch_from_serpapi(self, keywords: List[str] = None) -> List[Dict]:
        """
        从 SerpApi 获取新闻（Google 搜索结果）
        https://serpapi.com/
        """
        config = NEWS_APIS["serpapi"]
        
        if not config["enabled"] or not config["api_key"]:
            print("⚠️ SerpApi 未配置或未启用")
            return []
        
        if keywords is None:
            keywords = NEWS_KEYWORDS
        
        news_list = []
        
        try:
            # SerpApi 查询
            query = " OR ".join(keywords[:3])
            
            params = {
                "q": f"{query} 财经 新闻",
                "api_key": config["api_key"],
                "engine": "google_news",
                "hl": "zh-cn",
                "gl": "cn",
                "num": 20,
            }
            
            response = requests.get(
                config["base_url"],
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                for result in data.get("news_results", []):
                    news_list.append({
                        "title": result.get("title", ""),
                        "description": result.get("snippet", ""),
                        "source": result.get("source", "SerpApi"),
                        "url": result.get("link", ""),
                        "published_at": result.get("date", ""),
                        "api": "serpapi",
                    })
            
            print(f"✅ SerpApi 获取到 {len(news_list)} 条新闻")
            
        except Exception as e:
            print(f"❌ SerpApi 请求失败: {e}")
        
        return news_list
    
    def fetch_from_tavily(self, keywords: List[str] = None) -> List[Dict]:
        """
        从 Tavily API 获取新闻（AI 搜索）
        https://tavily.com/
        """
        config = NEWS_APIS["tavily"]
        
        if not config["enabled"] or not config["api_key"]:
            print("⚠️ Tavily API 未配置或未启用")
            return []
        
        if keywords is None:
            keywords = NEWS_KEYWORDS
        
        news_list = []
        
        try:
            # Tavily 查询
            query = " OR ".join(keywords[:3])
            
            payload = {
                "api_key": config["api_key"],
                "query": f"{query} 最新新闻 财经",
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
                "max_results": 20,
            }
            
            response = requests.post(
                config["base_url"],
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                for result in data.get("results", []):
                    news_list.append({
                        "title": result.get("title", ""),
                        "description": result.get("content", ""),
                        "source": result.get("url", "").split("/")[2] if result.get("url") else "Tavily",
                        "url": result.get("url", ""),
                        "published_at": datetime.now().isoformat(),
                        "api": "tavily",
                    })
            
            print(f"✅ Tavily API 获取到 {len(news_list)} 条新闻")
            
        except Exception as e:
            print(f"❌ Tavily API 请求失败: {e}")
        
        return news_list
    
    def fetch_from_exa(self, keywords: List[str] = None) -> List[Dict]:
        """
        从 Exa AI 获取新闻（AI搜索）
        https://exa.ai/
        """
        config = NEWS_APIS["exa"]
        
        if not config["enabled"] or not config["api_key"]:
            print("⚠️ Exa AI 未配置或未启用")
            return []
        
        if keywords is None:
            keywords = NEWS_KEYWORDS
        
        news_list = []
        
        try:
            # Exa AI 查询
            query = " OR ".join(keywords[:3])
            
            headers = {
                "x-api-key": config["api_key"],
                "Content-Type": "application/json",
            }
            
            payload = {
                "query": f"{query} 财经新闻 A股",
                "type": "auto",
                "category": "company",
                "numResults": 20,
            }
            
            response = requests.post(
                config["base_url"],
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                for result in data.get("results", []):
                    news_list.append({
                        "title": result.get("title", ""),
                        "description": result.get("text", "")[:500],
                        "source": result.get("url", "").split("/")[2] if result.get("url") else "Exa AI",
                        "url": result.get("url", ""),
                        "published_at": datetime.now().isoformat(),
                        "api": "exa",
                    })
            
            print(f"✅ Exa AI 获取到 {len(news_list)} 条新闻")
            
        except Exception as e:
            print(f"❌ Exa AI 请求失败: {e}")
        
        return news_list
    
    def fetch_all_news(self) -> List[Dict]:
        """从所有API获取新闻"""
        all_news = []
        
        # 从各个API获取
        all_news.extend(self.fetch_from_news_api())
        all_news.extend(self.fetch_from_tavily())
        all_news.extend(self.fetch_from_exa())  # 使用 Exa AI 替代 SerpApi
        
        # 去重（基于标题）
        unique_news = []
        seen_titles = set()
        
        for news in all_news:
            title = news["title"]
            if title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        print(f"\n📊 总计获取到 {len(unique_news)} 条去重后的新闻")
        
        # 按时间排序
        unique_news.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        
        self.news_cache = unique_news
        self.last_fetch_time = datetime.now()
        
        return unique_news
    
    def filter_important_news(self, news_list: List[Dict] = None) -> List[Dict]:
        """筛选重要新闻"""
        if news_list is None:
            news_list = self.news_cache
        
        important_news = []
        
        for news in news_list:
            title = news.get("title", "")
            description = news.get("description", "")
            text = f"{title} {description}"
            
            # 检查是否包含关键词
            for keyword in NEWS_KEYWORDS:
                if keyword in text:
                    news["matched_keyword"] = keyword
                    important_news.append(news)
                    break
            
            # 检查是否包含关注的公司
            for company in WATCHED_COMPANIES:
                if company in text:
                    news["matched_company"] = company
                    if news not in important_news:
                        important_news.append(news)
                    break
        
        print(f"🔍 筛选出 {len(important_news)} 条重要新闻")
        
        return important_news
    
    def analyze_and_alert(self, news_list: List[Dict] = None):
        """分析新闻并发送预警"""
        if news_list is None:
            news_list = self.filter_important_news()
        
        alerts = []
        
        for news in news_list:
            # 分析影响
            analysis = analyze_news_impact(
                news["title"],
                news.get("description", ""),
                news.get("source", "未知")
            )
            
            # 只记录高严重程度的事件
            if analysis["severity"] in ["高", "中"]:
                # 保存分析结果
                save_news_analysis(analysis)
                
                # 添加到预警列表
                alerts.append({
                    "title": news["title"],
                    "event_type": analysis["event_type"],
                    "severity": analysis["severity"],
                    "positive_stocks": analysis["positive_stocks"][:3],
                    "negative_stocks": analysis["negative_stocks"][:3],
                })
        
        # 发送预警
        if alerts:
            self._send_alerts(alerts)
        
        return alerts
    
    def _send_alerts(self, alerts: List[Dict]):
        """发送预警（保存到文件，供Web仪表盘读取）"""
        alert_file = os.path.join(PROJECT_ROOT, "data", "alerts.json")
        
        # 读取现有预警
        existing_alerts = []
        if os.path.exists(alert_file):
            with open(alert_file, 'r', encoding='utf-8') as f:
                existing_alerts = json.load(f)
        
        # 添加新预警
        for alert in alerts:
            alert["time"] = datetime.now().isoformat()
            alert["read"] = False
            existing_alerts.append(alert)
        
        # 只保留最近100条
        existing_alerts = existing_alerts[-100:]
        
        # 保存
        with open(alert_file, 'w', encoding='utf-8') as f:
            json.dump(existing_alerts, f, ensure_ascii=False, indent=2)
        
        print(f"⚠️ 已发送 {len(alerts)} 条预警")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 news_auto_collector.py <命令>")
        print("命令:")
        print("  fetch      获取新闻")
        print("  filter     筛选重要新闻")
        print("  analyze    分析新闻并发送预警")
        print("  all        完整流程（获取→筛选→分析→预警）")
        sys.exit(1)
    
    command = sys.argv[1]
    
    collector = NewsAutoCollector()
    
    if command == "fetch":
        news = collector.fetch_all_news()
        
        print("\n📰 最新新闻：")
        for i, n in enumerate(news[:10], 1):
            print(f"{i}. [{n['source']}] {n['title']}")
    
    elif command == "filter":
        news = collector.fetch_all_news()
        important = collector.filter_important_news(news)
        
        print("\n🔍 重要新闻：")
        for i, n in enumerate(important[:10], 1):
            print(f"{i}. [{n.get('matched_keyword', n.get('matched_company', '未知'))}] {n['title']}")
    
    elif command == "analyze":
        news = collector.fetch_all_news()
        important = collector.filter_important_news(news)
        alerts = collector.analyze_and_alert(important)
        
        print(f"\n⚠️ 发送了 {len(alerts)} 条预警")
    
    elif command == "all":
        news = collector.fetch_all_news()
        important = collector.filter_important_news(news)
        alerts = collector.analyze_and_alert(important)
        
        print(f"\n✅ 完整流程执行完成")
        print(f"   获取新闻：{len(news)} 条")
        print(f"   筛选重要：{len(important)} 条")
        print(f"   发送预警：{len(alerts)} 条")
    
    else:
        print("未知命令")
        sys.exit(1)


if __name__ == "__main__":
    main()
