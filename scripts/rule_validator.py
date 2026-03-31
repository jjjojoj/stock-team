#!/usr/bin/env python3
"""
统一规则验证入口

职责：
1. 验证规则库中的活跃规则表现并动态调权
2. 更新验证池规则的回测/实盘表现
3. 自动晋升或淘汰验证池规则
4. 将规则库、验证池、淘汰库统一同步到 SQLite
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.predictions import normalize_prediction_collection, prediction_result_status
from core.storage import (
    CONFIG_DIR,
    DATA_DIR,
    load_json,
    load_rule_state,
    save_rule_state,
)

LEARNING_DIR = PROJECT_ROOT / "learning"


class RuleValidator:
    """统一规则验证器。"""

    MIN_WEIGHT = 0.05
    MAX_WEIGHT = 0.35
    SUCCESS_BONUS = 0.02
    FAILURE_PENALTY = 0.03

    LIBRARY_REJECTION_SAMPLES = 10
    LIBRARY_REJECTION_RATE = 0.35

    PROMOTION_THRESHOLD = {
        "backtest_samples": 50,
        "backtest_success_rate": 0.50,
        "live_samples": 5,
        "live_success_rate": 0.45,
        "profit_factor": 1.3,
        "confidence": 0.70,
    }

    VALIDATION_REJECTION_THRESHOLD = {
        "confidence": 0.25,
        "live_samples": 10,
        "live_success_rate": 0.35,
    }

    PROMOTED_RULE_CATEGORY = "validated_rules"

    def __init__(self):
        self.predictions_file = DATA_DIR / "predictions.json"
        self.trades_file = DATA_DIR / "trade_history.json"
        self.config_file = CONFIG_DIR / "prediction_config.json"

        self._load_data()

    def _load_data(self) -> None:
        """Load rules, pool, trades, and supporting files."""
        (
            self.rules,
            self.validation_pool,
            self.rejected,
            self.rule_state_summary,
        ) = load_rule_state({}, {}, {})
        self.predictions = normalize_prediction_collection(
            load_json(self.predictions_file, {"active": {}, "history": []})
        )
        self.trades = load_json(self.trades_file, [])
        self.config = load_json(self.config_file, {})

    def _save_data(self) -> None:
        """Persist all mutable rule stores."""
        self.rule_state_summary = save_rule_state(self.rules, self.validation_pool, self.rejected)
        (
            self.rules,
            self.validation_pool,
            self.rejected,
            _,
        ) = load_rule_state({}, {}, {})

    def validate_rule_library(self) -> Dict[str, int]:
        """Validate active rules already in the rule library."""
        stats = {
            "total_rules": 0,
            "updated": 0,
            "rejected": 0,
            "weight_adjusted": 0,
        }

        for category_name, category_rules in list(self.rules.items()):
            print(f"\n📊 验证规则库分类: {category_name}")

            for rule_name, rule in list(category_rules.items()):
                stats["total_rules"] += 1

                results = self._get_rule_validation_results(rule_name)
                if not results["total"]:
                    continue

                old_samples = int(rule.get("samples", 0) or 0)
                old_rate = float(rule.get("success_rate", 0.0) or 0.0)
                old_weight = float(rule.get("weight", 0.15) or 0.15)

                rule["samples"] = results["total"]
                rule["success_rate"] = results["success_rate"]
                rule["updated_at"] = datetime.now().isoformat()

                if results["total"] >= 5:
                    new_weight = self._calculate_weight(old_weight, results)
                    if abs(new_weight - old_weight) > 0.01:
                        rule["weight"] = new_weight
                        stats["weight_adjusted"] += 1
                        print(f"   ⚖️ {rule_name}: 权重 {old_weight:.2f} → {new_weight:.2f}")

                stats["updated"] += 1

                if self._should_reject_library_rule(rule):
                    self._reject_library_rule(category_name, rule_name, rule)
                    stats["rejected"] += 1
                    print(f"   ❌ 淘汰: {rule_name} (成功率 {rule['success_rate'] * 100:.1f}%)")
                    continue

                if old_samples != rule["samples"] or abs(old_rate - rule["success_rate"]) > 1e-6:
                    delta = rule["success_rate"] - old_rate
                    sign = "+" if delta >= 0 else ""
                    print(
                        f"   📈 {rule_name}: {old_samples} → {rule['samples']} 样本, "
                        f"成功率 {rule['success_rate'] * 100:.1f}% ({sign}{delta * 100:.1f}%)"
                    )

        return stats

    def validate_validation_pool(self) -> Dict[str, int]:
        """Update validation pool performance and promote/reject when due."""
        stats = {
            "total": len(self.validation_pool),
            "updated": 0,
            "promoted": 0,
            "rejected": 0,
        }

        for rule_id, rule in list(self.validation_pool.items()):
            updated_rule = self._update_pool_rule_performance(rule_id, rule)
            self.validation_pool[rule_id] = updated_rule
            stats["updated"] += 1

            if self._should_promote_pool_rule(updated_rule):
                promoted_category, promoted_rule_id = self._promote_pool_rule(rule_id, updated_rule)
                stats["promoted"] += 1
                print(
                    f"   ✅ 晋升: {rule_id} → {promoted_category}.{promoted_rule_id} "
                    f"(置信度 {updated_rule['confidence']:.2f})"
                )
                continue

            if self._should_reject_pool_rule(updated_rule):
                self._reject_pool_rule(rule_id, updated_rule)
                stats["rejected"] += 1
                print(
                    f"   ❌ 淘汰验证池规则: {rule_id} "
                    f"(实盘胜率 {updated_rule['live_test']['success_rate'] * 100:.1f}%)"
                )

        return stats

    def validate_all(self) -> Dict[str, Dict[str, int]]:
        """Run library validation + pool validation in one pass."""
        print("=" * 60)
        print(f"🧪 统一规则验证 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        if self.rule_state_summary.get("changed"):
            print("🧹 已自动清理规则库 / 验证池 / 淘汰库中的重复规则状态")

        library_stats = self.validate_rule_library()

        print("\n" + "-" * 60)
        print("🧬 更新验证池")
        print("-" * 60)

        pool_stats = self.validate_validation_pool()

        self._save_data()

        print("\n" + "=" * 60)
        print("📊 验证统计")
        print(f"   规则库总数: {library_stats['total_rules']}")
        print(f"   规则库更新: {library_stats['updated']}")
        print(f"   权重调整: {library_stats['weight_adjusted']}")
        print(f"   规则库淘汰: {library_stats['rejected']}")
        print(f"   验证池更新: {pool_stats['updated']}")
        print(f"   验证池晋升: {pool_stats['promoted']}")
        print(f"   验证池淘汰: {pool_stats['rejected']}")
        print(f"   验证池剩余: {len(self.validation_pool)}")
        print("=" * 60)

        return {"library": library_stats, "validation_pool": pool_stats}

    def _get_rule_validation_results(self, rule_name: str) -> Dict[str, Any]:
        """Aggregate verified prediction results for a given rule id."""
        results = {
            "total": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "success_rate": 0.0,
        }

        all_predictions = list(self.predictions.get("active", {}).values()) + self.predictions.get("history", [])

        for prediction in all_predictions:
            rules_used = prediction.get("rules_used") or prediction.get("matched_rules", [])
            result_status = prediction_result_status(prediction)

            if rule_name not in rules_used or result_status == "pending":
                continue

            results["total"] += 1
            if result_status == "correct":
                results["correct"] += 1
            elif result_status == "partial":
                results["partial"] += 1
            else:
                results["wrong"] += 1

        if results["total"] > 0:
            results["success_rate"] = (
                results["correct"] + 0.5 * results["partial"]
            ) / results["total"]

        return results

    def _calculate_weight(self, current_weight: float, results: Dict[str, Any]) -> float:
        """Calculate a new rule weight from verified performance."""
        success_rate = results["success_rate"]
        samples = results["total"]

        if success_rate >= 0.6:
            adjustment = self.SUCCESS_BONUS * min(samples / 10, 1.0)
            new_weight = current_weight + adjustment
        elif success_rate < 0.4:
            adjustment = self.FAILURE_PENALTY * min(samples / 10, 1.0)
            new_weight = current_weight - adjustment
        else:
            new_weight = current_weight

        return max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, new_weight))

    def _should_reject_library_rule(self, rule: Dict[str, Any]) -> bool:
        """Cull only sufficiently-sampled underperforming library rules."""
        return (
            int(rule.get("samples", 0) or 0) >= self.LIBRARY_REJECTION_SAMPLES
            and float(rule.get("success_rate", 0.0) or 0.0) < self.LIBRARY_REJECTION_RATE
        )

    def _reject_library_rule(self, category: str, rule_name: str, rule: Dict[str, Any]) -> None:
        """Move a poor library rule into the rejected store."""
        rejected_rule = {
            **rule,
            "rule_id": rule_name,
            "category": category,
            "status": "rejected",
            "rejected_at": datetime.now().isoformat(),
            "reject_reason": f"规则库成功率过低 ({rule.get('success_rate', 0.0) * 100:.1f}%)",
        }
        self.rejected[rule_name] = rejected_rule
        del self.rules[category][rule_name]

    def _update_pool_rule_performance(self, rule_id: str, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Recalculate validation pool performance from predictions + trades."""
        updated = dict(rule or {})
        updated.setdefault("backtest", {})
        updated.setdefault("live_test", {})

        matched_predictions = [
            prediction
            for prediction in (list(self.predictions.get("active", {}).values()) + self.predictions.get("history", []))
            if self._rule_matches_prediction(updated, prediction)
            and prediction_result_status(prediction) != "pending"
        ]

        matched_trades = [trade for trade in self.trades if self._rule_matches_trade(updated, trade)]

        correct = sum(1 for pred in matched_predictions if prediction_result_status(pred) == "correct")
        partial = sum(1 for pred in matched_predictions if prediction_result_status(pred) == "partial")
        total_predictions = len(matched_predictions)

        profits = [float(trade.get("pnl_pct", 0) or 0) for trade in matched_trades if float(trade.get("pnl_pct", 0) or 0) > 0]
        losses = [float(trade.get("pnl_pct", 0) or 0) for trade in matched_trades if float(trade.get("pnl_pct", 0) or 0) < 0]

        backtest_success_rate = (
            (correct + 0.5 * partial) / total_predictions if total_predictions else 0.0
        )
        live_success_rate = (
            sum(1 for trade in matched_trades if float(trade.get("pnl_pct", 0) or 0) > 0) / len(matched_trades)
            if matched_trades
            else 0.0
        )

        avg_profit = (sum(profits) / len(profits) / 100) if profits else 0.0
        avg_loss = (abs(sum(losses) / len(losses)) / 100) if losses else 0.0
        profit_factor = (avg_profit / avg_loss) if avg_loss > 0 else (avg_profit if avg_profit > 0 else 0.0)

        updated["backtest"] = {
            "samples": total_predictions,
            "success_rate": backtest_success_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
        }
        updated["live_test"] = {
            **updated.get("live_test", {}),
            "samples": len(matched_trades),
            "success_rate": live_success_rate,
            "started_at": updated.get("live_test", {}).get("started_at") or updated.get("created_at"),
        }
        updated["confidence"] = self._calculate_pool_confidence(updated)
        updated["status"] = "validating"
        updated["updated_at"] = datetime.now().isoformat()
        updated["rule_id"] = updated.get("rule_id", rule_id)

        return updated

    def _rule_matches_prediction(self, rule: Dict[str, Any], prediction: Dict[str, Any]) -> bool:
        """Heuristic match between validation-pool rule and a prediction."""
        category = rule.get("category", "")
        direction = prediction.get("direction", "neutral")
        testable_form = str(rule.get("testable_form", ""))

        if category in {"趋势", "技术形态"}:
            if "下跌" in testable_form:
                return direction == "down"
            return direction == "up"
        if category in {"选股", "估值", "心态"}:
            return True
        if category == "仓位管理":
            return bool(prediction.get("rules_used") or prediction.get("matched_rules"))
        if category == "风控":
            return direction in {"down", "neutral"} or "止损" in testable_form

        lowered = testable_form.lower()
        if "上涨" in lowered or "收益" in lowered or "突破" in lowered:
            return direction == "up"
        if "下跌" in lowered:
            return direction == "down"

        return True

    def _rule_matches_trade(self, rule: Dict[str, Any], trade: Dict[str, Any]) -> bool:
        """Heuristic match between validation-pool rule and a trade."""
        category = rule.get("category", "")
        trade_type = str(trade.get("type", "")).lower()
        trade_reason = str(trade.get("reason", "")).lower()
        testable_form = str(rule.get("testable_form", ""))
        rule_text = str(rule.get("rule", ""))

        if category in {"趋势", "技术形态", "选股", "估值"}:
            return trade_type == "buy"
        if category == "仓位管理":
            if "减仓" in testable_form or "减" in rule_text:
                return trade_type == "sell"
            return trade_type == "buy"
        if category == "风控":
            return any(keyword in trade_reason for keyword in ("止损", "止盈", "风险"))
        if category == "心态":
            return True

        return trade_type in {"buy", "sell"}

    def _calculate_pool_confidence(self, rule: Dict[str, Any]) -> float:
        """Calculate blended confidence for a validation-pool rule."""
        backtest = rule.get("backtest") or {}
        live_test = rule.get("live_test") or {}

        backtest_score = float(backtest.get("success_rate", 0.0) or 0.0) * 0.3
        live_score = float(live_test.get("success_rate", 0.0) or 0.0) * 0.4
        total_samples = int(backtest.get("samples", 0) or 0) + int(live_test.get("samples", 0) or 0)
        sample_score = min(1.0, total_samples / 120) * 0.2
        profit_factor = float(backtest.get("profit_factor", 0.0) or 0.0)
        profit_score = min(1.0, profit_factor / 2.0) * 0.1

        return round(backtest_score + live_score + sample_score + profit_score, 3)

    def _should_promote_pool_rule(self, rule: Dict[str, Any]) -> bool:
        """Check if a validation-pool rule is ready for promotion."""
        backtest = rule.get("backtest") or {}
        live_test = rule.get("live_test") or {}
        threshold = self.PROMOTION_THRESHOLD

        return all(
            [
                int(backtest.get("samples", 0) or 0) >= threshold["backtest_samples"],
                float(backtest.get("success_rate", 0.0) or 0.0) >= threshold["backtest_success_rate"],
                int(live_test.get("samples", 0) or 0) >= threshold["live_samples"],
                float(live_test.get("success_rate", 0.0) or 0.0) >= threshold["live_success_rate"],
                float(backtest.get("profit_factor", 0.0) or 0.0) >= threshold["profit_factor"],
                float(rule.get("confidence", 0.0) or 0.0) >= threshold["confidence"],
            ]
        )

    def _should_reject_pool_rule(self, rule: Dict[str, Any]) -> bool:
        """Check whether a validation-pool rule should be discarded."""
        live_test = rule.get("live_test") or {}
        threshold = self.VALIDATION_REJECTION_THRESHOLD

        if int(live_test.get("samples", 0) or 0) < threshold["live_samples"]:
            return False

        if float(rule.get("confidence", 0.0) or 0.0) < threshold["confidence"]:
            return True

        return float(live_test.get("success_rate", 0.0) or 0.0) < threshold["live_success_rate"]

    def _promote_pool_rule(self, rule_id: str, rule: Dict[str, Any]) -> Tuple[str, str]:
        """Promote a validation-pool rule into the library."""
        category = rule.get("target_category") or self.PROMOTED_RULE_CATEGORY
        promoted_rule = {
            "condition": rule.get("testable_form", rule.get("rule", "")),
            "prediction": self._infer_prediction(rule),
            "weight": max(0.15, min(self.MAX_WEIGHT, float(rule.get("confidence", 0.15) or 0.15))),
            "success_rate": float(rule.get("live_test", {}).get("success_rate", 0.0) or 0.0),
            "samples": int(rule.get("live_test", {}).get("samples", 0) or 0),
            "source": rule.get("source_book") or rule.get("source") or "validation_pool",
            "source_book": rule.get("source_book"),
            "origin_rule_id": rule_id,
            "metadata": {
                "validation_confidence": rule.get("confidence", 0.0),
                "backtest": rule.get("backtest", {}),
                "live_test": rule.get("live_test", {}),
            },
            "created_at": rule.get("created_at"),
            "updated_at": datetime.now().isoformat(),
            "promoted_at": datetime.now().isoformat(),
            "status": "active",
        }

        self.rules.setdefault(category, {})[rule_id] = promoted_rule
        del self.validation_pool[rule_id]
        return category, rule_id

    def _reject_pool_rule(self, rule_id: str, rule: Dict[str, Any]) -> None:
        """Reject a validation-pool rule and archive it."""
        rejected_rule = {
            **rule,
            "rule_id": rule_id,
            "status": "rejected",
            "rejected_at": datetime.now().isoformat(),
            "reject_reason": (
                f"置信度 {rule.get('confidence', 0.0):.2f} / "
                f"实盘胜率 {rule.get('live_test', {}).get('success_rate', 0.0) * 100:.1f}% 不达标"
            ),
            "updated_at": datetime.now().isoformat(),
        }
        self.rejected[rule_id] = rejected_rule
        del self.validation_pool[rule_id]

    def _infer_prediction(self, rule: Dict[str, Any]) -> str:
        """Infer a high-level prediction label for promoted rules."""
        text = f"{rule.get('rule', '')} {rule.get('testable_form', '')}"
        if "下跌" in text or "止损" in text or "回避" in text:
            return "风险规避"
        if "突破" in text or "上涨" in text or "收益" in text:
            return "上涨"
        if "估值" in text or "安全边际" in text:
            return "低估"
        return "待验证模式"

    def get_rule_report(self) -> str:
        """Generate a markdown summary for rule validation."""
        lines = [
            "📊 **统一规则验证报告**",
            f"\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        total_rules = sum(len(category_rules) for category_rules in self.rules.values())
        lines.append(f"规则库总数: {total_rules}")
        lines.append(f"验证池规则: {len(self.validation_pool)}")
        lines.append(f"淘汰规则: {len(self.rejected)}")

        lines.append("\n### 规则库样本规则")
        ranked_rules: List[Tuple[str, str, Dict[str, Any]]] = []
        for category, category_rules in self.rules.items():
            for rule_id, rule in category_rules.items():
                if int(rule.get("samples", 0) or 0) > 0:
                    ranked_rules.append((category, rule_id, rule))

        ranked_rules.sort(
            key=lambda item: (
                float(item[2].get("success_rate", 0.0) or 0.0),
                int(item[2].get("samples", 0) or 0),
            ),
            reverse=True,
        )

        if ranked_rules:
            for category, rule_id, rule in ranked_rules[:10]:
                lines.append(
                    f"✅ {category}.{rule_id}: {rule.get('success_rate', 0.0) * 100:.1f}% "
                    f"({rule.get('samples', 0)}次, 权重 {rule.get('weight', 0):.2f})"
                )
        else:
            lines.append("暂无有样本的活跃规则")

        lines.append("\n### 验证池候选")
        pool_rules = sorted(
            self.validation_pool.items(),
            key=lambda item: (
                float(item[1].get("confidence", 0.0) or 0.0),
                int(item[1].get("backtest", {}).get("samples", 0) or 0),
            ),
            reverse=True,
        )
        if pool_rules:
            for rule_id, rule in pool_rules[:10]:
                lines.append(
                    f"🧪 {rule_id}: 置信度 {rule.get('confidence', 0.0):.2f}, "
                    f"回测 {rule.get('backtest', {}).get('success_rate', 0.0) * 100:.1f}%/"
                    f"{rule.get('backtest', {}).get('samples', 0)}次, "
                    f"实盘 {rule.get('live_test', {}).get('success_rate', 0.0) * 100:.1f}%/"
                    f"{rule.get('live_test', {}).get('samples', 0)}次"
                )
        else:
            lines.append("验证池为空")

        if self.rejected:
            lines.append(f"\n### 已淘汰规则 ({len(self.rejected)})")
            for rule_id, rule in list(self.rejected.items())[:10]:
                lines.append(f"❌ {rule_id}: {rule.get('reject_reason') or rule.get('reason', '未知原因')}")

        return "\n".join(lines)


def main() -> None:
    """CLI entrypoint."""
    validator = RuleValidator()

    if len(sys.argv) <= 1:
        results = validator.validate_all()
        _notify_rule_validation(validator, results)
        return

    command = sys.argv[1]
    if command in {"validate", "validate-all"}:
        results = validator.validate_all()
        _notify_rule_validation(validator, results)
    elif command == "validate-library":
        validator.validate_rule_library()
        validator._save_data()
    elif command == "validate-pool":
        validator.validate_validation_pool()
        validator._save_data()
    elif command == "report":
        print(validator.get_rule_report())
    else:
        print(f"未知命令: {command}")
        print("用法:")
        print("  python rule_validator.py validate         - 全量验证规则库 + 验证池")
        print("  python rule_validator.py validate-library - 只验证规则库")
        print("  python rule_validator.py validate-pool    - 只更新验证池")
        print("  python rule_validator.py report           - 生成规则报告")
        sys.exit(1)


def _notify_rule_validation(validator: RuleValidator, results: Dict[str, Dict[str, int]]) -> None:
    """将规则验证结果发送到飞书。"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from feishu_notifier import send_feishu_message

        library = results.get("library", {})
        pool = results.get("validation_pool", {})
        report = f"""时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

规则库
- 总规则：{library.get('total_rules', 0)}
- 更新：{library.get('updated', 0)}
- 调权：{library.get('weight_adjusted', 0)}
- 淘汰：{library.get('rejected', 0)}

验证池
- 更新：{pool.get('updated', 0)}
- 晋升：{pool.get('promoted', 0)}
- 淘汰：{pool.get('rejected', 0)}
- 剩余：{len(validator.validation_pool)}

规则库样本规则
{validator.get_rule_report()}"""
        send_feishu_message(
            title=f"🧪 规则验证日报 - {datetime.now().strftime('%Y-%m-%d')}",
            content=report,
            level="info",
        )
        print("✅ 飞书通知已发送")
    except Exception as exc:
        print(f"⚠️ 飞书通知发送失败: {exc}")


if __name__ == "__main__":
    main()
