#!/usr/bin/env python3
"""
事件K线关联器

功能：
1. 将新闻事件与K线数据进行关联
2. 计算事件前后价格变化（1天、3天、5天、10天）
3. 分析事件的最大涨幅和最大回撤
4. 评估事件影响的置信度
5. 生成事件影响分析报告

数据库表：
- event_kline_associations: 存储事件-K线关联结果
"""

import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import sys
import re

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
        logging.FileHandler(LOG_DIR / 'event_kline_mapper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EventKlineMapper:
    """事件K线关联器"""

    def __init__(self, config_file: str = None):
        """
        初始化事件K线关联器

        Args:
            config_file: 配置文件路径
        """
        self.config = self._load_config(config_file)
        self.conn = self._get_db_connection()

    def _load_config(self, config_file: str = None) -> Dict:
        """加载配置"""
        if config_file is None:
            config_file = CONFIG_DIR / "event_analysis_config.json"

        if Path(config_file).exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("kline_mapping", {})
        return {
            "enabled": True,
            "auto_map": True,
            "days_after_event": 5,
            "min_impact_threshold": 10
        }

    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(DATABASE_PATH)

    def _parse_stock_code(self, code_str: str) -> Optional[str]:
        """
        解析股票代码

        Args:
            code_str: 股票代码字符串（可能是 sh.600000 或 600000）

        Returns:
            标准化的股票代码格式
        """
        if not code_str:
            return None

        # 移除前缀
        code = re.sub(r'^(sh|sz|\.)([0-9]{6})', r'\2', code_str)
        code = code.strip()

        # 验证格式
        if re.match(r'^[0-9]{6}$', code):
            return code

        return None

    def _get_kline_data(self, stock_code: str, start_date: str,
                        end_date: str) -> List[Dict]:
        """
        获取K线数据

        Args:
            stock_code: 股票代码（6位数字）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            K线数据列表
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                SELECT date, open, high, low, close, volume
                FROM kline_daily
                WHERE symbol = ? AND date BETWEEN ? AND ?
                ORDER BY date ASC
            """, (stock_code, start_date, end_date))
        except sqlite3.OperationalError:
            logger.warning(f"kline_daily表不存在，无法获取K线数据")
            return []

        rows = cursor.fetchall()
        return [
            {
                "date": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5]
            }
            for row in rows
        ]

    def _get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                SELECT symbol, name, industry
                FROM stocks
                WHERE symbol = ?
                LIMIT 1
            """, (stock_code,))
        except sqlite3.OperationalError:
            return None

        row = cursor.fetchone()
        if row:
            return {
                "symbol": row[0],
                "name": row[1],
                "industry": row[2]
            }
        return None

    def _calculate_event_impact(self, pre_event_price: float,
                               post_event_klines: List[Dict]) -> Dict:
        """
        计算事件影响

        Args:
            pre_event_price: 事件前价格
            post_event_klines: 事件后K线数据

        Returns:
            影响分析结果
        """
        if not post_event_klines:
            return {
                "max_gain": 0,
                "max_drawdown": 0,
                "day1_change": 0,
                "day3_change": 0,
                "day5_change": 0,
                "day10_change": 0,
                "post_event_high": pre_event_price,
                "post_event_low": pre_event_price
            }

        max_high = max(k["high"] for k in post_event_klines)
        min_low = min(k["low"] for k in post_event_klines)

        max_gain = (max_high - pre_event_price) / pre_event_price * 100
        max_drawdown = (pre_event_price - min_low) / pre_event_price * 100

        # 计算各天涨跌幅
        day1_change = 0
        day3_change = 0
        day5_change = 0
        day10_change = 0

        if len(post_event_klines) >= 1:
            day1_change = (post_event_klines[0]["close"] - pre_event_price) / pre_event_price * 100

        if len(post_event_klines) >= 3:
            day3_change = (post_event_klines[2]["close"] - pre_event_price) / pre_event_price * 100

        if len(post_event_klines) >= 5:
            day5_change = (post_event_klines[4]["close"] - pre_event_price) / pre_event_price * 100

        if len(post_event_klines) >= 10:
            day10_change = (post_event_klines[9]["close"] - pre_event_price) / pre_event_price * 100

        return {
            "max_gain": max_gain,
            "max_drawdown": max_drawdown,
            "day1_change": day1_change,
            "day3_change": day3_change,
            "day5_change": day5_change,
            "day10_change": day10_change,
            "post_event_high": max_high,
            "post_event_low": min_low
        }

    def map_news_to_kline(self, news_id: str, stock_code: str = None) -> List[Dict]:
        """
        将新闻关联到K线数据

        Args:
            news_id: 新闻ID
            stock_code: 股票代码（如果为None，从新闻标签中提取）

        Returns:
            关联结果列表
        """
        # 获取新闻信息
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT news_id, title, content, affected_stocks, news_time
            FROM news_labels
            WHERE news_id = ?
        """, (news_id,))

        news_row = cursor.fetchone()
        if not news_row:
            logger.warning(f"未找到新闻: {news_id}")
            return []

        news = {
            "news_id": news_row[0],
            "title": news_row[1],
            "content": news_row[2],
            "affected_stocks": json.loads(news_row[3]) if news_row[3] else [],
            "news_time": news_row[4]
        }

        # 确定要分析的股票代码
        if stock_code:
            stocks = [stock_code]
        else:
            stocks = [self._parse_stock_code(s) for s in news["affected_stocks"]
                     if self._parse_stock_code(s)]

        if not stocks:
            logger.warning(f"没有可用的股票代码")
            return []

        results = []

        # 事件日期
        event_date_str = news["news_time"]
        if event_date_str:
            try:
                event_date = datetime.strptime(event_date_str[:10], "%Y-%m-%d")
            except:
                event_date = datetime.now()
        else:
            event_date = datetime.now()

        # 获取事件前的价格
        pre_date = event_date - timedelta(days=1)
        post_days = self.config.get("days_after_event", 5)
        post_date = event_date + timedelta(days=post_days)

        for stock_code in stocks:
            stock_info = self._get_stock_info(stock_code)
            if not stock_info:
                logger.warning(f"未找到股票信息: {stock_code}")
                continue

            # 获取事件前价格（前一交易日）
            pre_klines = self._get_kline_data(
                stock_code,
                pre_date.strftime("%Y-%m-%d"),
                pre_date.strftime("%Y-%m-%d")
            )

            pre_event_close = pre_klines[0]["close"] if pre_klines else None
            if not pre_event_close:
                logger.warning(f"未找到事件前价格: {stock_code}")
                continue

            # 获取事件后K线数据
            post_klines = self._get_kline_data(
                stock_code,
                event_date.strftime("%Y-%m-%d"),
                post_date.strftime("%Y-%m-%d")
            )

            # 计算影响
            impact = self._calculate_event_impact(pre_event_close, post_klines)

            # 计算关联强度
            impact_score = abs(impact["day1_change"])
            association_strength = min(1.0, impact_score / 10)  # 10%涨跌幅为满强度

            # 关联类型
            if impact["day1_change"] > 5:
                association_type = "strong_positive"
            elif impact["day1_change"] > 2:
                association_type = "positive"
            elif impact["day1_change"] < -5:
                association_type = "strong_negative"
            elif impact["day1_change"] < -2:
                association_type = "negative"
            else:
                association_type = "neutral"

            # 计算置信度
            confidence_score = 0.5
            if len(post_klines) >= 3:
                confidence_score = 0.7
            if len(post_klines) >= 5:
                confidence_score = 0.8

            # 准备数据
            result = {
                "news_id": news_id,
                "stock_code": stock_code,
                "stock_name": stock_info.get("name", ""),
                "association_type": association_type,
                "association_strength": association_strength,
                "kline_start_date": event_date.strftime("%Y-%m-%d"),
                "kline_end_date": post_date.strftime("%Y-%m-%d"),
                "pre_event_close": pre_event_close,
                **impact,
                "ai_analysis": self._generate_ai_analysis(news, impact),
                "confidence_score": confidence_score
            }

            # 保存到数据库
            self._save_association(result)

            results.append(result)

            logger.info(f"✅ 关联成功: {news_id} -> {stock_code}")
            logger.info(f"   类型: {association_type}, 强度: {association_strength:.2f}")
            logger.info(f"   涨跌: {impact['day1_change']:+.2f}%, "
                       f"最大涨幅: {impact['max_gain']:+.2f}%, "
                       f"最大回撤: {impact['max_drawdown']:+.2f}%")

        return results

    def _generate_ai_analysis(self, news: Dict, impact: Dict) -> str:
        """生成AI分析文本"""
        analysis_parts = []

        # 情绪描述
        if impact["day1_change"] > 5:
            analysis_parts.append("该事件对股价产生强烈正面影响，首日大涨")
        elif impact["day1_change"] > 2:
            analysis_parts.append("该事件对股价产生正面影响")
        elif impact["day1_change"] < -5:
            analysis_parts.append("该事件对股价产生强烈负面影响，首日大跌")
        elif impact["day1_change"] < -2:
            analysis_parts.append("该事件对股价产生负面影响")
        else:
            analysis_parts.append("该事件对股价影响较小")

        # 持续性分析
        if abs(impact["day5_change"]) > abs(impact["day1_change"]):
            analysis_parts.append("影响持续增强")
        elif abs(impact["day5_change"]) < abs(impact["day1_change"]) * 0.5:
            analysis_parts.append("影响快速消退")
        else:
            analysis_parts.append("影响相对稳定")

        # 波动性分析
        if impact["max_gain"] > 10 and impact["max_drawdown"] < -5:
            analysis_parts.append("短期波动较大，存在交易机会")
        elif impact["max_drawdown"] < -10:
            analysis_parts.append("存在较大回撤风险")

        return "。".join(analysis_parts)

    def _save_association(self, data: Dict):
        """保存关联到数据库"""
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO event_kline_associations (
                    news_id, stock_code, stock_name, association_type, association_strength,
                    kline_start_date, kline_end_date, pre_event_close,
                    post_event_high, post_event_low, post_event_days,
                    max_gain, max_drawdown, ai_analysis, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["news_id"],
                data["stock_code"],
                data["stock_name"],
                data["association_type"],
                data["association_strength"],
                data["kline_start_date"],
                data["kline_end_date"],
                data["pre_event_close"],
                data["post_event_high"],
                data["post_event_low"],
                len(self._get_kline_data(data["stock_code"],
                                        data["kline_start_date"],
                                        data["kline_end_date"])),
                data["max_gain"],
                data["max_drawdown"],
                data["ai_analysis"],
                data["confidence_score"]
            ))

            self.conn.commit()
        except sqlite3.IntegrityError:
            # 已存在，更新
            cursor.execute("""
                UPDATE event_kline_associations
                SET association_type = ?, association_strength = ?,
                    post_event_high = ?, post_event_low = ?,
                    max_gain = ?, max_drawdown = ?,
                    ai_analysis = ?, confidence_score = ?
                WHERE news_id = ? AND stock_code = ? AND kline_start_date = ?
            """, (
                data["association_type"],
                data["association_strength"],
                data["post_event_high"],
                data["post_event_low"],
                data["max_gain"],
                data["max_drawdown"],
                data["ai_analysis"],
                data["confidence_score"],
                data["news_id"],
                data["stock_code"],
                data["kline_start_date"]
            ))
            self.conn.commit()

    def get_associations(self, news_id: str = None, stock_code: str = None,
                       association_type: str = None, limit: int = 100) -> List[Dict]:
        """
        获取关联记录

        Args:
            news_id: 新闻ID过滤
            stock_code: 股票代码过滤
            association_type: 关联类型过滤
            limit: 最大数量

        Returns:
            关联记录列表
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM event_kline_associations WHERE 1=1"
        params = []

        if news_id:
            query += " AND news_id = ?"
            params.append(news_id)

        if stock_code:
            query += " AND stock_code = ?"
            params.append(stock_code)

        if association_type:
            query += " AND association_type = ?"
            params.append(association_type)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_stock_event_history(self, stock_code: str, days: int = 30) -> List[Dict]:
        """
        获取股票的事件历史

        Args:
            stock_code: 股票代码
            days: 最近天数

        Returns:
            事件历史列表
        """
        cursor = self.conn.cursor()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        cursor.execute("""
            SELECT eka.*, nl.title, nl.sentiment, nl.event_types
            FROM event_kline_associations eka
            JOIN news_labels nl ON eka.news_id = nl.news_id
            WHERE eka.stock_code = ? AND eka.kline_start_date >= ?
            ORDER BY eka.kline_start_date DESC
        """, (stock_code, start_date.strftime("%Y-%m-%d")))

        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def auto_map_recent_news(self):
        """自动关联最近的新闻"""
        if not self.config.get("auto_map", False):
            logger.info("自动关联未启用")
            return

        logger.info("开始自动关联最近的新闻...")

        # 获取最近7天的新闻
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT news_id, news_time
            FROM news_labels
            WHERE news_time >= datetime('now', '-7 days')
            AND news_id NOT IN (
                SELECT news_id FROM event_kline_associations
            )
            LIMIT 20
        """)

        news_items = cursor.fetchall()

        if not news_items:
            logger.info("没有需要关联的新闻")
            return

        logger.info(f"找到 {len(news_items)} 条未关联新闻")

        for news_id, _ in news_items:
            try:
                self.map_news_to_kline(news_id)
            except Exception as e:
                logger.error(f"关联失败 {news_id}: {e}")

        logger.info("✅ 自动关联完成")

    def close(self):
        """关闭数据库连接"""
        self.conn.close()


