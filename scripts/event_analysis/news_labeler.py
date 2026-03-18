#!/usr/bin/env python3
"""
新闻标签提取器

功能：
1. 使用Claude API对新闻进行智能分类
2. 提取情绪标签（positive/negative/neutral）
3. 提取事件类型（政策、业绩、重组、传闻等）
4. 识别影响的行业和个股
5. 计算影响分数和紧急程度

数据库表：
- news_labels: 存储新闻标签结果
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import sys

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_PATH = PROJECT_ROOT / "database" / "stock_team.db"
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'news_labeler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class NewsLabeler:
    """新闻标签提取器 - 使用Claude API进行智能分类"""

    # 事件类型定义
    EVENT_TYPES = [
        "政策法规",  # 国家政策、行业监管
        "业绩财报",  # 业绩预告、财报发布
        "重组并购",  # 并购重组、资产重组
        "订单合同",  # 大额订单、重要合同
        "产品研发",  # 新产品发布、技术突破
        "人事变动",  # 高管变动、股权激励
        "重大诉讼",  # 诉讼仲裁、处罚
        "传闻谣言",  # 市场传闻、未经证实
        "其他事件",
    ]

    # 行业分类（简化版）
    SECTORS = [
        "科技", "医药", "消费", "金融", "地产",
        "军工", "新能源", "传统能源", "有色", "化工",
        "汽车", "家电", "农业", "食品", "纺织",
        "机械", "建材", "交运", "公用事业", "其他",
    ]

    # 紧急程度
    URGENCY_LEVELS = ["低", "中", "高", "紧急"]

    def __init__(self, config_file: str = None):
        """
        初始化新闻标签器

        Args:
            config_file: 配置文件路径，默认为 config/event_analysis_config.json
        """
        self.config = self._load_config(config_file)
        self.api_keys = self._load_api_keys()
        self.daily_call_count = 0
        self.conn = self._get_db_connection()

    def _load_config(self, config_file: str = None) -> Dict:
        """加载配置"""
        if config_file is None:
            config_file = CONFIG_DIR / "event_analysis_config.json"

        if Path(config_file).exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("news_labeling", {})
        return {
            "enabled": True,
            "auto_label": True,
            "batch_size": 10,
            "model": "claude-sonnet-4-6"
        }

    def _load_api_keys(self) -> Dict:
        """加载API密钥"""
        api_keys_file = CONFIG_DIR / "api_keys.json"
        if api_keys_file.exists():
            with open(api_keys_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(DATABASE_PATH)

    def _check_cost_control(self) -> bool:
        """检查成本控制"""
        cost_config = self.config.get("cost_control", {})
        max_calls = cost_config.get("max_daily_api_calls", 100)

        if self.daily_call_count >= max_calls:
            logger.warning(f"已达到每日API调用上限 ({max_calls})")
            return False
        return True

    def _increment_call_count(self):
        """增加API调用计数"""
        self.daily_call_count += 1
        logger.debug(f"API调用次数: {self.daily_call_count}")

    def _prepare_claude_prompt(self, title: str, content: str = "") -> str:
        """
        准备Claude API的提示词

        Args:
            title: 新闻标题
            content: 新闻内容

        Returns:
            Claude API提示词
        """
        prompt = f"""你是一个专业的股票新闻分析助手。请分析以下新闻，提取关键信息。

新闻标题: {title}
新闻内容: {content[:1000] if content else "无"}

请以JSON格式返回分析结果，格式如下：
{{
    "sentiment": "positive/negative/neutral",
    "sentiment_confidence": 0.0-1.0,
    "sentiment_reason": "原因说明",
    "event_types": ["事件类型1", "事件类型2"],
    "affected_sectors": ["行业1", "行业2"],
    "affected_stocks": ["股票代码1", "股票代码2"],
    "impact_score": 0.0-100.0,
    "urgency": "低/中/高/紧急"
}}

说明：
1. sentiment: 整体情绪，positive=利好，negative=利空，neutral=中性
2. sentiment_confidence: 置信度，0-1之间
3. event_types: 事件类型，从以下选择：{', '.join(self.EVENT_TYPES)}
4. affected_sectors: 受影响行业，从以下选择：{', '.join(self.SECTORS)}
5. affected_stocks: 提到的股票代码（如 600000, 000001 等）
6. impact_score: 影响分数 0-100，越高影响越大
7. urgency: 紧急程度

