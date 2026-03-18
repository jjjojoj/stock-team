#!/usr/bin/env python3
"""
周总结报告生成器
- 本周准确率统计
- 最佳/最差规则
- 选股标准回顾
- 下周策略调整建议
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

ACCURACY_FILE = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
MEMORY_FILE = os.path.join(PROJECT_ROOT, "learning", "memory.md")
STRATEGY_FILE = os.path.join(PROJECT_ROOT, "config", "strategy.md")
REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "weekly_reports")


class WeeklySummary:
    """周总结生成器"""
    
    def __init__(self):
        self.accuracy = self._load_json(ACCURACY_FILE, {})
        self.rules = self._load_json(RULES_FILE, {})
        os.makedirs(REPORT_DIR, exist_ok=True)
        
    def _load_json(self, path: str, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def _get_week_range(self) -> tuple:
        """获取本周日期范围"""
        today = datetime.now()
        # 周一为一周开始
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
    
    def _get_this_week_predictions(self) -> Dict:
        """获取本周预测统计"""
        by_date = self.accuracy.get("by_date", {})
        
        week_start, week_end = self._get_week_range()
        week_stats = {
            "total": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0
        }
        
        for date, stats in by_date.items():
            if week_start <= date <= week_end:
                week_stats["total"] += stats.get("total", 0)
                week_stats["correct"] += stats.get("correct", 0)
                week_stats["partial"] += stats.get("partial", 0)
        
        week_stats["wrong"] = week_stats["total"] - week_stats["correct"] - week_stats["partial"]
        
        return week_stats
    
    def _get_top_rules(self, n: int = 5) -> tuple:
        """获取最佳/最差规则"""
        by_rule = self.accuracy.get("by_rule", {})
        
        if not by_rule:
            return [], []
        
        # 计算每个规则的准确率
        rule_rates = []
        for rule, stats in by_rule.items():
            total = stats.get("total", 0)
            correct = stats.get("correct", 0)
            partial = stats.get("partial", 0)
            
            if total > 0:
                rate = (correct + partial * 0.5) / total
                rule_rates.append({
                    "rule": rule,
                    "total": total,
                    "correct": correct,
                    "partial": partial,
                    "rate": rate
                })
        
        # 排序
        rule_rates.sort(key=lambda x: x["rate"], reverse=True)
        
        top_rules = rule_rates[:n]
        worst_rules = rule_rates[-n:] if len(rule_rates) >= n else rule_rates
        
        return top_rules, worst_rules
    
    def _get_direction_analysis(self) -> Dict:
        """分析预测方向表现"""
        by_direction = self.accuracy.get("by_direction", {})
        
        analysis = {}
        for direction, stats in by_direction.items():
            total = stats.get("total", 0)
            correct = stats.get("correct", 0)
            
            analysis[direction] = {
                "total": total,
                "correct": correct,
                "rate": correct / total if total > 0 else 0
            }
        
        return analysis
    
    def generate_report(self) -> str:
        """生成周总结报告"""
        week_start, week_end = self._get_week_range()
        
        # 收集数据
        week_stats = self._get_this_week_predictions()
        top_rules, worst_rules = self._get_top_rules()
        direction_analysis = self._get_direction_analysis()
        
        # 生成报告
        report = f"""# 周总结报告

**时间范围**: {week_start} ~ {week_end}
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 本周预测统计

| 指标 | 数值 |
|------|------|
| 总预测 | {week_stats['total']} |
| ✅ 正确 | {week_stats['correct']} |
| 🔶 部分 | {week_stats['partial']} |
| ❌ 错误 | {week_stats['wrong']} |
| **准确率** | **{week_stats['correct']/max(week_stats['total'],1)*100:.1f}%** |
| **综合得分** | **{(week_stats['correct']+week_stats['partial']*0.5)/max(week_stats['total'],1)*100:.1f}%** |

---

## 📈 按预测方向分析

| 方向 | 总数 | 正确 | 准确率 |
|------|------|------|--------|
"""
        
        for direction, stats in direction_analysis.items():
            if stats["total"] > 0:
                emoji = "📈" if direction == "up" else "📉" if direction == "down" else "➡️"
                report += f"| {emoji} {direction} | {stats['total']} | {stats['correct']} | {stats['rate']*100:.1f}% |\n"
        
        report += f"""
