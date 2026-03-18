#!/usr/bin/env python3
"""
规则验证样本更新脚本
根据历史预测验证结果，更新规则库中的样本数
"""

import sys
import os
import json
from datetime import datetime

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
VALIDATION_POOL_FILE = os.path.join(PROJECT_ROOT, "learning", "rule_validation_pool.json")


def load_json(path: str, default=None):
    """加载 JSON 文件"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default else {}


def save_json(path: str, data):
    """保存 JSON 文件"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_rules_from_prediction(pred: dict) -> list:
    """从预测中提取使用的规则"""
        # 优先使用 rules_used 字段
    rules_used = pred.get("rules_used", [])

    if rules_used:
        return rules_used

    # 兼容旧预测（从 signals 推断）
    rules = []
    signals = pred.get("signals", {})

    # 行业周期规则
    cycle = signals.get("industry_cycle", "medium")
    if cycle == "low":
        rules.append("industry_cycle_up")
    elif cycle == "high":
        rules.append("industry_cycle_high")

    # 技术面规则
    if signals.get("positive", 0) > signals.get("negative", 0):
        rules.append("break_ma20")

    # 情绪规则
    sentiment = signals.get("news_sentiment", "neutral")
    if sentiment == "positive":
        rules.append("positive_news")

    return rules


def update_rule_samples():
    """更新规则样本数"""
    print("=" * 60)
    print("🔄 更新规则验证样本")
    print("=" * 60)
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 加载数据
    predictions = load_json(PREDICTIONS_FILE, {"active": {}, "history": []})
    rules = load_json(RULES_FILE, {})
    validation_pool = load_json(VALIDATION_POOL_FILE, {})

    # 统计
    stats = {
        "total_predictions": 0,
        "verified_predictions": 0,
        "rules_updated": 0,
        "validation_pool_updated": 0,
    }

    # 遍历历史预测
    history = predictions.get("history", [])
    print(f"\n📚 历史预测: {len(history)} 个")

    for pred in history:
        # 只处理已验证的预测
        if pred.get("status") != "verified":
            continue

        stats["verified_predictions"] += 1

        # 提取规则
        rules_used = extract_rules_from_prediction(pred)
        if not rules_used:
            continue

        # 获取验证结果
        result = pred.get("result", {})
        correct = result.get("correct", False)
        partial = result.get("partial", False)

        # 更新规则库中的样本数
        for rule_id in rules_used:
            # 查找规则在规则库中的位置
            rule_found = False

            for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
                if category in rules and rule_id in rules[category]:
                    rule_data = rules[category][rule_id]
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

                    stats["rules_updated"] += 1
                    print(f"  ✅ 规则 {rule_id}: 样本 {new_samples}, 胜率 {rule_data['success_rate']:.1%}")

                    break

            # 更新验证池
            if rule_id not in validation_pool:
                # 创建验证池条目
                rule_info = None
                for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
                    if category in rules and rule_id in rules[category]:
                        rule_info = rules[category][rule_id]
                        break

                validation_pool[rule_id] = {
                    "rule_id": rule_id,
                    "rule": rule_info.get("condition", f"规则 {rule_id}") if rule_info else f"规则 {rule_id}",
                    "testable_form": rule_info.get("prediction", "待定义") if rule_info else "待定义",
                    "category": rule_info.get("source", "自动生成") if rule_info else "自动生成",
                    "status": "validating",
                    "confidence": 0.5,
                    "created_at": datetime.now().isoformat(),
                    "backtest": {
                        "samples": rule_info.get("samples", 0) if rule_info else 0,
                        "success_rate": rule_info.get("success_rate", 0) if rule_info else 0,
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

            # 更新验证池样本
            pool_rule = validation_pool[rule_id]
            old_samples = pool_rule["live_test"]["samples"]
            pool_rule["live_test"]["samples"] += 1
            new_samples = pool_rule["live_test"]["samples"]

            if correct:
                pool_rule["live_test"]["success_rate"] = (pool_rule["live_test"]["success_rate"] * old_samples + 1) / new_samples
            else:
                pool_rule["live_test"]["success_rate"] = (pool_rule["live_test"]["success_rate"] * old_samples) / new_samples

            pool_rule["updated_at"] = datetime.now().isoformat()
            stats["validation_pool_updated"] += 1

    # 保存更新
    save_json(RULES_FILE, rules)
    save_json(VALIDATION_POOL_FILE, validation_pool)

    # 显示统计
    print("\n" + "=" * 60)
    print("📊 更新完成")
    print(f"  验证预测: {stats['verified_predictions']}")
    print(f"  规则更新: {stats['rules_updated']}")
    print(f"  验证池更新: {stats['validation_pool_updated']}")
    print("=" * 60)

    # 显示规则统计
    print("\n📋 规则样本统计 (Top 10):")
    all_rules = []
    for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
        if category in rules:
            for rule_id, rule_data in rules[category].items():
                if rule_data.get("samples", 0) > 0:
                    all_rules.append((rule_id, rule_data))

    # 按样本数排序
    all_rules.sort(key=lambda x: x[1].get("samples", 0), reverse=True)

    for i, (rule_id, rule_data) in enumerate(all_rules[:10], 1):
        samples = rule_data.get("samples", 0)
        success_rate = rule_data.get("success_rate", 0)
        print(f"  {i}. {rule_id}: {samples} 样本, 胜率 {success_rate:.1%}")


def main():
    update_rule_samples()


if __name__ == "__main__":
    main()
