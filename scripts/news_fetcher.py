#!/usr/bin/env python3
"""
新闻获取器 - 为AI预测生成器提供新闻数据
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

# 导入现有的新闻收集器
try:
    from news_auto_collector import NewsAutoCollector
except ImportError:
    NewsAutoCollector = None

# 新闻缓存路径
NEWS_CACHE_FILE = os.path.join(PROJECT_ROOT, "data", "news_cache.json")


class NewsFetcher:
    """新闻获取器"""
    
    def __init__(self):
        self.collector = None
        if NewsAutoCollector:
            self.collector = NewsAutoCollector()
    
    def fetch_all(self, keywords: List[str] = None) -> List[Dict]:
        """
        获取所有相关新闻
        
        Args:
            keywords: 关键词列表
            
        Returns:
            新闻列表
        """
        # 首先尝试从缓存读取
        news_from_cache = self._load_news_from_cache()
        if news_from_cache:
            return news_from_cache
        
        # 如果有自动收集器，使用它
        if self.collector:
            try:
                all_news = self.collector.fetch_all_news()
                important_news = self.collector.filter_important_news(all_news)
                
                # 转换格式以匹配预期
                formatted_news = []
                for news in important_news:
                    formatted_news.append({
                        "title": news.get("title", ""),
                        "content": news.get("description", ""),
                        "source": news.get("source", "未知"),
                        "time": news.get("published_at", datetime.now().isoformat()),
                    })
                
                # 保存到缓存
                self._save_news_to_cache(formatted_news)
                return formatted_news
                
            except Exception as e:
                print(f"⚠️ 自动新闻收集失败: {e}")
        
        # 返回空列表作为备选
        return []
    
    def _load_news_from_cache(self) -> List[Dict]:
        """从缓存加载新闻"""
        if os.path.exists(NEWS_CACHE_FILE):
            try:
                with open(NEWS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    raw = f.read().strip()
                if not raw:
                    return []

                cache_data = json.loads(raw)
                
                # 检查是否是最近24小时内的数据
                last_check = cache_data.get("last_check")
                if last_check:
                    try:
                        last_check_time = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                        if (datetime.now() - last_check_time).total_seconds() < 24 * 3600:
                            return cache_data.get("news", [])
                    except:
                        pass
            
            except Exception as e:
                print(f"⚠️ 读取新闻缓存失败: {e}")
        
        return []
    
    def _save_news_to_cache(self, news_list: List[Dict]):
        """保存新闻到缓存"""
        try:
            cache_data = {
                "news": news_list,
                "last_check": datetime.now().isoformat(),
            }
            
            os.makedirs(os.path.dirname(NEWS_CACHE_FILE), exist_ok=True)
            with open(NEWS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"⚠️ 保存新闻缓存失败: {e}")


# 兼容性导入（如果需要）
def fetch_news(keywords=None):
    """兼容性函数"""
    fetcher = NewsFetcher()
    return fetcher.fetch_all(keywords)
