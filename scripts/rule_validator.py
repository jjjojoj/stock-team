#!/usr/bin/env python3
"""
规则验证器（增强版）

功能：
1. 验证 prediction_rules.json 中的规则
2. 更新规则的成功率和样本数
3. 动态调整规则权重
4. 淘汰低效规则

验证来源：
- predictions.json 中的历史预测
- trade_history.json 中的交易记录
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.predictions import normalize_prediction_collection, prediction_result_status
from core.storage import load_json

DATA_DIR = PROJECT_ROOT / "data"
LEARNING_DIR = PROJECT_ROOT / "learning"
CONFIG_DIR = PROJECT_ROOT / "config"


class RuleValidator:
    """规则验证器"""
    
    # 权重调整参数
    MIN_WEIGHT = 0.05
    MAX_WEIGHT = 0.35
    SUCCESS_BONUS = 0.02  # 成功时权重增加
    FAILURE_PENALTY = 0.03  # 失败时权重减少
    
    # 淘汰标准
    REJECTION_SAMPLES = 10  # 至少10次样本
    REJECTION_RATE = 0.35  # 成功率低于35%淘汰
    
    def __init__(self):
        self.rules_file = LEARNING_DIR / "prediction_rules.json"
        self.predictions_file = DATA_DIR / "predictions.json"
        self.trades_file = DATA_DIR / "trade_history.json"
        self.rejected_file = LEARNING_DIR / "rejected_rules.json"
        self.config_file = CONFIG_DIR / "prediction_config.json"
        
        self._load_data()
    
    def _load_data(self):
        """加载数据"""
        # 规则库
        self.rules = load_json(self.rules_file, {})
        
        # 预测历史
        self.predictions = normalize_prediction_collection(
            load_json(self.predictions_file, {"active": {}, "history": []})
        )
        
        # 交易历史
        self.trades = load_json(self.trades_file, [])
        
        # 淘汰库
        self.rejected = load_json(self.rejected_file, {})
        
        # 预测配置
        self.config = load_json(self.config_file, {})
    
    def _save_data(self):
        """保存数据"""
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)
        
        with open(self.rejected_file, 'w', encoding='utf-8') as f:
            json.dump(self.rejected, f, ensure_ascii=False, indent=2)
    
    def validate_all_rules(self) -> Dict:
        """验证所有规则"""
        print("=" * 60)
        print(f"🧪 规则验证器 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        stats = {
            "total_rules": 0,
            "updated": 0,
            "promoted": 0,
            "rejected": 0,
            "weight_adjusted": 0
        }
        
        # 遍历所有规则类别
        for category_name, category_rules in self.rules.items():
            print(f"\n📊 验证 {category_name}...")
            
            for rule_name, rule in category_rules.items():
                stats["total_rules"] += 1
                
                # 获取该规则的验证结果
                results = self._get_rule_validation_results(rule_name, rule)
                
                if not results:
                    continue
                
                # 更新规则统计数据
                old_samples = rule.get("samples", 0)
                old_rate = rule.get("success_rate", 0.0)
                
                rule["samples"] = results["total"]
                rule["success_rate"] = results["success_rate"]
                
                # 动态调整权重
                if results["total"] >= 5:
                    new_weight = self._calculate_weight(rule, results)
                    if abs(new_weight - rule.get("weight", 0.15)) > 0.01:
                        rule["weight"] = new_weight
                        stats["weight_adjusted"] += 1
                        print(f"   ⚖️ {rule_name}: 权重 {rule.get('weight', 0.15):.2f} → {new_weight:.2f}")
                
                stats["updated"] += 1
                
                # 检查是否淘汰
                if self._should_reject(rule):
                    self._reject_rule(category_name, rule_name, rule)
                    stats["rejected"] += 1
                    print(f"   ❌ 淘汰: {rule_name} (成功率 {rule['success_rate']*100:.1f}%)")
                
                # 打印更新
                if old_samples != rule["samples"]:
                    change = rule["success_rate"] - old_rate
                    change_str = f"+{change*100:.1f}%" if change > 0 else f"{change*100:.1f}%"
                    print(f"   📈 {rule_name}: {old_samples} → {rule['samples']} 样本, "
                          f"成功率 {rule['success_rate']*100:.1f}% ({change_str})")
        
        # 保存
        self._save_data()
        
        # 打印统计
        print("\n" + "=" * 60)
        print("📊 验证统计:")
        print(f"   总规则数: {stats['total_rules']}")
        print(f"   已更新: {stats['updated']}")
        print(f"   权重调整: {stats['weight_adjusted']}")
        print(f"   已淘汰: {stats['rejected']}")
        print("=" * 60)
        
        return stats
    
    def _get_rule_validation_results(self, rule_name: str, rule: dict) -> Dict:
        """获取规则的验证结果"""
        results = {
            "total": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "success_rate": 0.0
        }
        
        # 1. 从预测历史中查找匹配的预测
        for pred in self.predictions.get("history", []):
            rules_used = pred.get("rules_used") or pred.get("matched_rules", [])
            result_status = prediction_result_status(pred)

            if rule_name in rules_used and result_status != "pending":
                results["total"] += 1
                if result_status == "correct":
                    results["correct"] += 1
                elif result_status == "partial":
                    results["partial"] += 1
                else:
                    results["wrong"] += 1
        
        # 2. 从活跃预测中查找（已验证的）
        for pred_id, pred in self.predictions.get("active", {}).items():
            rules_used = pred.get("rules_used") or pred.get("matched_rules", [])
            result_status = prediction_result_status(pred)

            if result_status != "pending" and rule_name in rules_used:
                results["total"] += 1
                if result_status == "correct":
                    results["correct"] += 1
                elif result_status == "partial":
                    results["partial"] += 1
                else:
                    results["wrong"] += 1
        
        # 计算成功率
        if results["total"] > 0:
            results["success_rate"] = (results["correct"] + 0.5 * results["partial"]) / results["total"]
        
        return results
    
    def _calculate_weight(self, rule: dict, results: dict) -> float:
        """计算新的权重"""
        current_weight = rule.get("weight", 0.15)
        success_rate = results["success_rate"]
        samples = results["total"]
        
        # 基于成功率和样本数调整权重
        if success_rate >= 0.6:
            # 高成功率：增加权重
            adjustment = self.SUCCESS_BONUS * min(samples / 10, 1.0)
            new_weight = current_weight + adjustment
        elif success_rate < 0.4:
            # 低成功率：减少权重
            adjustment = self.FAILURE_PENALTY * min(samples / 10, 1.0)
            new_weight = current_weight - adjustment
        else:
            # 中等成功率：保持不变
            new_weight = current_weight
        
        # 限制范围
        return max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, new_weight))
    
    def _should_reject(self, rule: dict) -> bool:
        """检查是否应该淘汰"""
        if rule["samples"] < self.REJECTION_SAMPLES:
            return False
        
        if rule["success_rate"] < self.REJECTION_RATE:
            return True
        
        return False
    
    def _reject_rule(self, category: str, rule_name: str, rule: dict):
        """淘汰规则"""
        # 移动到淘汰库
        self.rejected[f"{category}.{rule_name}"] = {
            **rule,
            "rejected_at": datetime.now().isoformat(),
            "reason": f"成功率过低 ({rule['success_rate']*100:.1f}%)"
        }
        
        # 从规则库移除
        del self.rules[category][rule_name]
    
    def get_rule_report(self) -> str:
        """生成规则报告"""
        lines = [
            "📊 **规则验证报告**",
            f"\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ""
        ]
        
        # 按类别统计
        for category_name, category_rules in self.rules.items():
            lines.append(f"\n### {category_name}")
            
            sorted_rules = sorted(
                category_rules.items(),
                key=lambda x: x[1].get("success_rate", 0),
                reverse=True
            )
            
            for rule_name, rule in sorted_rules:
                if rule.get("samples", 0) > 0:
                    emoji = "✅" if rule["success_rate"] >= 0.6 else ("⚠️" if rule["success_rate"] >= 0.4 else "❌")
                    lines.append(
                        f"{emoji} {rule_name}: {rule['success_rate']*100:.1f}% "
                        f"({rule['samples']}次, 权重{rule.get('weight', 0):.2f})"
                    )
        
        # 淘汰规则
        if self.rejected:
            lines.append(f"\n### 已淘汰规则 ({len(self.rejected)})")
            for rule_id, rule in self.rejected.items():
                lines.append(f"❌ {rule_id}: {rule.get('reason', '未知')}")
        
        return "\n".join(lines)


def main():
    """主函数"""
    import sys
    
    validator = RuleValidator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "validate":
            validator.validate_all_rules()
        elif command == "report":
            print(validator.get_rule_report())
        else:
            print(f"未知命令: {command}")
            print("用法:")
            print("  python rule_validator.py validate  - 验证所有规则")
            print("  python rule_validator.py report    - 生成规则报告")
    else:
        # 默认：验证
        validator.validate_all_rules()


if __name__ == "__main__":
    main()