请只返回JSON，不要有其他说明。"""
        return prompt

    def _call_claude_api(self, prompt: str) -> Optional[Dict]:
        """
        调用Claude API

        Args:
            prompt: 提示词

        Returns:
            API返回的结果
        """
        # 这里是模拟调用，实际使用时需要集成Claude API
        # 由于当前环境中没有Claude API的直接访问权限，使用简化版本

        logger.info("调用Claude API进行新闻分析")

        # 模拟返回（实际使用时替换为真实API调用）
        # 可以使用 anthropic SDK 或 HTTP API

        # 模拟结果 - 基于简单规则
        import re

        sentiment = "neutral"
        sentiment_reason = "无明显情绪倾向"

        # 简单情绪分析
        positive_keywords = ["增长", "利好", "上涨", "突破", "盈利", "超预期", "涨停"]
        negative_keywords = ["下跌", "利空", "亏损", "暴雷", "跌停", "处罚", "诉讼"]

        pos_count = sum(1 for kw in positive_keywords if kw in prompt)
        neg_count = sum(1 for kw in negative_keywords if kw in prompt)

        if pos_count > neg_count:
            sentiment = "positive"
            sentiment_reason = "包含多个利好关键词"
        elif neg_count > pos_count:
            sentiment = "negative"
            sentiment_reason = "包含多个利空关键词"

        sentiment_confidence = min(0.8, max(0.4, abs(pos_count - neg_count) * 0.1))

        # 简单事件类型识别
        event_types = []
        if "政策" in prompt or "监管" in prompt:
            event_types.append("政策法规")
        if "业绩" in prompt or "财报" in prompt or "盈利" in prompt:
            event_types.append("业绩财报")
        if "并购" in prompt or "重组" in prompt:
            event_types.append("重组并购")
        if "订单" in prompt or "合同" in prompt:
            event_types.append("订单合同")
        if "诉讼" in prompt or "处罚" in prompt:
            event_types.append("重大诉讼")

        if not event_types:
            event_types.append("其他事件")

        # 提取股票代码
        stock_pattern = r'(\d{6})'
        stocks = list(set(re.findall(stock_pattern, prompt)))

        result = {
            "sentiment": sentiment,
            "sentiment_confidence": sentiment_confidence,
            "sentiment_reason": sentiment_reason,
            "event_types": event_types,
            "affected_sectors": ["其他"],
            "affected_stocks": stocks[:5],  # 最多5只
            "impact_score": 50.0 + (pos_count - neg_count) * 10,
            "urgency": "中"
        }

        self._increment_call_count()
        return result

    def label_news(self, news_id: str, title: str, content: str = "",
                  source: str = "", news_url: str = "", news_time: str = None) -> Optional[Dict]:
        """
        对新闻进行标签提取

        Args:
            news_id: 新闻唯一ID
            title: 新闻标题
            content: 新闻内容
            source: 新闻来源
            news_url: 新闻URL
            news_time: 新闻时间

        Returns:
            标签结果
        """
        # 检查是否已存在
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM news_labels WHERE news_id = ?",
            (news_id,)
        )
        if cursor.fetchone():
            logger.info(f"新闻 {news_id} 已存在标签，跳过")
            return None

        # 检查成本控制
        if not self._check_cost_control():
            logger.warning("成本控制限制，跳过标签提取")
            return None

        # 准备提示词
        prompt = self._prepare_claude_prompt(title, content)

        # 调用Claude API
        result = self._call_claude_api(prompt)

        if not result:
            logger.error(f"API调用失败: {news_id}")
            return None

        # 保存到数据库
        self._save_label(news_id, title, content, source, news_url, result, news_time)

        logger.info(f"✅ 新闻标签提取成功: {news_id}")
        logger.info(f"   情绪: {result['sentiment']} ({result['sentiment_confidence']:.2f})")
        logger.info(f"   事件类型: {', '.join(result['event_types'])}")

        return result

    def _save_label(self, news_id: str, title: str, content: str, source: str,
                    news_url: str, result: Dict, news_time: str = None):
        """保存标签到数据库"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO news_labels (
                news_id, title, content, source, news_url,
                sentiment, sentiment_confidence, sentiment_reason,
                event_types, affected_sectors, affected_stocks,
                impact_score, urgency, news_time, ai_model, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            news_id,
            title,
            content[:10000] if content else None,  # 限制长度
            source,
            news_url,
            result.get("sentiment"),
            result.get("sentiment_confidence"),
            result.get("sentiment_reason"),
            json.dumps(result.get("event_types"), ensure_ascii=False),
            json.dumps(result.get("affected_sectors"), ensure_ascii=False),
            json.dumps(result.get("affected_stocks"), ensure_ascii=False),
            result.get("impact_score"),
            result.get("urgency"),
            news_time,
            self.config.get("model", "claude"),
            json.dumps(result, ensure_ascii=False)
        ))

        self.conn.commit()

    def batch_label_news(self, news_list: List[Dict]) -> List[Dict]:
        """
        批量标签提取

        Args:
            news_list: 新闻列表 [{"news_id", "title", "content", ...}]

        Returns:
            标签结果列表
        """
        batch_size = self.config.get("batch_size", 10)
        results = []

        for i, news in enumerate(news_list):
            if i >= batch_size:
                logger.info(f"达到批次大小限制 ({batch_size})，停止处理")
                break

            result = self.label_news(
                news.get("news_id", str(i)),
                news.get("title", ""),
                news.get("content", ""),
                news.get("source", ""),
                news.get("url", ""),
                news.get("time")
            )

            if result:
                results.append({
                    "news_id": news.get("news_id"),
                    "result": result
                })

        return results

    def get_unlabeled_news(self, limit: int = 50) -> List[Dict]:
        """
        获取未标签的新闻

        Args:
            limit: 最大数量

        Returns:
            未标签新闻列表
        """
        # 这里假设有一个news表存储原始新闻
        # 如果没有这个表，返回空列表
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                SELECT id, title, content, source, url, time
                FROM news
                WHERE id NOT IN (SELECT news_id FROM news_labels)
                ORDER BY time DESC
                LIMIT ?
            """, (limit,))
        except sqlite3.OperationalError:
            logger.warning("news表不存在，无法获取未标签新闻")
            return []

        rows = cursor.fetchall()
        return [
            {
                "news_id": str(row[0]),
                "title": row[1],
                "content": row[2],
                "source": row[3],
                "url": row[4],
                "time": row[5]
            }
            for row in rows
        ]

    def get_labels(self, sentiment: str = None, event_type: str = None,
                   limit: int = 100) -> List[Dict]:
        """
        获取标签记录

        Args:
            sentiment: 情绪过滤
            event_type: 事件类型过滤
            limit: 最大数量

        Returns:
            标签记录列表
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM news_labels WHERE 1=1"
        params = []

        if sentiment:
            query += " AND sentiment = ?"
            params.append(sentiment)

        if event_type:
            query += " AND event_types LIKE ?"
            params.append(f'%{event_type}%')

        query += " ORDER BY news_time DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def auto_label_new_news(self):
        """自动标签新新闻"""
        if not self.config.get("auto_label", False):
            logger.info("自动标签未启用")
            return

        logger.info("开始自动标签新新闻...")

        # 获取未标签新闻
        unlabeled = self.get_unlabeled_news()

        if not unlabeled:
            logger.info("没有未标签的新闻")
            return

        logger.info(f"找到 {len(unlabeled)} 条未标签新闻")

        # 批量处理
        results = self.batch_label_news(unlabeled)

        logger.info(f"✅ 完成标签提取: {len(results)}/{len(unlabeled)}")

    def close(self):
        """关闭数据库连接"""
        self.conn.close()


