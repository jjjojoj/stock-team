#!/usr/bin/env python3
"""
自动规则生成器
基于事件模式识别结果自动生成交易规则
"""

import sqlite3
import json
import sys
from pathlib import Path
from typing import Dict, List
import logging
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "stock_team.db"
LEARNING_DIR = PROJECT_ROOT / "learning"

sys.path.insert(0, str(PROJECT_ROOT))

from core.storage import load_validation_pool, save_validation_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoRuleGenerator:
    """自动规则生成器"""
    
    def __init__(self):
        self.validation_threshold = 0.7
        self.min_samples = 5
        
    def generate_rules_from_events(self) -> List[Dict]:
        """从事件数据生成规则"""
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取高成功率的事件-收益关联
        cursor.execute("""
            SELECT nl.sentiment, nl.event_types, 
                   AVG(eih.actual_impact) as avg_impact,
                   AVG(eih.prediction_accuracy) as avg_accuracy,
                   COUNT(*) as sample_count
            FROM news_labels nl
            JOIN event_impact_history eih ON nl.news_id = eih.news_id
            WHERE eih.verified_at >= date('now', '-60 days')
              AND eih.prediction_accuracy IS NOT NULL
            GROUP BY nl.sentiment, nl.event_types
            HAVING COUNT(*) >= ? AND AVG(eih.prediction_accuracy) >= ?
        """, (self.min_samples, self.validation_threshold))
        
        rules = []
        for row in cursor.fetchall():
            sentiment = row['sentiment']
            event_types = row['event_types']
            avg_impact = row['avg_impact']
            avg_accuracy = row['avg_accuracy']
            sample_count = row['sample_count']
            
            # 解析事件类型
            try:
                event_types_list = json.loads(event_types) if event_types else []
            except (json.JSONDecodeError, TypeError):
                event_types_list = [event_types] if event_types else []
                
            for event_type in event_types_list:
                if not event_type:
                    continue
                    
                # 生成规则条件
                condition = f"sentiment='{sentiment}' AND event_type='{event_type}'"
                
                # 确定操作方向
                if avg_impact > 0:
                    action = 'buy'
                    confidence_boost = min(avg_impact * 2, 20)  # 最多+20%置信度
                else:
                    action = 'sell'
                    confidence_boost = min(abs(avg_impact) * 2, 20)
                    
                rule = {
                    'id': f"event_auto_{sentiment}_{event_type}_{datetime.now().strftime('%Y%m%d')}",
                    'condition': condition,
                    'prediction': f"{action} on {event_type} {sentiment} event",
                    'confidence_boost': confidence_boost,
                    'samples': sample_count,
                    'success_rate': avg_accuracy,
                    'source': 'auto_generated_event_rule',
                    'created_at': datetime.now().isoformat(),
                    'status': 'validating'  # 先放入验证池
                }
                rules.append(rule)
                
        conn.close()
        return rules
    
    def save_rules_to_validation_pool(self, rules: List[Dict]):
        """将规则保存到验证池"""
        validation_pool = load_validation_pool({})

        for rule in rules:
            rule_id = rule["id"]
            validation_pool[rule_id] = {
                "rule_id": rule_id,
                "source": rule.get("source", "auto_generated_event_rule"),
                "source_book": "event_analysis",
                "rule": rule.get("condition", rule_id),
                "testable_form": rule.get("prediction", ""),
                "category": "事件驱动",
                "backtest": {
                    "samples": rule.get("samples", 0),
                    "success_rate": rule.get("success_rate", 0.0),
                    "avg_profit": 0.0,
                    "avg_loss": 0.0,
                    "profit_factor": 0.0,
                },
                "live_test": {
                    "samples": 0,
                    "success_rate": 0.0,
                    "started_at": datetime.now().isoformat(),
                },
                "status": "validating",
                "confidence": min(0.95, max(0.5, float(rule.get("success_rate", 0.0) or 0.0))),
                "created_at": rule.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "metadata": rule,
            }

        save_validation_pool(validation_pool)
            
        logger.info(f"Added {len(rules)} new event-based rules to validation pool")
        
    def integrate_with_learning_system(self):
        """集成到学习系统"""
        rules = self.generate_rules_from_events()
        if rules:
            self.save_rules_to_validation_pool(rules)
            logger.info(f"Successfully generated {len(rules)} event-driven trading rules")
        else:
            logger.info("No new event-driven rules generated")


def main():
    """主函数"""
    generator = AutoRuleGenerator()
    generator.integrate_with_learning_system()


if __name__ == "__main__":
    main()