# ============================================================
# 命令行接口
# ============================================================

def main():
    """命令行接口"""
    parser = argparse.ArgumentParser(
        description="事件K线关联器 - 将新闻事件与K线数据关联"
    )
    parser.add_argument(
        "action",
        choices=["map", "list", "history", "auto", "test"],
        help="操作类型"
    )
    parser.add_argument("--news-id", type=str, help="新闻ID")
    parser.add_argument("--stock-code", type=str, help="股票代码")
    parser.add_argument("--type", type=str, help="关联类型过滤")
    parser.add_argument("--days", type=int, default=30, help="历史天数")
    parser.add_argument("--limit", type=int, default=20, help="列表数量限制")

    args = parser.parse_args()

    mapper = EventKlineMapper()

    try:
        if args.action == "map":
            # 关联新闻
            if not args.news_id:
                print("❌ 错误: 需要提供 --news-id 参数")
                return 1

            results = mapper.map_news_to_kline(args.news_id, args.stock_code)

            print(f"\n✅ 完成: 关联了 {len(results)} 个股票")
            for result in results:
                emoji = "🟢" if result['association_type'] in ['positive', 'strong_positive'] else \
                        "🔴" if result['association_type'] in ['negative', 'strong_negative'] else "⚪"
                print(f"{emoji} {result['stock_name']} ({result['stock_code']})")
                print(f"   类型: {result['association_type']}, "
                      f"首日涨跌: {result.get('day1_change', 0):+.2f}%")

        elif args.action == "list":
            # 列出关联记录
            associations = mapper.get_associations(
                news_id=args.news_id,
                stock_code=args.stock_code,
                association_type=args.type,
                limit=args.limit
            )

            print(f"\n找到 {len(associations)} 条关联记录:\n")

            for assoc in associations:
                emoji = "🟢" if assoc['association_type'] in ['positive', 'strong_positive'] else \
                        "🔴" if assoc['association_type'] in ['negative', 'strong_negative'] else "⚪"

                print(f"{emoji} {assoc['stock_name']} ({assoc['stock_code']}) - {assoc['news_id']}")
                print(f"   类型: {assoc['association_type']} | "
                      f"强度: {assoc['association_strength']:.2f} | "
                      f"首日: {assoc.get('day1_change', 0):+.2f}% | "
                      f"最大: {assoc['max_gain']:+.2f}% / {assoc['max_drawdown']:+.2f}%")
                print(f"   分析: {assoc['ai_analysis']}")
                print()

        elif args.action == "history":
            # 股票事件历史
            if not args.stock_code:
                print("❌ 错误: 需要提供 --stock-code 参数")
                return 1

            history = mapper.get_stock_event_history(args.stock_code, args.days)

            print(f"\n{args.stock_code} 最近{args.days}天的事件历史 ({len(history)}条):\n")

            for item in history:
                print(f"📅 {item['kline_start_date']} - {item['title'][:50]}")
                print(f"   情绪: {item['sentiment']} | "
                      f"类型: {item['event_types']}")
                print(f"   影响: 首日 {item.get('day1_change', 0):+.2f}%, "
                      f"最大 {item['max_gain']:+.2f}%")
                print()

        elif args.action == "auto":
            # 自动关联
            mapper.auto_map_recent_news()

        elif args.action == "test":
            # 测试功能
            print("\n" + "="*60)
            print("🧪 事件K线关联器测试")
            print("="*60)

            # 测试：关联一个模拟新闻
            test_news_id = f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # 先插入一条测试新闻
            cursor = mapper.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO news_labels (
                    news_id, title, content, sentiment, sentiment_confidence,
                    event_types, affected_stocks, impact_score, news_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_news_id,
                "公司发布重大利好消息",
                "公司今日发布公告称，获得政府重大项目订单，金额约10亿元。",
                "positive",
                0.8,
                json.dumps(["订单合同"]),
                json.dumps(["600000"]),  # 测试股票代码
                75.0,
                datetime.now().strftime("%Y-%m-%d")
            ))
            mapper.conn.commit()

            print(f"\n创建测试新闻: {test_news_id}")

            # 尝试关联
            results = mapper.map_news_to_kline(test_news_id)

            if results:
                print(f"✅ 关联成功，共 {len(results)} 个股票")
            else:
                print("⚠️ 关联失败（可能是K线数据不足）")

            print("\n" + "="*60)
            print("✅ 测试完成")
            print("="*60)

        return 0

    finally:
        mapper.close()


if __name__ == "__main__":
    sys.exit(main())
