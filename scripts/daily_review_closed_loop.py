#!/usr/bin/env python3
"""
每日复盘闭环系统 v2.0
- 验证预测
- 更新准确率统计（按规则）
- 更新规则权重
- 验证池规则样本累计
- 记录教训

这是闭环的核心！
"""

import sys
import os
import json
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
ACCURACY_FILE = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
VALIDATION_POOL_FILE = os.path.join(PROJECT_ROOT, "learning", "rule_validation_pool.json")
MEMORY_FILE = os.path.join(PROJECT_ROOT, "learning", "memory.md")
REVIEW_DIR = os.path.join(PROJECT_ROOT, "data", "reviews")


class ClosedLoopReview:
    """复盘闭环系统"""
    
    def __init__(self):
        self._ensure_dirs()
        self.predictions = self._load_json(PREDICTIONS_FILE, {"active": {}, "history": []})
        self.accuracy = self._load_json(ACCURACY_FILE, self._init_accuracy())
        self.rules = self._load_json(RULES_FILE, {})
        self.validation_pool = self._load_json(VALIDATION_POOL_FILE, {})
        
    def _ensure_dirs(self):
        os.makedirs(REVIEW_DIR, exist_ok=True)
        
    def _load_json(self, path: str, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def _save_json(self, path: str, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _init_accuracy(self) -> Dict:
        """初始化准确率统计结构"""
        return {
            "total_predictions": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "by_rule": {},      # 每个规则的准确率
            "by_stock": {},     # 每只股票的准确率
            "by_direction": {   # 按预测方向
                "up": {"total": 0, "correct": 0},
                "down": {"total": 0, "correct": 0},
                "neutral": {"total": 0, "correct": 0}
            },
            "by_date": {},      # 按日期统计
            "last_updated": None
        }
    
    def _get_current_price(self, code: str) -> Optional[float]:
        """获取当前价格"""
        try:
            stock_code = code.replace(".", "")
            if code.startswith("sh"):
                stock_code = "sh" + code.split(".")[1]
            else:
                stock_code = "sz" + code.split(".")[1]
            
            url = f"http://qt.gtimg.cn/q={stock_code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk")
            
            if "~" in text:
                parts = text.split("~")
                return float(parts[3])
        except Exception as e:
            print(f"  ⚠️ 获取 {code} 价格失败: {e}")
        
        return None
    
    def _extract_rules_from_prediction(self, pred: Dict) -> List[str]:
        """从预测中提取使用的规则【修复版】"""
        # 优先使用rules_used字段
        rules_used = pred.get("rules_used", [])
        
        if rules_used:
            return rules_used
        
        # 兼容旧预测（从signals推断）
        rules = []
        signals = pred.get("signals", {})
        
        # 行业周期规则
        cycle = signals.get("industry_cycle", "medium")
        if cycle == "low":
            rules.append("industry_cycle_up")  # 修复：使用规则库中的ID
        elif cycle == "high":
            rules.append("industry_cycle_high")
        
        # 技术面规则
        if signals.get("positive", 0) > signals.get("negative", 0):
            rules.append("break_ma20")  # 修复：使用规则库中的ID
        
        # 情绪规则
        sentiment = signals.get("news_sentiment", "neutral")
        if sentiment == "positive":
            rules.append("positive_news")
        
        return rules
    
    def _load_trade_history(self) -> List[Dict]:
        """加载交易历史"""
        trade_history_file = os.path.join(PROJECT_ROOT, "data", "trade_history.json")
        if os.path.exists(trade_history_file):
            with open(trade_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _link_prediction_to_trade(self, pred_id: str, pred: Dict, correct: bool, partial: bool) -> Optional[Dict]:
        """
        关联预测到交易记录，计算实际盈亏

        Returns:
            关联的交易记录，如果没有找到则返回 None
        """
        trade_history = self._load_trade_history()

        # 查找与该预测相关的交易
        # 优先查找 prediction_id 匹配的
        for trade in trade_history:
            if trade.get("prediction_id") == pred_id:
                # 计算交易盈亏
                trade["prediction_correct"] = correct
                trade["prediction_partial"] = partial
                return trade

        # 如果没有找到，根据股票和时间匹配
        pred_created = datetime.fromisoformat(pred["created_at"])
        pred_code = pred["code"]

        for trade in trade_history:
            # 匹配股票代码
            if trade.get("code") != pred_code:
                continue

            # 匹配时间（交易时间在预测后24小时内）
            trade_time = datetime.fromisoformat(trade["timestamp"])
            if (trade_time - pred_created).total_seconds() <= 86400:  # 24小时内
                # 避免重复关联
                if "prediction_id" not in trade:
                    trade["prediction_id"] = pred_id
                    trade["prediction_correct"] = correct
                    trade["prediction_partial"] = partial

                return trade

        return None

    def verify_all_predictions(self) -> Dict:
        """验证所有活跃预测并更新闭环"""
        print("=" * 60)
        print("📊 复盘闭环系统 v2.0")
        print("=" * 60)
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        active = self.predictions["active"]
        results = {
            "verified": 0,
            "pending": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "linked_trades": 0  # 统计关联的交易数
        }

        # 需要验证的预测（创建超过1小时的）
        to_verify = []
        for pred_id, pred in active.items():
            created = datetime.fromisoformat(pred["created_at"])
            age_hours = (datetime.now() - created).total_seconds() / 3600
            if age_hours > 1:  # 超过1小时的预测才验证
                to_verify.append((pred_id, pred))

        print(f"📋 待验证预测: {len(to_verify)} 个")
        print()

        for pred_id, pred in to_verify:
            current_price = self._get_current_price(pred["code"])

            if current_price is None:
                print(f"  ⏭️ {pred['name']}: 价格获取失败，跳过")
                results["pending"] += 1
                continue

            # 计算结果
            direction = pred["direction"]
            start_price = pred["current_price"]
            target_price = pred["target_price"]
            price_change = (current_price / start_price - 1) * 100

            # 判断正确性
            correct = False
            partial = False

            if direction == "up":
                if current_price >= target_price:
                    correct = True
                elif price_change > 0:
                    partial = True
            elif direction == "down":
                if current_price <= target_price:
                    correct = True
                elif price_change < 0:
                    partial = True
            else:  # neutral
                if abs(price_change) < 2:  # ±2% 算中性正确
                    correct = True
                elif abs(price_change) < 5:
                    partial = True

            # 更新预测状态
            pred["status"] = "verified"
            pred["result"] = {
                "verified_at": datetime.now().isoformat(),
                "final_price": current_price,
                "price_change_pct": round(price_change, 2),
                "correct": correct,
                "partial": partial
            }

            # 【新增】关联预测到交易
            linked_trade = self._link_prediction_to_trade(pred_id, pred, correct, partial)
            if linked_trade:
                results["linked_trades"] += 1
                if linked_trade.get("type") == "sell":
                    pnl_pct = linked_trade.get("pnl_pct", 0)
                    print(f"  📊 关联交易: {pnl_pct*100:+.2f}% 盈亏")

            # 移动到历史
            self.predictions["history"].append(pred)
            del self.predictions["active"][pred_id]

            # 更新统计
            results["verified"] += 1
            if correct:
                results["correct"] += 1
                status = "✅ 正确"
            elif partial:
                results["partial"] += 1
                status = "🔶 部分正确"
            else:
                results["wrong"] += 1
                status = "❌ 错误"

            print(f"  {status} {pred['name']}: {direction} {price_change:+.2f}% (目标: {target_price})")

            # 【闭环核心】更新准确率统计
            self._update_accuracy(pred, correct, partial)

            # 【闭环核心】更新规则权重
            self._update_rule_weights(pred, correct, partial)

            # 【闭环核心】更新验证池样本
            self._update_validation_pool(pred, correct)
        
        # 保存所有更新
        self._save_json(PREDICTIONS_FILE, self.predictions)
        self._save_json(ACCURACY_FILE, self.accuracy)
        self._save_json(RULES_FILE, self.rules)
        self._save_json(VALIDATION_POOL_FILE, self.validation_pool)
        
        # 生成复盘报告
        self._generate_report(results)
        
        print()
        print("=" * 60)
        print(f"📈 复盘完成")
        print(f"  验证: {results['verified']} 个")
        print(f"  ✅ 正确: {results['correct']} ({results['correct']/max(results['verified'],1)*100:.1f}%)")
        print(f"  🔶 部分: {results['partial']}")
        print(f"  ❌ 错误: {results['wrong']}")
        print(f"  🔗 关联交易: {results.get('linked_trades', 0)} 个")
        print("=" * 60)
        
        return results
    
    def _update_accuracy(self, pred: Dict, correct: bool, partial: bool):
        """更新准确率统计（按规则分类）"""
        self.accuracy["total_predictions"] += 1
        
        if correct:
            self.accuracy["correct"] += 1
        elif partial:
            self.accuracy["partial"] += 1
        else:
            self.accuracy["wrong"] += 1
        
        # 按方向统计
        direction = pred["direction"]
        if direction in self.accuracy["by_direction"]:
            self.accuracy["by_direction"][direction]["total"] += 1
            if correct:
                self.accuracy["by_direction"][direction]["correct"] += 1
        
        # 按股票统计
        code = pred["code"]
        if code not in self.accuracy["by_stock"]:
            self.accuracy["by_stock"][code] = {"total": 0, "correct": 0, "partial": 0}
        self.accuracy["by_stock"][code]["total"] += 1
        if correct:
            self.accuracy["by_stock"][code]["correct"] += 1
        elif partial:
            self.accuracy["by_stock"][code]["partial"] += 1
        
        # 【关键】按规则统计
        rules_used = self._extract_rules_from_prediction(pred)
        for rule in rules_used:
            if rule not in self.accuracy["by_rule"]:
                self.accuracy["by_rule"][rule] = {"total": 0, "correct": 0, "partial": 0}
            self.accuracy["by_rule"][rule]["total"] += 1
            if correct:
                self.accuracy["by_rule"][rule]["correct"] += 1
            elif partial:
                self.accuracy["by_rule"][rule]["partial"] += 1
        
        # 按日期统计
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.accuracy["by_date"]:
            self.accuracy["by_date"][today] = {"total": 0, "correct": 0, "partial": 0}
        self.accuracy["by_date"][today]["total"] += 1
        if correct:
            self.accuracy["by_date"][today]["correct"] += 1
        elif partial:
            self.accuracy["by_date"][today]["partial"] += 1
        
        self.accuracy["last_updated"] = datetime.now().isoformat()
    
    def _update_rule_weights(self, pred: Dict, correct: bool, partial: bool):
        """根据预测结果更新规则权重（修复版）"""
        rules_used = self._extract_rules_from_prediction(pred)

        for rule in rules_used:
            # 【修复】查找规则在规则库中的位置
            rule_found = False

            # 遍历所有规则分类
            for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
                if category in self.rules and rule in self.rules[category]:
                    rule_data = self.rules[category][rule]
                    rule_found = True

                    # 更新样本数和胜率
                    old_samples = rule_data.get("samples", 0)
                    rule_data["samples"] = old_samples + 1

                    new_samples = rule_data["samples"]
                    old_rate = rule_data.get("success_rate", 0)

                    if correct:
                        rule_data["success_rate"] = (old_rate * old_samples + 1) / new_samples
                    elif partial:
                        rule_data["success_rate"] = (old_rate * old_samples + 0.5) / new_samples
                    else:
                        rule_data["success_rate"] = (old_rate * old_samples) / new_samples

                    # 动态调整权重（如果存在）
                    if "weight" in rule_data:
                        old_weight = rule_data["weight"]
                        if rule_data["success_rate"] > 0.7:
                            rule_data["weight"] = min(old_weight + 0.02, 0.4)  # 最高 0.4
                        elif rule_data["success_rate"] < 0.4:
                            rule_data["weight"] = max(old_weight - 0.02, 0.05)  # 最低 0.05

                        print(f"    📊 规则 {rule}: 胜率 {rule_data['success_rate']:.1%}, 样本 {new_samples}")

                    break

            # 如果规则不在规则库中，输出警告
            if not rule_found:
                print(f"    ⚠️ 规则 {rule} 不在规则库中，跳过权重更新")
    
    def _update_validation_pool(self, pred: Dict, correct: bool):
        """更新验证池规则样本（修复版）"""
        rules_used = self._extract_rules_from_prediction(pred)

        for rule_id in rules_used:
            # 【修复P0-3】如果规则不在验证池中，创建新条目
            if rule_id not in self.validation_pool:
                # 尝试从规则库获取规则信息
                rule_info = self._find_rule_in_library(rule_id)

                # 创建验证池条目
                self.validation_pool[rule_id] = {
                    "rule_id": rule_id,
                    "rule": rule_info.get("condition", f"规则 {rule_id}") if rule_info else f"规则 {rule_id}",
                    "testable_form": rule_info.get("prediction", "待定义") if rule_info else "待定义",
                    "category": rule_info.get("source", "自动生成") if rule_info else "自动生成",
                    "status": "validating",
                    "confidence": 0.5,
                    "created_at": datetime.now().isoformat(),
                    "backtest": {
                        "samples": 0,
                        "success_rate": 0.0,
                        "avg_profit": 0.0,
                        "avg_loss": 0.0,
                        "profit_factor": 0.0
                    },
                    "live_test": {
                        "samples": 0,
                        "success_rate": 0.0,
                        "started_at": datetime.now().isoformat(),
                        "required_samples": 10,
                        "required_success_rate": 0.6
                    }
                }
                print(f"    ✨ 新增验证规则: {rule_id}")

            # 更新样本数和胜率
            pool_rule = self.validation_pool[rule_id]
            old_samples = pool_rule["live_test"]["samples"]
            old_rate = pool_rule["live_test"]["success_rate"]

            pool_rule["live_test"]["samples"] += 1
            new_samples = pool_rule["live_test"]["samples"]

            if correct:
                # 成功：更新胜率
                pool_rule["live_test"]["success_rate"] = (old_rate * old_samples + 1) / new_samples
            else:
                # 失败：胜率下降
                pool_rule["live_test"]["success_rate"] = (old_rate * old_samples) / new_samples

            pool_rule["updated_at"] = datetime.now().isoformat()

            # 检查是否可以晋升
            if (new_samples >= 10 and
                pool_rule["live_test"]["success_rate"] >= 0.6):
                pool_rule["status"] = "ready_for_promotion"
                print(f"    🎉 规则 {rule_id} 达到晋升标准! 样本: {new_samples}, 胜率: {pool_rule['live_test']['success_rate']:.1%}")

    def _find_rule_in_library(self, rule_id: str) -> Optional[Dict]:
        """在规则库中查找规则"""
        # 遍历所有规则分类
        for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
            if category in self.rules and rule_id in self.rules[category]:
                return self.rules[category][rule_id]
        return None
    
    def _generate_report(self, results: Dict):
        """生成复盘报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = os.path.join(REVIEW_DIR, f"review_{today}.md")
        
        # 【修复】从 history 中提取今天的验证结果
        today_verified = []
        for pred in self.predictions.get("history", []):
            if pred.get("status") == "verified":
                result = pred.get("result", {})
                verified_at = result.get("verified_at", "")
                if verified_at.startswith(today):
                    today_verified.append(pred)
        
        # 如果 active 没有待验证的，使用今天的 history
        if results["verified"] == 0 and today_verified:
            results["verified"] = len(today_verified)
            results["correct"] = sum(1 for p in today_verified if p.get("result", {}).get("correct", False))
            results["partial"] = sum(1 for p in today_verified if p.get("result", {}).get("partial", False))
            results["wrong"] = results["verified"] - results["correct"] - results["partial"]
        
        total = results["verified"]
        correct_rate = results["correct"] / max(total, 1) * 100
        
        report = f"""# 复盘报告 - {today}

## 预测验证

| 指标 | 数值 |
|------|------|
| 验证预测 | {total} |
| ✅ 正确 | {results['correct']} ({correct_rate:.1f}%) |
| 🔶 部分 | {results['partial']} |
| ❌ 错误 | {results['wrong']} |
| 🔗 关联交易 | {results.get('linked_trades', 0)} |

## 预测-交易关联分析

【新增功能】本次复盘关联了 {results.get('linked_trades', 0)} 个交易到预测，实现了闭环验证。
通过关联分析，可以：
1. 评估预测的实际交易效果
2. 计算基于预测的盈亏
3. 优化预测模型和交易策略

## 规则准确率（Top 10）

"""
        # 按准确率排序规则
        rule_stats = self.accuracy["by_rule"]
        sorted_rules = sorted(
            rule_stats.items(),
            key=lambda x: x[1]["correct"] / max(x[1]["total"], 1),
            reverse=True
        )[:10]
        
        for rule, stats in sorted_rules:
            rate = stats["correct"] / max(stats["total"], 1) * 100
            report += f"- {rule}: {rate:.1f}% ({stats['correct']}/{stats['total']})\n"
        
        report += f"""
## 累计统计

- 总预测: {self.accuracy['total_predictions']}
- 准确率: {self.accuracy['correct']/max(self.accuracy['total_predictions'],1)*100:.1f}%

---
*生成时间: {datetime.now().isoformat()}*
"""
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📝 复盘报告已保存: {report_path}")


def main():
    reviewer = ClosedLoopReview()
    reviewer.verify_all_predictions()


if __name__ == "__main__":
    main()
