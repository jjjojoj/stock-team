#!/usr/bin/env python3
"""
预测系统集成器

功能：
1. 将事件分析结果整合到预测系统
2. 基于历史事件学习和验证
3. 生成事件驱动的交易规则
4. 更新预测置信度
5. 持续学习和改进

数据库表：
- event_impact_history: 存储事件影响历史（用于学习）
"""

import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import sys
from collections import defaultdict

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_PATH = PROJECT_ROOT / "database" / "stock_team.db"
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"
LEARNING_DIR = PROJECT_ROOT / "learning"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LEARNING_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'prediction_integration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PredictionIntegrator:
    """预测系统集成器"""

    def __init__(self, config_file: str = None):
        """
        初始化预测系统集成器

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
                return {
                    "prediction_integration": config.get("prediction_integration", {}),
                    "learning": config.get("learning", {})
                }
        return {
            "prediction_integration": {
                "enabled": False,
                "update_threshold": 15,
                "confidence_boost": 10
            },
            "learning": {
                "enabled": True,
                "min_sample_size": 5,
                "accuracy_threshold": 0.6
            }
        }

    def _get_db_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(DATABASE_PATH)

    def _get_event_associations(self, days: int = 30) -> List[Dict]:
        """
        获取最近的关联事件

        Args:
            days: 天数

        Returns:
            关联事件列表
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                SELECT eka.*, nl.sentiment, nl.event_types, nl.impact_score
                FROM event_kline_associations eka
                JOIN news_labels nl ON eka.news_id = nl.news_id
                WHERE eka.kline_start_date >= date('now', '-{} days')
                ORDER BY eka.kline_start_date DESC
            """.format(days))
        except sqlite3.OperationalError:
            return []

        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _get_predictions(self, stock_code: str = None,
                        days: int = 7) -> List[Dict]:
        """
        获取预测记录

        Args:
            stock_code: 股票代码过滤
            days: 天数

        Returns:
            预测记录列表
        """
        cursor = self.conn.cursor()

        try:
            if stock_code:
                cursor.execute("""
                    SELECT * FROM predictions
                    WHERE symbol = ? AND created_at >= date('now', '-{} days')
                    ORDER BY created_at DESC
                """.format(days), (stock_code,))
            else:
                cursor.execute("""
                    SELECT * FROM predictions
                    WHERE created_at >= date('now', '-{} days')
                    ORDER BY created_at DESC
                    LIMIT 50
                """.format(days))
        except sqlite3.OperationalError:
            return []

        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _verify_event_prediction(self, news_id: str, stock_code: str) -> Optional[Dict]:
        """
        验证事件预测的准确性

        Args:
            news_id: 新闻ID
            stock_code: 股票代码

        Returns:
            验证结果
        """
        # 获取事件关联
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM event_kline_associations
            WHERE news_id = ? AND stock_code = ?
        """, (news_id, stock_code))

        association = cursor.fetchone()
        if not association:
            return None

        columns = [desc[0] for desc in cursor.description]
        assoc_data = dict(zip(columns, association))

        # 获取新闻标签
        cursor.execute("""
            SELECT sentiment, event_types, impact_score
            FROM news_labels
            WHERE news_id = ?
        """, (news_id,))

        news_row = cursor.fetchone()
        if not news_row:
            return None

        sentiment, event_types_str, impact_score = news_row
        event_types = json.loads(event_types_str) if event_types_str else []

        # 确定预测方向
        predicted_direction = "up" if sentiment == "positive" else \
                           "down" if sentiment == "negative" else "neutral"

        # 确定实际方向
        actual_change = assoc_data.get("day1_change", 0)
        actual_direction = "up" if actual_change > 1 else \
                         "down" if actual_change < -1 else "neutral"

        # 验证准确性
        prediction_accuracy = 1.0 if predicted_direction == actual_direction else 0.0

        # 提取教训
        lesson_learned = self._extract_lesson(
            predicted_direction, actual_direction,
            sentiment, actual_change
        )

        # 生成规则建议
        rule_suggestion = self._generate_rule_suggestion(
            event_types, sentiment, prediction_accuracy
        )

        return {
            "news_id": news_id,
            "stock_code": stock_code,
            "predicted_direction": predicted_direction,
            "actual_direction": actual_direction,
            "predicted_impact": impact_score,
            "actual_impact": abs(actual_change),
            "day1_change": actual_change,
            "day3_change": assoc_data.get("day3_change", 0),
            "day5_change": assoc_data.get("day5_change", 0),
            "day10_change": assoc_data.get("day10_change", 0),
            "prediction_accuracy": prediction_accuracy,
            "lesson_learned": lesson_learned,
            "rule_suggestion": rule_suggestion
        }

    def _extract_lesson(self, predicted: str, actual: str,
                      sentiment: str, actual_change: float) -> str:
        """提取教训"""
        if predicted == actual:
            if abs(actual_change) > 5:
                return f"验证成功：{sentiment}情绪与实际走势一致，影响显著"
            return f"验证成功：{sentiment}情绪预测准确"

        if sentiment == "positive" and actual_change <= 0:
            if actual_change < -5:
                return f"预测失败：利好消息被市场解读为利空，可能是市场提前反映或消息已兑现"
            return f"预测偏差：利好消息未推动上涨，市场反应不足"

        if sentiment == "negative" and actual_change >= 0:
            if actual_change > 5:
                return f"预测失败：利空消息被市场解读为利好，可能是利空出尽"
            return f"预测偏差：利空消息未导致下跌，市场情绪过度悲观"

        return f"预测偏差：情绪{sentiment}与实际方向{actual}不符"

    def _generate_rule_suggestion(self, event_types: List[str],
                                 sentiment: str, accuracy: float) -> str:
        """生成规则建议"""
        if accuracy >= 0.8:
            type_str = ", ".join(event_types[:2])
            return f"可生成规则：{type_str} + {sentiment}情绪 → 高置信度交易信号"

        if accuracy < 0.3:
            type_str = ", ".join(event_types[:2])
            return f"需谨慎：{type_str} + {sentiment}情绪组合预测准确率低，不宜单独使用"

        return f"需更多样本：{sentiment}情绪事件需更多验证"

    def _save_impact_history(self, data: Dict):
        """保存影响历史"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO event_impact_history (
                news_id, stock_code, predicted_direction, actual_direction,
                predicted_impact, actual_impact, day1_change, day3_change,
                day5_change, day10_change, prediction_accuracy,
                lesson_learned, rule_suggestion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["news_id"],
            data["stock_code"],
            data["predicted_direction"],
            data["actual_direction"],
            data["predicted_impact"],
            data["actual_impact"],
            data["day1_change"],
            data["day3_change"],
            data["day5_change"],
            data["day10_change"],
            data["prediction_accuracy"],
            data["lesson_learned"],
            data["rule_suggestion"]
        ))

        self.conn.commit()

    def update_prediction_confidence(self, prediction_id: int,
                                  event_news_id: str) -> bool:
        """
        更新预测置信度

        Args:
            prediction_id: 预测ID
            event_news_id: 关联的新闻ID

        Returns:
            是否成功
        """
        config = self.config["prediction_integration"]
        if not config.get("enabled", False):
            logger.info("预测集成未启用")
            return False

        # 获取事件影响
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT sentiment, impact_score, event_types
            FROM news_labels
            WHERE news_id = ?
        """, (event_news_id,))

        news_row = cursor.fetchone()
        if not news_row:
            return False

        sentiment, impact_score, event_types_str = news_row

        # 检查影响分数是否达到阈值
        threshold = config.get("update_threshold", 15)
        if impact_score < threshold:
            logger.debug(f"影响分数 {impact_score} 低于阈值 {threshold}，不更新")
            return False

        # 计算置信度提升
        boost = config.get("confidence_boost", 10)

        # 更新预测置信度
        cursor.execute("""
            UPDATE predictions
            SET confidence = MIN(100, confidence + ?),
                event_enhanced = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (boost, prediction_id))

        self.conn.commit()

        logger.info(f"✅ 更新预测 {prediction_id} 置信度 +{boost}%")
        return True

    def verify_and_learn(self, days: int = 10):
        """
        验证并学习

        Args:
            days: 验证最近N天的事件
        """
        learning_config = self.config["learning"]
        if not learning_config.get("enabled", True):
            logger.info("学习功能未启用")
            return

        logger.info(f"开始验证最近 {days} 天的事件...")

        # 获取需要验证的事件
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT eka.news_id, eka.stock_code
            FROM event_kline_associations eka
            WHERE eka.kline_start_date >= date('now', '-{} days')
            AND eka.news_id NOT IN (
                SELECT news_id FROM event_impact_history
            )
            LIMIT 50
        """.format(days))

        items = cursor.fetchall()

        if not items:
            logger.info("没有需要验证的事件")
            return

        logger.info(f"找到 {len(items)} 个待验证事件")

        # 验证每个事件
        for news_id, stock_code in items:
            try:
                result = self._verify_event_prediction(news_id, stock_code)
                if result:
                    self._save_impact_history(result)
                    logger.info(f"✅ 验证完成: {news_id} -> {stock_code}")
            except Exception as e:
                logger.error(f"验证失败 {news_id} {stock_code}: {e}")

        # 学习和生成规则
        self._learn_and_generate_rules()

        logger.info("✅ 验证和学习完成")

    def _learn_and_generate_rules(self):
        """学习并生成规则"""
        learning_config = self.config["learning"]
        min_samples = learning_config.get("min_sample_size", 5)
        accuracy_threshold = learning_config.get("accuracy_threshold", 0.6)

        # 获取历史验证结果
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT event_types, sentiment, prediction_accuracy, rule_suggestion
            FROM event_impact_history
            ORDER BY verified_at DESC
            LIMIT 100
        """)

        results = cursor.fetchall()

        # 按事件类型和情绪分组统计
        stats = defaultdict(lambda: {"count": 0, "correct": 0})

        for event_types_str, sentiment, accuracy, suggestion in results:
            if not event_types_str:
                continue

            event_types = json.loads(event_types_str)
            for event_type in event_types:
                key = f"{event_type}_{sentiment}"
                stats[key]["count"] += 1
                if accuracy >= accuracy_threshold:
                    stats[key]["correct"] += 1

        # 生成高置信度规则
        high_confidence_rules = []

        for key, data in stats.items():
            if data["count"] >= min_samples:
                accuracy = data["correct"] / data["count"]
                if accuracy >= accuracy_threshold:
                    high_confidence_rules.append({
                        "pattern": key,
                        "accuracy": accuracy,
                        "samples": data["count"]
                    })

        # 保存到学习文件
        if high_confidence_rules:
            rules_file = LEARNING_DIR / "event_rules.json"

            existing_rules = []
            if rules_file.exists():
                with open(rules_file, 'r', encoding='utf-8') as f:
                    existing_rules = json.load(f)

            # 合并规则
            existing_dict = {r["pattern"]: r for r in existing_rules}
            for rule in high_confidence_rules:
                existing_dict[rule["pattern"]] = {
                    "pattern": rule["pattern"],
                    "accuracy": rule["accuracy"],
                    "samples": rule["samples"],
                    "updated_at": datetime.now().isoformat()
                }

            with open(rules_file, 'w', encoding='utf-8') as f:
                json.dump(list(existing_dict.values()), f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 生成/更新 {len(high_confidence_rules)} 条高置信度规则")

    def get_learning_progress(self) -> Dict:
        """
        获取学习进度

        Returns:
            学习进度信息
        """
        cursor = self.conn.cursor()

        # 统计验证数量
        cursor.execute("SELECT COUNT(*) FROM event_impact_history")
        total_verified = cursor.fetchone()[0]

        # 统计准确率
        cursor.execute("""
            SELECT AVG(prediction_accuracy) * 100,
                   COUNT(CASE WHEN prediction_accuracy >= 0.8 THEN 1 END),
                   COUNT(*)
            FROM event_impact_history
        """)
        row = cursor.fetchone()
        avg_accuracy = row[0] or 0
        high_conf_count = row[1] or 0
        total_count = row[2] or 0

        # 获取规则数量
        rules_file = LEARNING_DIR / "event_rules.json"
        rule_count = 0
        if rules_file.exists():
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                rule_count = len(rules)

        return {
            "total_verified": total_verified,
            "avg_accuracy": avg_accuracy,
            "high_confidence_count": high_conf_count,
            "high_confidence_ratio": high_conf_count / total_count if total_count > 0 else 0,
            "generated_rules": rule_count
        }

    def close(self):
        """关闭数据库连接"""
        self.conn.close()


# ============================================================
# 命令行接口
# ============================================================

def main():
    """命令行接口"""
    parser = argparse.ArgumentParser(
        description="预测系统集成器 - 整合事件分析到预测系统"
    )
    parser.add_argument(
        "action",
        choices=["learn", "update", "progress", "test"],
        help="操作类型"
    )
    parser.add_argument("--prediction-id", type=int, help="预测ID")
    parser.add_argument("--news-id", type=str, help="新闻ID")
    parser.add_argument("--days", type=int, default=10, help="验证天数")

    args = parser.parse_args()

    integrator = PredictionIntegrator()

    try:
        if args.action == "learn":
            # 验证并学习
            integrator.verify_and_learn(days=args.days)

        elif args.action == "update":
            # 更新预测置信度
            if not all([args.prediction_id, args.news_id]):
                print("❌ 错误: 需要提供 --prediction-id 和 --news-id 参数")
                return 1

            success = integrator.update_prediction_confidence(
                args.prediction_id,
                args.news_id
            )

            if success:
                print("✅ 预测置信度更新成功")
            else:
                print("❌ 更新失败（可能是功能未启用或影响分数不足）")

        elif args.action == "progress":
            # 查看学习进度
            progress = integrator.get_learning_progress()

            print("\n" + "="*60)
            print("📊 事件分析学习进度")
            print("="*60)
            print(f"已验证事件: {progress['total_verified']}")
            print(f"平均准确率: {progress['avg_accuracy']:.1f}%")
            print(f"高置信度: {progress['high_confidence_count']} "
                  f"({progress['high_confidence_ratio']:.1%})")
            print(f"生成规则: {progress['generated_rules']}")
            print("="*60)

        elif args.action == "test":
            # 测试功能
            print("\n" + "="*60)
            print("🧪 预测系统集成器测试")
            print("="*60)

            print("\n1. 测试学习进度查询...")
            progress = integrator.get_learning_progress()
            print(f"   ✅ 已验证: {progress['total_verified']}个")
            print(f"   ✅ 准确率: {progress['avg_accuracy']:.1f}%")

            print("\n2. 测试验证功能...")
            # 创建测试数据
            cursor = integrator.conn.cursor()

            # 插入测试新闻
            test_news_id = f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            cursor.execute("""
                INSERT OR IGNORE INTO news_labels (
                    news_id, title, content, sentiment, sentiment_confidence,
                    event_types, impact_score, news_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_news_id,
                "测试新闻",
                "测试内容",
                "positive",
                0.8,
                json.dumps(["业绩财报"]),
                80.0,
                datetime.now().strftime("%Y-%m-%d")
            ))

            # 插入测试关联
            cursor.execute("""
                INSERT OR IGNORE INTO event_kline_associations (
                    news_id, stock_code, association_type, association_strength,
                    kline_start_date, pre_event_close,
                    post_event_high, post_event_low,
                    day1_change, day3_change, day5_change
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_news_id,
                "600000",
                "positive",
                0.8,
                datetime.now().strftime("%Y-%m-%d"),
                10.0,
                11.0,
                9.5,
                8.0,  # day1_change = (11-10)/10*100 = 10%
                15.0,  # day3_change = 15%
                12.0   # day5_change = 12%
            ))

            integrator.conn.commit()

            print(f"   创建测试数据: {test_news_id}")

            # 验证测试事件
            result = integrator._verify_event_prediction(test_news_id, "600000")

            if result:
                print(f"   ✅ 验证成功")
                print(f"   预测方向: {result['predicted_direction']}")
                print(f"   实际方向: {result['actual_direction']}")
                print(f"   准确率: {result['prediction_accuracy']:.0%}")
                print(f"   教训: {result['lesson_learned']}")

            print("\n" + "="*60)
            print("✅ 测试完成")
            print("="*60)

        return 0

    finally:
        integrator.close()


if __name__ == "__main__":
    sys.exit(main())
