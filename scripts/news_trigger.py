#!/usr/bin/env python3
"""
新闻监控触发器
- 监控持仓/关注股票相关新闻
- 分析新闻对预测的影响
- 自动更新预测置信度
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)
NEWS_CACHE_FILE = os.path.join(PROJECT_ROOT, "data", "news_cache.json")
PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
POSITIONS_FILE = os.path.join(PROJECT_ROOT, "config", "positions.json")

from core.storage import load_watchlist

# 新闻关键词权重（影响程度）
NEWS_KEYWORDS = {
    # 正面（看多）
    "positive": {
        "涨价": 15,
        "提价": 15,
        "盈利": 10,
        "利好": 10,
        "订单": 8,
        "扩产": 8,
        "突破": 5,
        "超预期": 12,
        "回购": 8,
        "分红": 5,
        "战": 20,  # 战争（对资源股利好）
        "冲突": 18,
        "制裁": 15,
        "稀土": 12,
        "锂": 10,
        "铜": 8,
        "铝": 8,
        "黄金": 10,
    },
    # 负面（看空）
    "negative": {
        "跌价": -15,
        "降价": -15,
        "亏损": -15,
        "利空": -12,
        "暴雷": -20,
        "减持": -10,
        "预警": -10,
        "调查": -8,
        "处罚": -10,
        "违约": -15,
        "退市": -25,
        "战争结束": -10,  # 对资源股利空
        "和平": -8,
    },
    # 政策类（需要判断）
    "policy": {
        "政策": 0,  # 需要具体分析
        "监管": -5,
        "环保": 5,  # 对资源股通常利好（供给减少）
        "碳中和": 8,
        "新能源": 10,
        "补贴": 10,
        "关税": -8,
    },
}

# 行业-股票映射
INDUSTRY_STOCKS = {
    "铂族金属": ["sh.600459"],  # 贵研铂业
    "铁矿": ["sh.601121"],  # 宝地矿业
    "稀土": ["sh.600111"],  # 北方稀土
    "铜": ["sh.601168", "sh.600362"],  # 西部矿业、江西铜业
    "铝": ["sh.601600"],  # 中国铝业
    "锂": ["sz.000792"],  # 盐湖股份
    "黄金": ["sh.600547", "sh.601899"],  # 山东黄金、紫金矿业
}


class NewsMonitor:
    """新闻监控器"""
    
    def __init__(self):
        self._ensure_dirs()
        self.news_cache = self._load_cache()
        self.predictions = self._load_predictions()
    
    def _ensure_dirs(self):
        os.makedirs(os.path.dirname(NEWS_CACHE_FILE), exist_ok=True)
    
    def _load_cache(self) -> Dict:
        if os.path.exists(NEWS_CACHE_FILE):
            with open(NEWS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"processed": [], "last_check": None}
    
    def _save_cache(self):
        with open(NEWS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.news_cache, f, ensure_ascii=False, indent=2)
    
    def _load_predictions(self) -> Dict:
        if os.path.exists(PREDICTIONS_FILE):
            with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"active": {}, "history": []}
    
    def _save_predictions(self):
        with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.predictions, f, ensure_ascii=False, indent=2)
    
    def analyze_news(self, news_item: Dict) -> Dict:
        """
        分析单条新闻
        
        Args:
            news_item: {
                "title": "新闻标题",
                "content": "新闻内容",
                "source": "来源",
                "time": "时间",
            }
        
        Returns:
            {
                "sentiment": "positive/negative/neutral",
                "impact_score": 15,  # 影响分数
                "affected_stocks": ["sh.600459"],
                "affected_industries": ["铂族金属"],
                "keywords_found": ["战", "涨价"],
            }
        """
        text = f"{news_item.get('title', '')} {news_item.get('content', '')}"
        
        impact_score = 0
        keywords_found = []
        affected_industries = []
        affected_stocks = set()
        
        # 分析关键词
        for category, keywords in NEWS_KEYWORDS.items():
            for keyword, score in keywords.items():
                if keyword in text:
                    impact_score += score
                    keywords_found.append(keyword)
        
        # 识别受影响的行业
        for industry, stocks in INDUSTRY_STOCKS.items():
            if industry in text:
                affected_industries.append(industry)
                affected_stocks.update(stocks)
        
        # 从持仓中识别股票
        positions = self._load_positions()
        for code, pos in positions.items():
            if pos.get("name", "") in text:
                affected_stocks.add(code)

        # 从观察池中识别股票
        watchlist = load_watchlist({})
        for code, info in watchlist.items():
            if info.get("name", "") in text:
                affected_stocks.add(code)
        
        # 判断情绪
        if impact_score >= 10:
            sentiment = "positive"
        elif impact_score <= -10:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "impact_score": impact_score,
            "affected_stocks": list(affected_stocks),
            "affected_industries": affected_industries,
            "keywords_found": keywords_found,
        }
    
    def _load_positions(self) -> Dict:
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def update_predictions_from_news(self, news_analysis: Dict, news_item: Dict):
        """
        根据新闻分析更新预测
        
        Args:
            news_analysis: analyze_news 的返回结果
            news_item: 原始新闻
        """
        if news_analysis["sentiment"] == "neutral":
            return  # 中性新闻不更新
        
        affected_stocks = news_analysis["affected_stocks"]
        impact_score = news_analysis["impact_score"]
        
        updates_made = []
        
        for pred_id, pred in self.predictions["active"].items():
            if pred["code"] not in affected_stocks:
                continue
            
            # 计算置信度变化
            # 看多预测 + 正面新闻 = 置信度上升
            # 看多预测 + 负面新闻 = 置信度下降
            direction_match = (
                (pred["direction"] == "up" and news_analysis["sentiment"] == "positive") or
                (pred["direction"] == "down" and news_analysis["sentiment"] == "negative")
            )
            
            if direction_match:
                confidence_change = min(15, abs(impact_score) // 2)  # 最多+15
            else:
                confidence_change = -min(20, abs(impact_score) // 2)  # 最多-20
            
            # 记录更新
            update = {
                "type": "news",
                "content": news_item.get("title", ""),
                "impact": news_analysis["sentiment"],
                "confidence_change": confidence_change,
                "reason": f"新闻关键词: {', '.join(news_analysis['keywords_found'][:3])}",
            }
            
            pred["updates"].append(update)
            pred["confidence"] = max(0, min(100, pred["confidence"] + confidence_change))
            
            updates_made.append({
                "stock": pred["name"],
                "confidence_change": confidence_change,
                "new_confidence": pred["confidence"],
            })
        
        if updates_made:
            self._save_predictions()
            
            print(f"📰 新闻触发预测更新:")
            print(f"   新闻: {news_item.get('title', '')[:50]}...")
            for update in updates_made:
                sign = "+" if update["confidence_change"] >= 0 else ""
                print(f"   {update['stock']}: {sign}{update['confidence_change']}% → {update['new_confidence']}%")
    
    def check_news_impact(self) -> List[Dict]:
        """
        检查最新新闻的影响（用于定时任务）
        
        Returns:
            有影响的新闻列表
        """
        # 这里应该从实际新闻源获取
        # 目前返回示例
        recent_news = self._fetch_recent_news()
        
        impactful_news = []
        
        for news in recent_news:
            # 跳过已处理的
            news_id = news.get("id", news.get("title", "")[:20])
            if news_id in self.news_cache["processed"]:
                continue
            
            # 分析新闻
            analysis = self.analyze_news(news)
            
            # 只处理有影响的新闻
            if analysis["sentiment"] != "neutral" and analysis["affected_stocks"]:
                self.update_predictions_from_news(analysis, news)
                impactful_news.append({
                    "news": news,
                    "analysis": analysis,
                })
            
            # 标记为已处理
            self.news_cache["processed"].append(news_id)
        
        # 清理旧记录（保留最近1000条）
        self.news_cache["processed"] = self.news_cache["processed"][-1000:]
        self.news_cache["last_check"] = datetime.now().isoformat()
        self._save_cache()
        
        return impactful_news
    
    def _fetch_recent_news(self) -> List[Dict]:
        """
        获取最近新闻（从 news_cache.json 读取已收集的新闻）
        """
        # 从缓存中读取已收集的新闻
        if "news" in self.news_cache and self.news_cache["news"]:
            # 只返回最近 24 小时内的新闻
            recent = []
            now = datetime.now()
            for news in self.news_cache["news"]:
                # 解析新闻时间
                news_time_str = news.get("time", "")
                try:
                    if news_time_str.isdigit():
                        # Unix 时间戳
                        news_time = datetime.fromtimestamp(int(news_time_str))
                    else:
                        # ISO 格式
                        news_time = datetime.fromisoformat(news_time_str.replace('Z', '+00:00'))
                    
                    # 检查是否在 24 小时内
                    if (now - news_time.replace(tzinfo=None)).total_seconds() < 24 * 3600:
                        recent.append(news)
                except:
                    # 时间解析失败，仍然包含该新闻
                    recent.append(news)
            
            return recent[-50:]  # 最多返回最近 50 条
        
        # 如果没有数据，返回空列表
        return []
    
    def generate_news_digest(self) -> str:
        """生成新闻摘要报告"""
        impactful = self.check_news_impact()
        
        digest = f"📰 新闻监控摘要 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
        digest += "=" * 50 + "\n\n"
        
        if not impactful:
            digest += "暂无影响持仓/预测的重要新闻\n"
        else:
            digest += f"发现 {len(impactful)} 条相关新闻:\n\n"
            
            for item in impactful:
                news = item["news"]
                analysis = item["analysis"]
                
                sentiment_icon = "📈" if analysis["sentiment"] == "positive" else "📉"
                digest += f"{sentiment_icon} {news['title']}\n"
                digest += f"   影响: {analysis['sentiment']}\n"
                digest += f"   关键词: {', '.join(analysis['keywords_found'][:5])}\n"
                digest += f"   相关股票: {', '.join(analysis['affected_stocks'])}\n\n"
        
        return digest


def main():
    if len(sys.argv) < 2:
        print("新闻监控触发器")
        print("\n用法:")
        print("  python3 news_trigger.py check     # 检查新闻影响")
        print("  python3 news_trigger.py digest    # 生成新闻摘要")
        print("  python3 news_trigger.py verify      # 测试新闻分析")
        sys.exit(1)
    
    command = sys.argv[1]
    monitor = NewsMonitor()
    
    if command == "check":
        impactful = monitor.check_news_impact()
        print(f"检查完成: 发现 {len(impactful)} 条有影响的新闻")
    
    elif command == "digest":
        print(monitor.generate_news_digest())
    
    elif command == "verify":
        # 测试新闻分析
        verify_news = {
            "title": "美伊战争升级，稀土价格暴涨",
            "content": "受地缘冲突影响，稀土、铂族金属等战略资源价格大幅上涨...",
            "source": "测试",
            "time": datetime.now().isoformat(),
        }
        
        analysis = monitor.analyze_news(verify_news)
        print("新闻分析结果:")
        print(f"  情绪: {analysis['sentiment']}")
        print(f"  影响分数: {analysis['impact_score']}")
        print(f"  关键词: {analysis['keywords_found']}")
        print(f"  受影响行业: {analysis['affected_industries']}")
        print(f"  受影响股票: {analysis['affected_stocks']}")


if __name__ == "__main__":
    main()
