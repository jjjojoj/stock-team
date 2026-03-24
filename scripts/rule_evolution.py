#!/usr/bin/env python3
"""
规则进化系统

功能：
1. 分析规则表现（成功率 + 样本数）
2. 自动调整规则权重
3. 淘汰低质量规则
4. 从案例中发现新规则
5. 记录规则进化历史

核心理念：规则库是活的，持续进化
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
LEARNING_DIR = PROJECT_ROOT / "learning"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"

sys.path.insert(0, str(PROJECT_ROOT))

from core.storage import load_rules, save_rules


class RuleEvolution:
    """规则进化系统"""
    
    def __init__(self):
        self.rules_file = LEARNING_DIR / "prediction_rules.json"
        self.history_file = LEARNING_DIR / "rule_evolution_history.json"
        self.stats_file = LEARNING_DIR / "rule_stats.json"
        
        self._ensure_dirs()
        self._load_data()
    
    def _ensure_dirs(self):
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_data(self):
        """加载规则和历史"""
        self.rules = load_rules({})
        
        if self.history_file.exists():
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self.history = json.load(f)
        else:
            self.history = {"evolutions": []}
    
    def _save_data(self):
        """保存规则和历史"""
        save_rules(self.rules)
        
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    def analyze_rule_performance(self) -> Dict:
        """
        分析所有规则的表现
        
        返回：
        {
            "excellent": [...],  # 成功率>70%, 样本>10
            "good": [...],       # 成功率>50%, 样本>10
            "poor": [...],       # 成功率<40%, 样本>10
            "new": [...]         # 样本<10
        }
        """
        stats = {
            "excellent": [],
            "good": [],
            "poor": [],
            "new": [],
            "total": 0
        }
        
        for category_name, category in self.rules.items():
            for rule_name, rule in category.items():
                stats["total"] += 1
                
                success_rate = rule.get('success_rate', 0)
                samples = rule.get('samples', 0)
                
                rule_info = {
                    "category": category_name,
                    "rule": rule_name,
                    "success_rate": success_rate,
                    "samples": samples,
                    "weight": rule.get('weight', 0),
                    "condition": rule.get('condition', ''),
                }
                
                if samples < 10:
                    stats["new"].append(rule_info)
                elif success_rate >= 0.7:
                    stats["excellent"].append(rule_info)
                elif success_rate >= 0.5:
                    stats["good"].append(rule_info)
                else:
                    stats["poor"].append(rule_info)
        
        return stats
    
    def adjust_rule_weights(self):
        """
        根据表现调整规则权重
        
        规则：
        - 优秀规则（成功率>70%）：权重 +10%
        - 良好规则（成功率>50%）：权重不变
        - 差规则（成功率<40%）：权重 -20%
        - 极差规则（成功率<30% 且样本>20）：标记为待移除
        """
        adjustments = []
        
        for category_name, category in self.rules.items():
            for rule_name, rule in category.items():
                success_rate = rule.get('success_rate', 0)
                samples = rule.get('samples', 0)
                old_weight = rule.get('weight', 0)
                
                adjustment = None
                
                # 优秀规则：加分
                if success_rate >= 0.7 and samples >= 10:
                    new_weight = min(1.0, old_weight * 1.1)
                    adjustment = {
                        "rule": f"{category_name}.{rule_name}",
                        "action": "increase",
                        "old_weight": old_weight,
                        "new_weight": new_weight,
                        "reason": f"成功率 {success_rate*100:.1f}% 优秀"
                    }
                    rule['weight'] = new_weight
                
                # 差规则：减分
                elif success_rate < 0.4 and samples >= 10:
                    new_weight = max(0.05, old_weight * 0.8)
                    adjustment = {
                        "rule": f"{category_name}.{rule_name}",
                        "action": "decrease",
                        "old_weight": old_weight,
                        "new_weight": new_weight,
                        "reason": f"成功率 {success_rate*100:.1f}% 过低"
                    }
                    rule['weight'] = new_weight
                
                # 极差规则：标记待移除
                elif success_rate < 0.3 and samples >= 20:
                    rule['marked_for_removal'] = True
                    rule['removal_reason'] = f"成功率仅{success_rate*100:.1f}%，样本{samples}个"
                    adjustment = {
                        "rule": f"{category_name}.{rule_name}",
                        "action": "mark_for_removal",
                        "old_weight": old_weight,
                        "reason": f"成功率{success_rate*100:.1f}% 极低，样本{samples}个"
                    }
                
                if adjustment:
                    adjustments.append(adjustment)
        
        return adjustments
    
    def remove_poor_rules(self) -> List:
        """移除标记的规则"""
        removed = []
        
        for category_name, category in list(self.rules.items()):
            for rule_name, rule in list(category.items()):
                if rule.get('marked_for_removal'):
                    removed.append({
                        "category": category_name,
                        "rule": rule_name,
                        "success_rate": rule.get('success_rate', 0),
                        "samples": rule.get('samples', 0),
                        "reason": rule.get('removal_reason', '')
                    })
                    del category[rule_name]
        
        return removed
    
    def extract_new_rules_from_cases(self, case_studies: List[Dict]) -> List:
        """
        从成功案例中提取新规则
        
        案例格式：
        {
            "stock": "北方稀土",
            "success_factors": ["行业周期低位", "央企背景", "稀土涨价"],
            "outcome": "correct",
            "profit_pct": 5.2
        }
        """
        new_rules = []
        
        # 统计成功因素频率
        factor_counts = {}
        for case in case_studies:
            if case.get('outcome') == 'correct' and case.get('profit_pct', 0) > 3:
                for factor in case.get('success_factors', []):
                    factor_counts[factor] = factor_counts.get(factor, 0) + 1
        
        # 频繁出现的因素 → 新规则
        for factor, count in factor_counts.items():
            if count >= 3:  # 出现 3 次以上
                # 检查是否已存在类似规则
                exists = False
                for category in self.rules.values():
                    for rule_name, rule in category.items():
                        if factor in rule.get('condition', ''):
                            exists = True
                            break
                
                if not exists:
                    # 创建新规则
                    new_rule = {
                        "condition": factor,
                        "prediction": "上涨",
                        "weight": 0.15,  # 初始权重
                        "success_rate": 0.5,  # 初始估计
                        "samples": count,
                        "created_at": datetime.now().isoformat(),
                        "source": "case_study"
                    }
                    
                    # 添加到合适类别
                    if "周期" in factor:
                        category = "event_rules"
                    elif "央企" in factor or "国资" in factor:
                        category = "fundamental_rules"
                    elif "涨价" in factor:
                        category = "sentiment_rules"
                    else:
                        category = "event_rules"
                    
                    self.rules[category][f"extracted_{factor}_{datetime.now().strftime('%Y%m%d')}"] = new_rule
                    
                    new_rules.append({
                        "category": category,
                        "rule": f"extracted_{factor}",
                        "condition": factor,
                        "count": count
                    })
        
        return new_rules
    
    def run_evolution(self, case_studies: List[Dict] = None) -> Dict:
        """
        运行完整的规则进化流程
        
        1. 分析表现
        2. 调整权重
        3. 移除差规则
        4. 提取新规则
        5. 记录历史
        """
        print("=" * 60)
        print(f"🧬 规则进化 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        # 1. 分析表现
        print("\n1️⃣ 分析规则表现...")
        stats = self.analyze_rule_performance()
        print(f"   总规则数：{stats['total']}")
        print(f"   优秀：{len(stats['excellent'])} 条")
        print(f"   良好：{len(stats['good'])} 条")
        print(f"   差：{len(stats['poor'])} 条")
        print(f"   新规则：{len(stats['new'])} 条")
        
        # 2. 调整权重
        print("\n2️⃣ 调整规则权重...")
        adjustments = self.adjust_rule_weights()
        if adjustments:
            for adj in adjustments:
                if adj['action'] == 'increase':
                    print(f"   ⬆️ {adj['rule']}: {adj['old_weight']:.2f} → {adj['new_weight']:.2f}")
                elif adj['action'] == 'decrease':
                    print(f"   ⬇️ {adj['rule']}: {adj['old_weight']:.2f} → {adj['new_weight']:.2f}")
                elif adj['action'] == 'mark_for_removal':
                    print(f"   🗑️ {adj['rule']}: 标记移除 ({adj['reason']})")
        else:
            print("   无需调整")
        
        # 3. 移除差规则
        print("\n3️⃣ 移除差规则...")
        removed = self.remove_poor_rules()
        if removed:
            for r in removed:
                print(f"   ❌ 移除 {r['category']}.{r['rule']}: 成功率{r['success_rate']*100:.1f}%")
        else:
            print("   无需移除")
        
        # 4. 提取新规则
        if case_studies:
            print("\n4️⃣ 从案例中提取新规则...")
            new_rules = self.extract_new_rules_from_cases(case_studies)
            if new_rules:
                for nr in new_rules:
                    print(f"   ✅ 新规则：{nr['category']}.{nr['rule']} ({nr['condition']})")
            else:
                print("   无新规则")
        
        # 5. 保存
        self._save_data()
        
        # 6. 记录历史
        evolution_record = {
            "date": datetime.now().isoformat(),
            "stats": {
                "total": stats['total'],
                "excellent": len(stats['excellent']),
                "poor": len(stats['poor']),
            },
            "adjustments": adjustments,
            "removed": removed,
        }
        self.history["evolutions"].append(evolution_record)
        
        # 保留最近 100 次记录
        if len(self.history["evolutions"]) > 100:
            self.history["evolutions"] = self.history["evolutions"][-100:]
        
        self._save_data()
        
        print("\n✅ 规则进化完成")
        print(f"   规则总数：{stats['total'] - len(removed)}")
        print(f"   历史进化记录：{len(self.history['evolutions'])}次")
        
        return {
            "stats": stats,
            "adjustments": adjustments,
            "removed": removed,
        }


def main():
    """主函数"""
    evolution = RuleEvolution()
    evolution.run_evolution(case_studies=[])


if __name__ == "__main__":
    main()
