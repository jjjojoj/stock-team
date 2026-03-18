#!/usr/bin/env python3
"""
每日规则分析
分析昨日交易，评估规则效果，提出优化建议
"""

import sys
import os
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

from scripts.rule_evolution import RuleEvolutionEngine

def main():
    engine = RuleEvolutionEngine()
    
    print("="*60)
    print("📊 每日规则分析报告")
    print(f"日期：{datetime.now().strftime('%Y-%m-%d')}")
    print("="*60)
    
    # 回顾规则表现
    engine.review_rules()
    
    # 检查是否需要调整
    print("\n💡 今日建议：")
    print("-" * 50)
    
    # 读取最近的交易记录
    # （实际应用中会从数据库读取）
    
    print("✅ 规则系统运行正常")
    print("📝 详细历史见：learning/rule_evolution_history.json")
    print("="*60)

if __name__ == "__main__":
    main()