---

## 🏆 最佳规则 TOP 5

| 规则 | 样本数 | 正确 | 部分正确 | 准确率 |
|------|--------|------|----------|--------|
"""
        
        for rule in top_rules:
            report += f"| {rule['rule']} | {rule['total']} | {rule['correct']} | {rule['partial']} | {rule['rate']*100:.1f}% |\n"
        
        report += f"""
---

## ⚠️ 最差规则 BOTTOM 5

| 规则 | 样本数 | 正确 | 部分正确 | 准确率 |
|------|--------|------|----------|--------|
"""
        
        for rule in worst_rules:
            report += f"| {rule['rule']} | {rule['total']} | {rule['correct']} | {rule['partial']} | {rule['rate']*100:.1f}% |\n"
        
        # 生成建议
        recommendations = self._generate_recommendations(week_stats, top_rules, worst_rules, direction_analysis)
        
        report += f"""
---

## 💡 下周策略建议

{recommendations}

---

## 📝 本周总结

"""
        
        # 添加总结
        accuracy = week_stats['correct']/max(week_stats['total'],1)*100
        
        if accuracy >= 75:
            report += "✅ **本周表现优秀！** 准确率达标，继续保持当前策略。\n"
        elif accuracy >= 60:
            report += "🔶 **本周表现良好。** 准确率接近目标，需要微调策略。\n"
        else:
            report += "❌ **本周表现不佳。** 准确率低于目标，需要认真复盘改进。\n"
        
        # 添加具体建议
        if direction_analysis.get("up", {}).get("rate", 0) < 0.3:
            report += "\n⚠️ **上涨预测准确率过低**，建议：\n"
            report += "- 提高上涨预测门槛（置信度要求更高）\n"
            report += "- 增加「大盘走势」作为必要条件\n"
            report += "- 减少周期股抄底预测\n"
        
        report += f"""
---

*报告自动生成 by 股票团队 AI*
"""
        
        return report
    
    def _generate_recommendations(self, week_stats, top_rules, worst_rules, direction_analysis) -> str:
        """生成下周策略建议"""
        recommendations = []
        
        accuracy = week_stats['correct']/max(week_stats['total'],1)*100
        
        # 基于准确率的建议
        if accuracy < 60:
            recommendations.append("1. **暂停自动交易**，直到准确率恢复到 60% 以上")
            recommendations.append("2. **重新审视选股标准**，排除低效规则")
        elif accuracy < 75:
            recommendations.append("1. **继续观察**，暂不调整核心策略")
        
        # 基于规则表现的建议
        if worst_rules:
            worst_rule = worst_rules[0]
            if worst_rule["rate"] < 0.3 and worst_rule["total"] >= 5:
                recommendations.append(f"3. **考虑废弃规则**: {worst_rule['rule']} (准确率仅 {worst_rule['rate']*100:.1f}%)")
        
        if top_rules:
            best_rule = top_rules[0]
            if best_rule["rate"] > 0.7:
                recommendations.append(f"4. **增加规则权重**: {best_rule['rule']} (准确率 {best_rule['rate']*100:.1f}%)")
        
        # 基于方向的建议
        up_rate = direction_analysis.get("up", {}).get("rate", 0)
        if up_rate < 0.3 and direction_analysis.get("up", {}).get("total", 0) >= 5:
            recommendations.append("5. **减少上涨预测**，当前准确率过低")
        
        if not recommendations:
            recommendations.append("1. **保持当前策略**，继续观察市场变化")
        
        return "\n".join(recommendations)
    
    def save_report(self, report: str) -> str:
        """保存报告"""
        week_start, week_end = self._get_week_range()
        filename = f"weekly_{week_start}_{week_end}.md"
        filepath = os.path.join(REPORT_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        return filepath


def main():
    print("=" * 70)
    print("📊 周总结报告生成器")
    print("=" * 70)
    print()
    
    generator = WeeklySummary()
    report = generator.generate_report()
    filepath = generator.save_report(report)
    
    print(report)
    print()
    print(f"📝 报告已保存: {filepath}")
    print("=" * 70)


if __name__ == "__main__":
    main()
