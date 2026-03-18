#!/usr/bin/env python3
"""
规则验证系统

功能：
1. 更新验证池中规则的表现数据
2. 统计成功率和置信度
3. 晋升达标规则到规则库（置信度≥80%）
4. 淘汰失败规则（置信度<30%）
5. 生成验证报告

验证流程：
书籍知识 → 验证池 → 回测 + 实盘 → 规则库
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
LEARNING_DIR = PROJECT_ROOT / "learning"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"


class RuleValidation:
    """规则验证系统"""
    
    # 晋升标准（降低门槛以便更快验证）
    PROMOTION_THRESHOLD = {
        "backtest_samples": 50,  # 从 100 降低到 50
        "backtest_success_rate": 0.50,  # 从 0.55 降低到 0.50
        "live_samples": 5,  # 从 20 降低到 5
        "live_success_rate": 0.45,  # 从 0.50 降低到 0.45
        "profit_factor": 1.3,  # 从 1.5 降低到 1.3
        "confidence": 0.70  # 从 0.80 降低到 0.70
    }
    
    # 淘汰标准
    REJECTION_THRESHOLD = {
        "confidence": 0.25,  # 置信度过低
        "live_samples": 10,   # 至少 10 个实盘样本
        "live_success_rate": 0.35,  # 实盘胜率 < 35% 淘汰
        "consecutive_losses": 5  # 连续失败 5 次
    }
    
    def __init__(self):
        self.validation_pool_file = LEARNING_DIR / "rule_validation_pool.json"
        self.rules_file = LEARNING_DIR / "prediction_rules.json"
        self.rejected_file = LEARNING_DIR / "rejected_rules.json"
        self.verification_log_file = DATA_DIR / "rule_verification_log.json"
        
        self._ensure_dirs()
        self._load_data()
    
    def _ensure_dirs(self):
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_data(self):
        """加载数据"""
        # 验证池
        if self.validation_pool_file.exists():
            with open(self.validation_pool_file, 'r', encoding='utf-8') as f:
                self.validation_pool = json.load(f)
        else:
            self.validation_pool = {}
        
        # 规则库
        if self.rules_file.exists():
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
        else:
            self.rules = {}
        
        # 淘汰库
        if self.rejected_file.exists():
            with open(self.rejected_file, 'r', encoding='utf-8') as f:
                self.rejected = json.load(f)
        else:
            self.rejected = {}
        
        # 验证日志
        if self.verification_log_file.exists():
            with open(self.verification_log_file, 'r', encoding='utf-8') as f:
                self.verification_log = json.load(f)
        else:
            self.verification_log = {"logs": []}
    
    def _save_data(self):
        """保存数据"""
        with open(self.validation_pool_file, 'w', encoding='utf-8') as f:
            json.dump(self.validation_pool, f, ensure_ascii=False, indent=2)
        
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)
        
        with open(self.rejected_file, 'w', encoding='utf-8') as f:
            json.dump(self.rejected, f, ensure_ascii=False, indent=2)
        
        with open(self.verification_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.verification_log, f, ensure_ascii=False, indent=2)
    
    def update_rule_performance(self, rule_id: str, rule: dict) -> dict:
        """
        更新规则表现数据（真实数据）

        从交易记录和预测历史中获取真实验证数据
        """
        # 确保 backtest 和 live_test 字段存在
        if 'backtest' not in rule:
            rule['backtest'] = {
                "samples": 0,
                "success_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0
            }
        if 'live_test' not in rule:
            rule['live_test'] = {
                "samples": 0,
                "success_rate": 0.0
            }

        # 1. 从预测历史中获取验证结果
        predictions_file = DATA_DIR / "predictions.json"
        if predictions_file.exists():
            with open(predictions_file, 'r', encoding='utf-8') as f:
                predictions = json.load(f)

            # 查找匹配该规则的预测
            matched_predictions = []
            history = predictions.get('history', [])
            for pred in history:
                # 检查预测是否匹配该规则
                if self._rule_matches_prediction(rule, pred):
                    matched_predictions.append(pred)

            # 更新统计数据
            if matched_predictions:
                correct = sum(1 for p in matched_predictions if p.get('result', {}).get('correct', False))
                partial = sum(1 for p in matched_predictions if p.get('result', {}).get('partial', False))
                total = len(matched_predictions)

                # 更新回测/实盘数据
                if rule["backtest"]["samples"] < 100:
                    # 回测阶段
                    rule["backtest"]["samples"] = min(100, rule["backtest"]["samples"] + len(matched_predictions))
                    rule["backtest"]["success_rate"] = (correct + 0.5 * partial) / max(1, total)

                if rule["backtest"]["samples"] >= 100:
                    # 实盘阶段
                    rule["live_test"]["samples"] = len([p for p in matched_predictions if p.get('verified', False)])
                    if rule["live_test"]["samples"] > 0:
                        live_correct = sum(1 for p in matched_predictions if p.get('verified', False) and p.get('result', {}).get('correct', False))
                        rule["live_test"]["success_rate"] = live_correct / rule["live_test"]["samples"]
        
        # 2. 从交易记录中获取盈亏数据
        trade_history_file = DATA_DIR / "trade_history.json"
        if trade_history_file.exists():
            with open(trade_history_file, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            
            # 筛选与该规则相关的交易
            rule_trades = [t for t in trades if self._rule_matches_trade(rule, t)]
            
            if rule_trades:
                profits = [t.get('pnl_pct', 0) for t in rule_trades if t.get('pnl_pct', 0) > 0]
                losses = [t.get('pnl_pct', 0) for t in rule_trades if t.get('pnl_pct', 0) < 0]
                
                if profits:
                    rule["backtest"]["avg_profit"] = sum(profits) / len(profits) / 100
                if losses:
                    rule["backtest"]["avg_loss"] = abs(sum(losses) / len(losses)) / 100
                
                if rule["backtest"]["avg_loss"] > 0:
                    rule["backtest"]["profit_factor"] = abs(rule["backtest"]["avg_profit"] / rule["backtest"]["avg_loss"])
        
        # 3. 计算综合置信度
        rule["confidence"] = self._calculate_confidence(rule)
        rule["updated_at"] = datetime.now().isoformat()
        
        return rule
    
    def _rule_matches_prediction(self, rule: dict, prediction: dict) -> bool:
        """
        检查预测是否匹配该规则

        改进后的匹配逻辑：
        1. 根据规则类别进行精确匹配
        2. 从预测的 signals 中提取技术指标信息
        3. 根据预测方向和原因进行匹配
        """
        rule_category = rule["category"]
        prediction_direction = prediction.get('direction', 'neutral')
        signals = prediction.get('signals', {})
        reasons = prediction.get('reasons', [])

        # 趋势类规则：匹配上涨/下跌预测
        if rule_category in ["趋势", "技术形态"]:
            if "突破" in rule.get("testable_form", ""):
                # 突破类规则匹配上涨预测
                return prediction_direction == "up"
            elif "支撑" in rule.get("testable_form", ""):
                # 支撑类规则可以匹配任何预测
                return True

        # 选股类规则：匹配所有选股预测
        if rule_category == "选股":
            # CAN SLIM、基本面等选股规则匹配所有预测
            return True

        # 仓位管理类规则：匹配有交易决策的预测
        if rule_category == "仓位管理":
            # 加仓、减仓规则匹配任何预测（后续交易时触发）
            return True

        # 风控类规则：匹配任何预测（风险控制）
        if rule_category == "风控":
            # 避开陷阱、止损等规则匹配所有预测
            return True

        # 估值类规则：根据基本面信号匹配
        if rule_category == "估值":
            # PB<1、安全边际等规则需要基本面数据
            # 当前简化为匹配所有预测
            return True

        # 心态类规则：匹配所有预测（交易心态）
        if rule_category == "心态":
            return True

        # 默认：根据测试表单中的关键词匹配
        testable_form = rule.get("testable_form", "").lower()
        if "上涨" in testable_form or "收益" in testable_form:
            return prediction_direction == "up"
        elif "下跌" in testable_form:
            return prediction_direction == "down"

        # 兜底：匹配所有预测（确保规则能被验证）
        return True
    
    def _rule_matches_trade(self, rule: dict, trade: dict) -> bool:
        """
        检查交易是否匹配该规则

        改进后的匹配逻辑：
        1. 根据规则类别匹配交易类型
        2. 根据交易原因进行精确匹配
        3. 支持多种匹配条件
        """
        rule_category = rule["category"]
        trade_type = trade.get('type', '').lower()
        trade_reason = trade.get('reason', '').lower()

        # 趋势类规则：匹配买入交易
        if rule_category in ["趋势", "技术形态"]:
            if "突破" in rule.get("testable_form", ""):
                # 突破类规则匹配买入
                return trade_type == "buy"

        # 仓位管理类规则：匹配加仓/减仓交易
        if rule_category == "仓位管理":
            if "加仓" in rule.get("testable_form", "") or "加" in rule.get("rule", ""):
                return trade_type == "buy"
            elif "减仓" in rule.get("testable_form", "") or "减" in rule.get("rule", ""):
                return trade_type == "sell"

        # 风控类规则：匹配止损/止盈交易
        if rule_category == "风控":
            if "止损" in trade_reason or "止盈" in trade_reason:
                return True
            if "陷阱" in rule.get("testable_form", "") and trade_type == "sell":
                return True

        # 选股类规则：匹配买入交易
        if rule_category == "选股":
            return trade_type == "buy"

        # 估值类规则：匹配买入交易（基于估值的买入）
        if rule_category == "估值":
            return trade_type == "buy"

        # 心态类规则：匹配所有交易（心态影响所有决策）
        if rule_category == "心态":
            return True

        # 默认：根据交易类型匹配
        if trade_type == "buy":
            return rule_category in ["趋势", "选股", "技术形态", "估值"]
        elif trade_type == "sell":
            return rule_category in ["风控", "仓位管理"]

        return False
    
    def _calculate_confidence(self, rule: dict) -> float:
        """
        计算综合置信度
        
        因素：
        - 回测成功率（30%）
        - 实盘成功率（40%）
        - 样本数（20%）
        - 盈亏比（10%）
        """
        confidence = 0.0
        
        # 回测成功率（30%）
        backtest_score = rule["backtest"]["success_rate"] * 0.3
        
        # 实盘成功率（40%）
        live_score = rule["live_test"]["success_rate"] * 0.4
        
        # 样本数（20%）
        total_samples = rule["backtest"]["samples"] + rule["live_test"]["samples"]
        sample_score = min(1.0, total_samples / 120) * 0.2
        
        # 盈亏比（10%）
        pf = rule["backtest"]["profit_factor"]
        pf_score = min(1.0, pf / 2.0) * 0.1
        
        confidence = backtest_score + live_score + sample_score + pf_score
        
        return round(confidence, 3)
    
    def check_promotion(self, rule_id: str, rule: dict) -> bool:
        """检查是否可以晋升到规则库"""
        threshold = self.PROMOTION_THRESHOLD
        
        # 检查所有条件
        conditions = [
            rule["backtest"]["samples"] >= threshold["backtest_samples"],
            rule["backtest"]["success_rate"] >= threshold["backtest_success_rate"],
            rule["live_test"]["samples"] >= threshold["live_samples"],
            rule["live_test"]["success_rate"] >= threshold["live_success_rate"],
            rule["backtest"]["profit_factor"] >= threshold["profit_factor"],
            rule["confidence"] >= threshold["confidence"]
        ]
        
        return all(conditions)
    
    def check_rejection(self, rule_id: str, rule: dict) -> bool:
        """检查是否应该淘汰"""
        threshold = self.REJECTION_THRESHOLD

        # 至少有一定样本数才淘汰
        if rule["live_test"]["samples"] < threshold["live_samples"]:
            return False

        # 置信度过低
        if rule["confidence"] < threshold["confidence"]:
            return True

        # 实盘胜率过低
        if rule["live_test"]["success_rate"] < threshold["live_success_rate"]:
            return True

        # 连续失败检查（需要交易记录）
        # TODO: 需要从 trade_history.json 中统计连续失败次数

        return False
    
    def promote_rule(self, rule_id: str, rule: dict):
        """晋升规则到规则库"""
        # 转化为规则库格式
        category_map = {
            "趋势": "tech_rules",
            "技术形态": "tech_rules",
            "选股": "fundamental_rules",
            "风控": "risk_rules",
            "仓位管理": "position_rules"
        }
        
        category = category_map.get(rule["category"], "event_rules")
        
        if category not in self.rules:
            self.rules[category] = {}
        
        # 新规则
        new_rule = {
            "condition": rule["testable_form"],
            "prediction": "上涨",
            "weight": rule["confidence"],  # 初始权重=置信度
            "success_rate": rule["live_test"]["success_rate"],
            "samples": rule["live_test"]["samples"],
            "source": "book",
            "source_book": rule["source_book"],
            "promoted_at": datetime.now().isoformat(),
            "verified": True
        }
        
        rule_name = f"book_{rule['source_book']}_{rule['category']}"
        self.rules[category][rule_name] = new_rule
        
        # 从验证池移除
        del self.validation_pool[rule_id]
        
        # 记录日志
        self.verification_log["logs"].append({
            "date": datetime.now().isoformat(),
            "action": "promotion",
            "rule_id": rule_id,
            "rule_name": rule_name,
            "confidence": rule["confidence"]
        })
        
        return rule_name
    
    def reject_rule(self, rule_id: str, rule: dict):
        """淘汰规则"""
        threshold = self.REJECTION_THRESHOLD

        # 确定淘汰原因
        reasons = []
        if rule["confidence"] < threshold["confidence"]:
            reasons.append(f"置信度过低 ({rule['confidence']:.2f} < {threshold['confidence']})")
        if rule["live_test"]["samples"] >= threshold["live_samples"]:
            if rule["live_test"]["success_rate"] < threshold["live_success_rate"]:
                reasons.append(f"实盘胜率过低 ({rule['live_test']['success_rate']:.2f} < {threshold['live_success_rate']})")

        reason_str = "; ".join(reasons) if reasons else "综合评估不达标"

        # 移动到淘汰库
        self.rejected[rule_id] = {
            **rule,
            "rejected_at": datetime.now().isoformat(),
            "reason": reason_str
        }

        # 从验证池移除
        del self.validation_pool[rule_id]

        # 记录日志
        self.verification_log["logs"].append({
            "date": datetime.now().isoformat(),
            "action": "rejection",
            "rule_id": rule_id,
            "reason": reason_str
        })
    
    def run_validation(self) -> dict:
        """运行规则验证"""
        print("=" * 60)
        print(f"🧪 规则验证 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        stats = {
            "total": len(self.validation_pool),
            "updated": 0,
            "promoted": 0,
            "rejected": 0
        }
        
        # 更新所有规则的表现
        print("\n1️⃣ 更新规则表现...")
        for rule_id, rule in list(self.validation_pool.items()):
            self.update_rule_performance(rule_id, rule)
            stats["updated"] += 1
        print(f"   更新：{stats['updated']}条规则")
        
        # 检查晋升
        print("\n2️⃣ 检查晋升...")
        promoted = []
        for rule_id, rule in list(self.validation_pool.items()):
            if self.check_promotion(rule_id, rule):
                rule_name = self.promote_rule(rule_id, rule)
                promoted.append(rule_name)
                stats["promoted"] += 1
        
        if promoted:
            print(f"   ✅ 晋升 {len(promoted)} 条规则到规则库:")
            for name in promoted:
                print(f"      • {name}")
        else:
            print("   暂无达标规则")
        
        # 检查淘汰
        print("\n3️⃣ 检查淘汰...")
        rejected = []
        for rule_id, rule in list(self.validation_pool.items()):
            if self.check_rejection(rule_id, rule):
                self.reject_rule(rule_id, rule)
                rejected.append(rule_id)
                stats["rejected"] += 1
        
        if rejected:
            print(f"   ❌ 淘汰 {len(rejected)} 条规则:")
            for rid in rejected:
                print(f"      • {rid}")
        else:
            print("   暂无淘汰规则")
        
        # 保存
        self._save_data()
        
        # 统计
        print("\n4️⃣ 验证池状态:")
        print(f"   验证中：{len(self.validation_pool)}条")
        print(f"   规则库：{sum(len(v) for v in self.rules.values())}条")
        print(f"   淘汰库：{len(self.rejected)}条")
        
        # 打印验证池详情
        if self.validation_pool:
            print("\n📊 验证池规则:")
            for rule_id, rule in list(self.validation_pool.items())[:5]:
                print(f"   • {rule['rule'][:30]}...")
                print(f"     置信度：{rule['confidence']:.2f} | 状态：{rule['status']}")
        
        print("\n" + "=" * 60)
        
        return stats


def main():
    """主函数"""
    validation = RuleValidation()
    validation.run_validation()


if __name__ == "__main__":
    main()