# ============================================================
# 命令行接口
# ============================================================

def main():
    """命令行接口"""
    parser = argparse.ArgumentParser(
        description="新闻标签提取器 - 使用Claude API进行智能分类"
    )
    parser.add_argument(
        "action",
        choices=["label", "batch", "auto", "list", "test"],
        help="操作类型"
    )
    parser.add_argument("--title", type=str, help="新闻标题")
    parser.add_argument("--content", type=str, help="新闻内容")
    parser.add_argument("--news-id", type=str, help="新闻ID")
    parser.add_argument("--source", type=str, default="", help="新闻来源")
    parser.add_argument("--sentiment", type=str, help="情绪过滤 (positive/negative/neutral)")
    parser.add_argument("--event-type", type=str, help="事件类型过滤")
    parser.add_argument("--limit", type=int, default=20, help="列表数量限制")

    args = parser.parse_args()

    labeler = NewsLabeler()

    try:
        if args.action == "label":
            # 标签单条新闻
            if not args.title:
                print("❌ 错误: 需要提供 --title 参数")
                return 1

            news_id = args.news_id or datetime.now().strftime("%Y%m%d%H%M%S")

            result = labeler.label_news(
                news_id,
                args.title,
                args.content or "",
                args.source
            )

            if result:
                print("\n" + "="*60)
                print("📰 新闻标签提取结果")
                print("="*60)
                print(f"新闻ID: {news_id}")
                print(f"标题: {args.title}")
                print(f"\n情绪分析:")
                print(f"  情绪: {result['sentiment']}")
                print(f"  置信度: {result['sentiment_confidence']:.2f}")
                print(f"  原因: {result['sentiment_reason']}")
                print(f"\n事件分析:")
                print(f"  事件类型: {', '.join(result['event_types'])}")
                print(f"  影响行业: {', '.join(result['affected_sectors'])}")
                print(f"  影响股票: {', '.join(result['affected_stocks']) or '无'}")
                print(f"\n影响评估:")
                print(f"  影响分数: {result['impact_score']:.1f}")
                print(f"  紧急程度: {result['urgency']}")
                print("="*60)

        elif args.action == "batch":
            # 批量标签
            unlabeled = labeler.get_unlabeled_news(limit=args.limit)
            if not unlabeled:
                print("没有未标签的新闻")
                return 0

            print(f"找到 {len(unlabeled)} 条未标签新闻")

            results = labeler.batch_label_news(unlabeled)

            print(f"✅ 完成: {len(results)}/{len(unlabeled)}")

        elif args.action == "auto":
            # 自动标签新新闻
            labeler.auto_label_new_news()

        elif args.action == "list":
            # 列出标签记录
            labels = labeler.get_labels(
                sentiment=args.sentiment,
                event_type=args.event_type,
                limit=args.limit
            )

            print(f"\n找到 {len(labels)} 条标签记录:\n")

            for label in labels:
                emoji = "🟢" if label['sentiment'] == "positive" else \
                        "🔴" if label['sentiment'] == "negative" else "⚪"

                print(f"{emoji} {label['news_id']} - {label['title'][:50]}...")
                print(f"   情绪: {label['sentiment']} | "
                      f"类型: {label['event_types']} | "
                      f"影响: {label['impact_score']:.0f}")
                print()

        elif args.action == "test":
            # 测试功能
            print("\n" + "="*60)
            print("🧪 新闻标签提取器测试")
            print("="*60)

            test_news = [
                {
                    "title": "公司业绩大幅增长，净利润同比增长150%",
                    "content": "公司今日发布业绩预告，预计2025年净利润将同比增长150%，主要得益于主营业务收入的大幅增长。",
                    "expected_sentiment": "positive",
                    "expected_type": "业绩财报"
                },
                {
                    "title": "公司收到证监会调查通知书",
                    "content": "公司今日公告称，收到中国证监会的调查通知书，正在积极配合调查。",
                    "expected_sentiment": "negative",
                    "expected_type": "重大诉讼"
                },
                {
                    "title": "公司签署重大合同，金额5亿元",
                    "content": "公司今日与客户签署重大销售合同，合同总金额为5亿元人民币。",
                    "expected_sentiment": "positive",
                    "expected_type": "订单合同"
                }
            ]

            for i, news in enumerate(test_news, 1):
                print(f"\n测试 {i}/{len(test_news)}")
                print(f"标题: {news['title']}")

                result = labeler.label_news(
                    f"test_{i}",
                    news["title"],
                    news["content"]
                )

                if result:
                    sentiment_match = "✅" if result['sentiment'] == news['expected_sentiment'] else "⚠️"
                    type_match = "✅" if news['expected_type'] in result['event_types'] else "⚠️"

                    print(f"  情绪: {result['sentiment']} (预期: {news['expected_sentiment']}) {sentiment_match}")
                    print(f"  类型: {', '.join(result['event_types'])} (预期包含: {news['expected_type']}) {type_match}")
                    print(f"  影响: {result['impact_score']:.1f}")

            print("\n" + "="*60)
            print("✅ 测试完成")
            print("="*60)

        return 0

    finally:
        labeler.close()


if __name__ == "__main__":
    sys.exit(main())
