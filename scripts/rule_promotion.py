#!/usr/bin/env python3
"""
规则晋升/废弃系统
- 检查验证池规则是否达到晋升标准
- 晋升合格规则到规则库
- 废弃不合格规则
"""

import sys
import os
import json
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

VALIDATION_POOL_FILE = os.path.join(PROJECT_ROOT, "learning", "rule_validation_pool.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
REJECTED_FILE = os.path.join(PROJECT_ROOT, "learning", "rejected_rules.json")


class RulePromotion:
    """规则晋升系统"""
    
    # 晋升标准
    PROMOTION_MIN_SAMPLES = 10      # 最少样本数
    PROMOTION_MIN_RATE = 0.60       # 最低胜率 60%
    
    # 废弃标准
    REJECT_MIN_SAMPLES = 5          # 最少样本数
    REJECT_MAX_RATE = 0.35          # 最高胜率 35%
    
    def __init__(self):
        self.validation_pool = self._load_json(VALIDATION_POOL_FILE, {})
        self.rules = self._load_json(RULES_FILE, {})
        self.rejected = self._load_json(REJECTED_FILE, {})
        
    def _load_json(self, path: str, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def _save_json(self, path: str, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def check_and_promote(self) -> Dict:
        """检查并晋升/废弃规则"""
        print("=" * 60)
        print("🔄 规则晋升/废弃检查")
        print("=" * 60)
        print()
        
        results = {
            "promoted": [],
            "rejected": [],
            "pending": [],
            "culled": []  # 新增：规则库淘汰
        }
        
        # 先检查规则库淘汰
        culled = self._cull_low_perf_rules()
        results["culled"] = culled
        
        rules_to_remove = []
        
        for rule_id, rule in self.validation_pool.items():
            if rule["status"] != "validating":
                continue
            
            samples = rule["live_test"]["samples"]
            success_rate = rule["live_test"]["success_rate"]
            
            # 检查晋升
            if samples >= self.PROMOTION_MIN_SAMPLES and success_rate >= self.PROMOTION_MIN_RATE:
                print(f"  ✅ 晋升: {rule_id}")
                print(f"     规则: {rule['rule']}")
                print(f"     来源: {rule.get('source_book', '未知')}")
                print(f"     胜率: {success_rate:.1%} ({samples} 样本)")
                
                # 添加到规则库
                self._add_to_rules(rule_id, rule)
                rules_to_remove.append(rule_id)
                results["promoted"].append({
                    "id": rule_id,
                    "rule": rule["rule"],
                    "success_rate": success_rate,
                    "samples": samples
                })
                print()
            
            # 检查废弃
            elif samples >= self.REJECT_MIN_SAMPLES and success_rate < self.REJECT_MAX_RATE:
                print(f"  ❌ 废弃: {rule_id}")
                print(f"     规则: {rule['rule']}")
                print(f"     胜率: {success_rate:.1%} ({samples} 样本)")
                
                # 添加到废弃列表
                rule["status"] = "rejected"
                rule["rejected_at"] = datetime.now().isoformat()
                rule["reject_reason"] = f"胜率 {success_rate:.1%} 低于阈值 {self.REJECT_MAX_RATE:.0%}"
                self.rejected[rule_id] = rule
                rules_to_remove.append(rule_id)
                results["rejected"].append({
                    "id": rule_id,
                    "rule": rule["rule"],
                    "success_rate": success_rate,
                    "samples": samples
                })
                print()
            
            # 继续验证
            else:
                results["pending"].append({
                    "id": rule_id,
                    "samples": samples,
                    "success_rate": success_rate,
                    "need_samples": max(0, self.PROMOTION_MIN_SAMPLES - samples)
                })
        
        # 从验证池移除已处理规则
        for rule_id in rules_to_remove:
            del self.validation_pool[rule_id]
        
        # 保存
        self._save_json(VALIDATION_POOL_FILE, self.validation_pool)
        self._save_json(RULES_FILE, self.rules)
        self._save_json(REJECTED_FILE, self.rejected)
        
        # 打印总结
        print("=" * 60)
        print("📊 检查完成")
        print(f"  晋升: {len(results['promoted'])} 条")
        print(f"  废弃: {len(results['rejected'])} 条")
        print(f"  待验证: {len(results['pending'])} 条")
        
        if results["pending"]:
            print("\n📋 待验证规则状态:")
            for p in results["pending"][:5]:  # 只显示前5条
                print(f"  - {p['id']}: {p['success_rate']:.1%} (还需 {p['need_samples']} 样本)")
        
        print("=" * 60)
        
        return results
    
    def _cull_low_perf_rules(self) -> List[Dict]:
        """淘汰规则库中的低效规则"""
        print("🗑️ 检查规则库淘汰...")
        print()
        
        culled = []
        
        # 淘汰标准：样本>=15 且 胜率<30%
        MIN_SAMPLES = 15
        MAX_RATE = 0.30
        
        for category in ["tech_rules", "fundamental_rules", "event_rules", "sentiment_rules"]:
            if category not in self.rules:
                continue
            
            rules_to_remove = []
            
            for rule_id, rule in self.rules[category].items():
                samples = rule.get("samples", 0)
                success_rate = rule.get("success_rate", 0)
                
                # 跳过新规则（样本不足）
                if samples < MIN_SAMPLES:
                    continue
                
                # 检查是否需要淘汰
                if success_rate < MAX_RATE:
                    print(f"  ❌ 淘汰: {rule_id}")
                    print(f"     条件: {rule.get('condition', '-')}")
                    print(f"     胜率: {success_rate:.1%} ({samples} 样本)")
                    print(f"     原因: 样本充足但胜率过低")
                    print()
                    
                    # 移动到废弃列表
                    self.rejected[rule_id] = {
                        **rule,
                        "rejected_at": datetime.now().isoformat(),
                        "reject_reason": f"胜率过低({success_rate:.1%})，已从规则库淘汰"
                    }
                    
                    rules_to_remove.append(rule_id)
                    culled.append({
                        "id": rule_id,
                        "category": category,
                        "success_rate": success_rate,
                        "samples": samples
                    })
            
            # 从规则库删除
            for rule_id in rules_to_remove:
                del self.rules[category][rule_id]
        
        if culled:
            print(f"  共淘汰 {len(culled)} 条低效规则")
            print()
        else:
            print("  无需淘汰（所有规则表现正常或样本不足）")
            print()
        
        return culled
    
    def _add_to_rules(self, rule_id: str, rule: Dict):
        """将规则添加到规则库"""
        # 根据规则类别决定放入哪个分类
        category = rule.get("category", "general")
        
        # 映射到规则库分类
        category_map = {
            "趋势": "tech_rules",
            "技术形态": "tech_rules",
            "估值": "fundamental_rules",
            "选股": "fundamental_rules",
            "仓位管理": "fundamental_rules",
            "心态": "sentiment_rules",
            "general": "sentiment_rules"
        }
        
        target_category = category_map.get(category, "sentiment_rules")
        
        if target_category not in self.rules:
            self.rules[target_category] = {}
        
        # 添加规则
        self.rules[target_category][rule_id] = {
            "condition": rule["testable_form"],
            "prediction": self._infer_prediction(rule["rule"]),
            "weight": 0.15,  # 新规则初始权重
            "success_rate": rule["live_test"]["success_rate"],
            "samples": rule["live_test"]["samples"],
            "source": rule.get("source_book", "验证池晋升"),
            "promoted_at": datetime.now().isoformat()
        }
    
    def _infer_prediction(self, rule_text: str) -> str:
        """从规则文本推断预测方向"""
        if any(w in rule_text for w in ["上涨", "突破", "反弹", "加仓"]):
            return "上涨"
        elif any(w in rule_text for w in ["下跌", "止损", "减仓"]):
            return "下跌"
        else:
            return "中性"


def main():
    promoter = RulePromotion()
    promoter.check_and_promote()


if __name__ == "__main__":
    main()
