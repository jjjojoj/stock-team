#!/usr/bin/env python3
"""
事件模式识别器
从历史事件数据中识别高概率盈利的事件模式
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import logging

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "stock_team.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventPatternRecognizer:
    """事件模式识别器"""
    
    def __init__(self):
        self.patterns = {}
        self.min_samples = 5
        
    def analyze_event_patterns(self) -> Dict[str, Dict]:
        """分析事件模式"""
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取所有事件及其后续表现
        cursor.execute("""
            SELECT eka.*, nl.sentiment, nl.event_types, 
                   eih.actual_impact, eih.prediction_accuracy,
                   eih.day1_change, eih.day5_change, eih.day10_change
            FROM event_kline_associations eka
            JOIN news_labels nl ON eka.news_id = nl.news_id
            LEFT JOIN event_impact_history eih ON eka.news_id = eih.news_id
            WHERE eka.kline_start_date >= date('now', '-90 days')
        """)
        
        events = []
        for row in cursor.fetchall():
            event_dict = dict(row)
            if event_dict.get('event_types'):
                try:
                    event_dict['event_types'] = json.loads(event_dict['event_types'])
                except (json.JSONDecodeError, TypeError):
                    event_dict['event_types'] = []
            events.append(event_dict)
            
        conn.close()
        
        # 按事件类型和情绪分组
        pattern_groups = defaultdict(list)
        for event in events:
            if not event['event_types']:
                continue
                
            for event_type in event['event_types']:
                key = f"{event_type}_{event['sentiment']}"
                pattern_groups[key].append(event)
                
        # 计算每个模式的统计指标
        patterns = {}
        for pattern_key, pattern_events in pattern_groups.items():
            if len(pattern_events) < self.min_samples:
                continue
                
            # 计算平均收益
            day1_returns = [e['day1_change'] for e in pattern_events if e['day1_change'] is not None]
            day5_returns = [e['day5_change'] for e in pattern_events if e['day5_change'] is not None]
            day10_returns = [e['day10_change'] for e in pattern_events if e['day10_change'] is not None]
            
            # 计算成功率
            success_count = sum(1 for e in pattern_events 
                              if e['prediction_accuracy'] and e['prediction_accuracy'] > 0.6)
            success_rate = success_count / len(pattern_events) if pattern_events else 0
            
            patterns[pattern_key] = {
                'pattern': pattern_key,
                'event_type': pattern_key.split('_')[0],
                'sentiment': pattern_key.split('_')[1],
                'sample_size': len(pattern_events),
                'avg_day1_return': sum(day1_returns) / len(day1_returns) if day1_returns else 0,
                'avg_day5_return': sum(day5_returns) / len(day5_returns) if day5_returns else 0,
                'avg_day10_return': sum(day10_returns) / len(day10_returns) if day10_returns else 0,
                'success_rate': success_rate,
                'confidence_score': min(success_rate * len(pattern_events) / 10, 1.0)
            }
            
        return patterns
    
    def generate_trading_rules(self, patterns: Dict[str, Dict]) -> List[Dict]:
        """从模式生成交易规则"""
        rules = []
        
        for pattern_key, pattern in patterns.items():
            if pattern['confidence_score'] < 0.7:
                continue
                
            # 生成买入规则（正面事件）
            if pattern['sentiment'] == 'positive' and pattern['avg_day5_return'] > 2.0:
                rule = {
                    'condition': f"sentiment='positive' AND event_type='{pattern['event_type']}'",
                    'action': 'buy',
                    'target_return': pattern['avg_day5_return'],
                    'confidence': pattern['confidence_score'],
                    'source': 'event_pattern_recognition',
                    'created_at': 'auto'
                }
                rules.append(rule)
                
            # 生成卖出规则（负面事件）
            elif pattern['sentiment'] == 'negative' and pattern['avg_day5_return'] < -2.0:
                rule = {
                    'condition': f"sentiment='negative' AND event_type='{pattern['event_type']}'",
                    'action': 'sell',
                    'target_return': pattern['avg_day5_return'],
                    'confidence': pattern['confidence_score'],
                    'source': 'event_pattern_recognition',
                    'created_at': 'auto'
                }
                rules.append(rule)
                
        return rules


def main():
    """主函数"""
    recognizer = EventPatternRecognizer()
    patterns = recognizer.analyze_event_patterns()
    
    print("=== 事件模式分析结果 ===")
    for pattern_key, pattern in patterns.items():
        print(f"\n模式: {pattern['event_type']}_{pattern['sentiment']}")
        print(f"  样本数: {pattern['sample_size']}")
        print(f"  5日平均收益: {pattern['avg_day5_return']:.2f}%")
        print(f"  成功率: {pattern['success_rate']:.2%}")
        print(f"  置信度: {pattern['confidence_score']:.2f}")
        
    rules = recognizer.generate_trading_rules(patterns)
    print(f"\n=== 生成的交易规则 ({len(rules)} 条) ===")
    for rule in rules:
        print(f"\n条件: {rule['condition']}")
        print(f"动作: {rule['action']}")
        print(f"目标收益: {rule['target_return']:.2f}%")
        print(f"置信度: {rule['confidence']:.2f}")


if __name__ == "__main__":
    main()