#!/usr/bin/env python3
"""
框选区间分析器

功能：
1. 用户框选K线区间进行分析
2. 统计区间内的重大事件
3. 分析区间表现（收益、波动率等）
4. 识别关键事件和转折点
5. 生成AI总结和投资建议

数据库表：
- range_analysis: 存储区间分析结果
"""

import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import sys
import statistics
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
        logging.FileHandler(LOG_DIR / 'range_analyzer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RangeAnalyzer:
    """框选区间分析器"""

    def __init__(self, config_file: str = None, user_id: str = "default"):
        """
        初始化区间分析器

        Args:
            config_file: 配置文件路径
            user_id: 用户ID
        """
        self.config = self._load_config(config_file)
        self.user_id = user_id
        self.conn = self._get_db_connection()

    def _load_config(self, config_file: str = None) -> Dict:
        """加载配置"""
        if config_file is None:
            config_file = CONFIG_DIR / "event_analysis_config.json"

        if Path(config_file).exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("range_analysis", {})
        return {
            "enabled": True,
            "default_days_range": 30
        }

    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(DATABASE_PATH)

    def _get_kline_range(self, stock_code: str, start_date: str,
                         end_date: str) -> List[Dict]:
        """
        获取K线区间数据

        Args:
            stock_code: 股票代码
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

    def _get_range_events(self, stock_code: str, start_date: str,
                         end_date: str) -> List[Dict]:
        """
        获取区间内的事件

        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            事件列表
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                SELECT eka.*, nl.title, nl.sentiment, nl.event_types, nl.impact_score
                FROM event_kline_associations eka
                JOIN news_labels nl ON eka.news_id = nl.news_id
                WHERE eka.stock_code = ? AND eka.kline_start_date BETWEEN ? AND ?
                ORDER BY eka.kline_start_date ASC
            """, (stock_code, start_date, end_date))
        except sqlite3.OperationalError:
            return []

        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _calculate_range_metrics(self, klines: List[Dict]) -> Dict:
        """
        计算区间指标

        Args:
            klines: K线数据列表

        Returns:
            区间指标
        """
        if not klines:
            return {
                "start_price": 0,
                "end_price": 0,
                "high_price": 0,
                "low_price": 0,
                "total_return": 0,
                "volatility": 0
            }

        start_price = klines[0]["open"]
        end_price = klines[-1]["close"]
        high_price = max(k["high"] for k in klines)
        low_price = min(k["low"] for k in klines)

        total_return = (end_price - start_price) / start_price * 100

        # 计算波动率（基于日收益率）
        daily_returns = []
        for i in range(1, len(klines)):
            ret = (klines[i]["close"] - klines[i-1]["close"]) / klines[i-1]["close"]
            daily_returns.append(ret)

        volatility = statistics.stdev(daily_returns) * 100 if len(daily_returns) > 1 else 0

        return {
            "start_price": start_price,
            "end_price": end_price,
            "high_price": high_price,
            "low_price": low_price,
            "total_return": total_return,
            "volatility": volatility
        }

    def _analyze_events_impact(self, events: List[Dict]) -> Dict:
        """
        分析事件影响

        Args:
            events: 事件列表

        Returns:
            事件影响分析
        """
        positive_events = [e for e in events if e["sentiment"] == "positive"]
        negative_events = [e for e in events if e["sentiment"] == "negative"]

        # 计算平均影响
        avg_impact = sum(e.get("impact_score", 0) for e in events) / len(events) if events else 0

        # 识别关键事件
        key_events = sorted(
            events,
            key=lambda x: x.get("impact_score", 0),
            reverse=True
        )[:3]

        return {
            "event_count": len(events),
            "positive_events": len(positive_events),
            "negative_events": len(negative_events),
            "avg_impact": avg_impact,
            "key_events": key_events
        }

    def _generate_ai_summary(self, metrics: Dict, event_analysis: Dict,
                           stock_info: Dict) -> Tuple[str, str, List[Dict]]:
        """
        生成AI分析

        Args:
            metrics: 区间指标
            event_analysis: 事件分析
            stock_info: 股票信息

        Returns:
            (总结, 见解, 建议)
        """
        summary_parts = []

        # 表现总结
        if metrics["total_return"] > 10:
            summary_parts.append(f"{stock_info['name']}({stock_info['symbol']})在分析区间内表现优异，"
                              f"上涨{metrics['total_return']:.1f}%")
        elif metrics["total_return"] > 0:
            summary_parts.append(f"{stock_info['name']}在分析区间内小幅上涨{metrics['total_return']:.1f}%")
        elif metrics["total_return"] > -10:
            summary_parts.append(f"{stock_info['name']}在分析区间内小幅下跌{abs(metrics['total_return']):.1f}%")
        else:
            summary_parts.append(f"{stock_info['name']}在分析区间内表现疲弱，"
                              f"下跌{abs(metrics['total_return']):.1f}%")

        # 波动性
        if metrics["volatility"] > 3:
            summary_parts.append("波动较大")
        elif metrics["volatility"] > 1.5:
            summary_parts.append("波动适中")
        else:
            summary_parts.append("波动较小")

        # 事件总结
        if event_analysis["event_count"] > 0:
            summary_parts.append(f"共发生{event_analysis['event_count']}起相关事件")
            if event_analysis["positive_events"] > event_analysis["negative_events"]:
                summary_parts.append("以利好事件为主")
            elif event_analysis["negative_events"] > event_analysis["positive_events"]:
                summary_parts.append("以利空事件为主")

        summary = "，".join(summary_parts) + "。"

        # 生成见解
        insights = []

        if metrics["volatility"] > 2.5:
            insights.append("区间内波动率较高，显示股价受消息面影响较大，适合短线交易")

        if metrics["total_return"] > 5 and event_analysis["positive_events"] > event_analysis["negative_events"]:
            insights.append("利好事件对股价产生明显推动作用，市场对公司前景乐观")

        if metrics["total_return"] < -5 and event_analysis["negative_events"] > 0:
            insights.append("利空事件对股价造成打击，市场情绪偏谨慎")

        if abs(metrics["total_return"]) < 3 and metrics["volatility"] < 1:
            insights.append("区间内走势平稳，消息面影响有限，适合中长期持有")

        insights_text = "\n".join(f"• {insight}" for insight in insights) if insights else "无明显规律"

        # 生成建议
        recommendations = []

        if metrics["total_return"] > 5 and metrics["volatility"] < 2:
            recommendations.append({
                "action": "持有",
                "reason": "区间内表现稳定且上涨，建议继续持有"
            })

        if metrics["total_return"] > 10 and metrics["volatility"] > 3:
            recommendations.append({
                "action": "减仓",
                "reason": "涨幅较大且波动率高，建议适当减仓锁定收益"
            })

        if metrics["total_return"] < -10:
            recommendations.append({
                "action": "观望",
                "reason": "跌幅较大，建议等待企稳信号"
            })

        if event_analysis["positive_events"] > 2 and metrics["total_return"] < 0:
            recommendations.append({
                "action": "关注",
                "reason": "利好事件较多但股价未反映，存在机会"
            })

        if not recommendations:
            recommendations.append({
                "action": "中性",
                "reason": "根据当前情况无明确操作建议"
            })

        return summary, insights_text, recommendations

    def analyze_range(self, stock_code: str, start_date: str, end_date: str,
                     session_id: str = None) -> Optional[Dict]:
        """
        分析K线区间

        Args:
            stock_code: 股票代码
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            session_id: 会话ID

        Returns:
            分析结果
        """
        # 获取股票信息
        stock_info = self._get_stock_info(stock_code)
        if not stock_info:
            logger.warning(f"未找到股票信息: {stock_code}")
            return None

        # 获取K线数据
        klines = self._get_kline_range(stock_code, start_date, end_date)
        if not klines:
            logger.warning(f"未找到K线数据: {stock_code} {start_date} ~ {end_date}")
            return None

        # 计算区间指标
        metrics = self._calculate_range_metrics(klines)

        # 获取区间内事件
        events = self._get_range_events(stock_code, start_date, end_date)
        event_analysis = self._analyze_events_impact(events)

        # 生成AI分析
        summary, insights, recommendations = self._generate_ai_summary(
            metrics, event_analysis, stock_info
        )

        # 准备结果
        result = {
            "user_id": self.user_id,
            "session_id": session_id or datetime.now().strftime("%Y%m%d%H%M%S"),
            "stock_code": stock_code,
            "stock_name": stock_info["name"],
            "start_date": start_date,
            "end_date": end_date,
            **metrics,
            **event_analysis,
            "ai_summary": summary,
            "ai_insights": insights,
            "key_events": json.dumps(event_analysis["key_events"], ensure_ascii=False),
            "recommendations": json.dumps(recommendations, ensure_ascii=False)
        }

        # 保存到数据库
        self._save_analysis(result)

        logger.info(f"✅ 区间分析完成: {stock_code} {start_date} ~ {end_date}")
        logger.info(f"   收益: {metrics['total_return']:+.2f}%")
        logger.info(f"   事件: {event_analysis['event_count']}个")

        return result

    def _save_analysis(self, data: Dict):
        """保存分析到数据库"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO range_analysis (
                user_id, session_id, stock_code, stock_name, start_date, end_date,
                start_price, end_price, high_price, low_price, total_return, volatility,
                event_count, positive_events, negative_events, event_summary,
                ai_summary, ai_insights, key_events, recommendations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["user_id"],
            data["session_id"],
            data["stock_code"],
            data["stock_name"],
            data["start_date"],
            data["end_date"],
            data["start_price"],
            data["end_price"],
            data["high_price"],
            data["low_price"],
            data["total_return"],
            data["volatility"],
            data["event_count"],
            data["positive_events"],
            data["negative_events"],
            f"共{data['event_count']}起事件，"
            f"利好{data['positive_events']}起，利空{data['negative_events']}起",
            data["ai_summary"],
            data["ai_insights"],
            data["key_events"],
            data["recommendations"]
        ))

        self.conn.commit()

    def get_analysis_history(self, stock_code: str = None,
                           limit: int = 20) -> List[Dict]:
        """
        获取分析历史

        Args:
            stock_code: 股票代码过滤
            limit: 最大数量

        Returns:
            分析历史列表
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM range_analysis WHERE 1=1"
        params = []

        if stock_code:
            query += " AND stock_code = ?"
            params.append(stock_code)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def format_report(self, analysis: Dict) -> str:
        """
        格式化分析报告

        Args:
            analysis: 分析结果

        Returns:
            格式化的报告文本
        """
        lines = [
            "="*70,
            f"📊 区间分析报告",
            "="*70,
            f"",
            f"股票: {analysis['stock_name']} ({analysis['stock_code']})",
            f"区间: {analysis['start_date']} ~ {analysis['end_date']}",
            f"",
            f"💰 收益表现",
            f"  开盘价: ¥{analysis['start_price']:.2f}",
            f"  收盘价: ¥{analysis['end_price']:.2f}",
            f"  最高价: ¥{analysis['high_price']:.2f}",
            f"  最低价: ¥{analysis['low_price']:.2f}",
            f"  区间收益: {analysis['total_return']:+.2f}%",
            f"  波动率: {analysis['volatility']:.2f}%",
            f"",
            f"📰 事件统计",
            f"  事件总数: {analysis['event_count']}",
            f"  利好事件: {analysis['positive_events']}",
            f"  利空事件: {analysis['negative_events']}",
            f"",
            f"🤖 AI分析",
            f"  {analysis['ai_summary']}",
            f"",
            f"💡 关键见解:",
        ]

        insights = analysis['ai_insights'].split('\n') if analysis['ai_insights'] else []
        for insight in insights:
            lines.append(f"  {insight}")

        lines.append("")
        lines.append("📋 投资建议:")

        recommendations = json.loads(analysis['recommendations']) if analysis.get('recommendations') else []
        for rec in recommendations:
            lines.append(f"  • {rec['action']}: {rec['reason']}")

        lines.append("")
        lines.append("="*70)

        return "\n".join(lines)

    def close(self):
        """关闭数据库连接"""
        self.conn.close()


# ============================================================
# 命令行接口
# ============================================================

def main():
    """命令行接口"""
    parser = argparse.ArgumentParser(
        description="框选区间分析器 - 分析指定K线区间的表现和事件"
    )
    parser.add_argument(
        "action",
        choices=["analyze", "history", "report", "test"],
        help="操作类型"
    )
    parser.add_argument("--stock-code", type=str, help="股票代码")
    parser.add_argument("--start-date", type=str, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=20, help="列表数量限制")

    args = parser.parse_args()

    analyzer = RangeAnalyzer()

    try:
        if args.action == "analyze":
            # 分析区间
            if not all([args.stock_code, args.start_date, args.end_date]):
                print("❌ 错误: 需要提供 --stock-code, --start-date, --end-date 参数")
                return 1

            result = analyzer.analyze_range(
                args.stock_code,
                args.start_date,
                args.end_date
            )

            if result:
                print("\n" + analyzer.format_report(result))

        elif args.action == "history":
            # 查看历史
            history = analyzer.get_analysis_history(
                stock_code=args.stock_code,
                limit=args.limit
            )

            print(f"\n找到 {len(history)} 条分析记录:\n")

            for item in history:
                emoji = "🟢" if item['total_return'] > 0 else \
                        "🔴" if item['total_return'] < 0 else "⚪"
                print(f"{emoji} {item['stock_name']} ({item['stock_code']})")
                print(f"   区间: {item['start_date']} ~ {item['end_date']}")
                print(f"   收益: {item['total_return']:+.2f}% | "
                      f"事件: {item['event_count']}个 | "
                      f"波动: {item['volatility']:.2f}%")
                print()

        elif args.action == "report":
            # 生成报告
            history = analyzer.get_analysis_history(
                stock_code=args.stock_code,
                limit=1
            )

            if history:
                print("\n" + analyzer.format_report(history[0]))
            else:
                print("未找到分析记录")

        elif args.action == "test":
            # 测试功能
            print("\n" + "="*60)
            print("🧪 区间分析器测试")
            print("="*60)

            # 测试：分析一个最近30天的区间
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            print(f"\n测试区间: {start_date} ~ {end_date}")
            print("测试股票: 600000 (浦发银行)")

            result = analyzer.analyze_range("600000", start_date, end_date)

            if result:
                print("\n" + analyzer.format_report(result))
            else:
                print("⚠️ 分析失败（可能是数据不足）")

            print("\n" + "="*60)
            print("✅ 测试完成")
            print("="*60)

        return 0

    finally:
        analyzer.close()


if __name__ == "__main__":
    sys.exit(main())
