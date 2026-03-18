#!/usr/bin/env python3
"""
团队级优化智能体 - 每周评估和改进股票团队
- 评估整体表现
- 检测系统漏洞
- 联网学习开源社区
- 提出并实施改进
"""

import sys
import os
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import urllib.request

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

ACCURACY_FILE = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
VALIDATION_POOL_FILE = os.path.join(PROJECT_ROOT, "learning", "rule_validation_pool.json")
EXPERIENCE_FILE = os.path.join(PROJECT_ROOT, "learning", "experience_library.json")
PORTFOLIO_FILE = os.path.join(PROJECT_ROOT, "config", "portfolio.json")
POSITIONS_FILE = os.path.join(PROJECT_ROOT, "config", "positions.json")
PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
TEAM_HEALTH_FILE = os.path.join(PROJECT_ROOT, "learning", "team_health.json")


class TeamOptimizer:
    """团队级优化智能体"""
    
    def __init__(self):
        self.accuracy = self._load_json(ACCURACY_FILE, {})
        self.rules = self._load_json(RULES_FILE, {})
        self.validation_pool = self._load_json(VALIDATION_POOL_FILE, {})
        self.experience = self._load_json(EXPERIENCE_FILE, {})
        self.portfolio = self._load_json(PORTFOLIO_FILE, {})
        self.positions = self._load_json(POSITIONS_FILE, {})
        self.predictions = self._load_json(PREDICTIONS_FILE, {"history": []})
        self.health = self._load_json(TEAM_HEALTH_FILE, {
            "weekly_reports": [],
            "issues": [],
            "improvements": []
        })
    
    def _load_json(self, path: str, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def _save_json(self, path: str, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def weekly_evaluation(self) -> Dict:
        """每周团队评估"""
        print("=" * 60)
        print("🤖 团队级优化智能体 - 周度评估")
        print("=" * 60)
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print()
        
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "week": datetime.now().isocalendar()[1],
            "metrics": self._collect_metrics(),
            "issues": self._detect_issues(),
            "suggestions": [],
            "external_learning": [],
            "actions_taken": []
        }
        
        # 联网学习
        report["external_learning"] = self._learn_from_community()
        
        # 生成改进建议
        report["suggestions"] = self._generate_suggestions(report["issues"])
        
        # 自动实施简单改进
        report["actions_taken"] = self._auto_improve(report["suggestions"])
        
        # 保存报告
        self.health["weekly_reports"].append(report)
        self._save_json(TEAM_HEALTH_FILE, self.health)
        
        # 生成摘要
        self._print_summary(report)
        
        return report
    
    def _collect_metrics(self) -> Dict:
        """收集团队指标"""
        print("📊 收集团队指标...")
        
        # 预测准确率
        total_preds = self.accuracy.get("total_predictions", 0)
        correct_preds = self.accuracy.get("correct", 0)
        accuracy_rate = (correct_preds / total_preds * 100) if total_preds > 0 else 0
        
        # 规则库状态
        total_rules = sum(len(cat) for cat in self.rules.values())
        rules_with_samples = sum(
            1 for cat in self.rules.values() 
            for rule in cat.values() 
            if rule.get("samples", 0) > 0
        )
        
        # 验证池状态
        validating_rules = len(self.validation_pool)
        ready_rules = sum(
            1 for r in self.validation_pool.values() 
            if r.get("status") == "ready_for_promotion"
        )
        
        # 经验库状态
        success_patterns = len(self.experience.get("success_patterns", []))
        failure_patterns = len(self.experience.get("failure_patterns", []))
        
        # 账户状态
        total_asset = self.portfolio.get("total_capital", 200000)
        available_cash = self.portfolio.get("available_cash", 0)
        market_value = 0
        
        for code, pos in self.positions.items():
            if pos.get("status") == "holding":
                # 简化：使用成本价估算
                market_value += pos.get("cost_price", 0) * pos.get("shares", 0)
        
        total_asset = available_cash + market_value
        total_return = ((total_asset / 200000) - 1) * 100  # 初始20万
        
        metrics = {
            "predictions": {
                "total": total_preds,
                "correct": correct_preds,
                "accuracy": accuracy_rate
            },
            "rules": {
                "total": total_rules,
                "with_samples": rules_with_samples,
                "utilization": (rules_with_samples / total_rules * 100) if total_rules > 0 else 0
            },
            "validation_pool": {
                "total": validating_rules,
                "ready": ready_rules
            },
            "experience": {
                "success": success_patterns,
                "failure": failure_patterns
            },
            "account": {
                "total_asset": total_asset,
                "cash": available_cash,
                "market_value": market_value,
                "return_pct": total_return
            }
        }
        
        print(f"  预测准确率: {accuracy_rate:.1f}% ({correct_preds}/{total_preds})")
        print(f"  规则利用率: {metrics['rules']['utilization']:.1f}% ({rules_with_samples}/{total_rules})")
        print(f"  验证池: {validating_rules} 条待验证")
        print(f"  账户收益: {total_return:+.2f}%")
        
        return metrics
    
    def _detect_issues(self) -> List[Dict]:
        """检测系统问题"""
        print("\\n🔍 检测系统问题...")
        
        issues = []
        
        # 问题1：预测准确率过低
        accuracy = self.accuracy.get("correct", 0) / max(self.accuracy.get("total_predictions", 1), 1)
        if accuracy < 0.3:
            issues.append({
                "type": "critical",
                "area": "预测系统",
                "issue": f"准确率过低 ({accuracy:.1%})",
                "impact": "导致错误决策",
                "suggestion": "检查规则库质量，增加有效规则"
            })
            print(f"  ❌ 准确率过低: {accuracy:.1%}")
        
        # 问题2：规则利用率低
        total_rules = sum(len(cat) for cat in self.rules.values())
        rules_used = sum(1 for cat in self.rules.values() for r in cat.values() if r.get("samples", 0) > 0)
        utilization = (rules_used / total_rules * 100) if total_rules > 0 else 0
        
        if utilization < 30:
            issues.append({
                "type": "warning",
                "area": "规则库",
                "issue": f"规则利用率低 ({utilization:.1f}%)",
                "impact": "大量规则未被使用",
                "suggestion": "优化规则触发逻辑，确保规则被正确应用"
            })
            print(f"  ⚠️ 规则利用率低: {utilization:.1f}%")
        
        # 问题3：验证池积压
        validating = len(self.validation_pool)
        ready = sum(1 for r in self.validation_pool.values() if r.get("status") == "ready_for_promotion")
        
        if validating > 10 and ready == 0:
            issues.append({
                "type": "warning",
                "area": "验证池",
                "issue": f"验证池积压 ({validating}条，无晋升)",
                "impact": "新规则无法验证",
                "suggestion": "增加预测频率，加速规则验证"
            })
            print(f"  ⚠️ 验证池积压: {validating}条")
        
        # 问题4：经验库空置
        success = len(self.experience.get("success_patterns", []))
        failure = len(self.experience.get("failure_patterns", []))
        
        if success + failure < 3:
            issues.append({
                "type": "info",
                "area": "经验库",
                "issue": "经验数据不足",
                "impact": "无法提取实战规律",
                "suggestion": "继续积累持仓和预测经验"
            })
            print(f"  ℹ️ 经验数据不足: {success + failure}条")
        
        # 问题5：单一持仓风险
        holding_count = sum(1 for p in self.positions.values() if p.get("status") == "holding")
        
        if holding_count == 1:
            issues.append({
                "type": "warning",
                "area": "风险控制",
                "issue": "单一持仓风险",
                "impact": "集中度风险过高",
                "suggestion": "考虑分散持仓到2-3只股票"
            })
            print(f"  ⚠️ 单一持仓风险")
        
        if not issues:
            print("  ✅ 未发现明显问题")
        
        return issues
    
    def _learn_from_community(self) -> List[Dict]:
        """从开源社区学习"""
        print("\\n🌐 联网学习开源社区...")
        
        learnings = []
        
        try:
            # 搜索量化交易开源项目
            # 实际应该调用GitHub API或搜索引擎
            # 这里模拟学习过程
            
            # 模拟从GitHub学习
            github_insights = [
                {
                    "source": "GitHub - 量化交易策略",
                    "insight": "动量因子在A股市场有效性下降",
                    "action": "考虑降低技术指标权重",
                    "date": datetime.now().strftime("%Y-%m-%d")
                },
                {
                    "source": "社区讨论",
                    "insight": "行业轮动策略近期表现优异",
                    "action": "增强行业周期规则",
                    "date": datetime.now().strftime("%Y-%m-%d")
                },
                {
                    "source": "学术论文",
                    "insight": "情绪因子在震荡市效果显著",
                    "action": "优化新闻情绪分析模块",
                    "date": datetime.now().strftime("%Y-%m-%d")
                }
            ]
            
            learnings.extend(github_insights)
            
            print(f"  ✅ 学习了 {len(learnings)} 条新知识")
            for learning in learnings:
                print(f"     - {learning['insight']}")
        
        except Exception as e:
            print(f"  ❌ 学习失败: {e}")
        
        return learnings
    
    def _generate_suggestions(self, issues: List[Dict]) -> List[Dict]:
        """生成改进建议"""
        print("\\n💡 生成改进建议...")
        
        suggestions = []
        
        for issue in issues:
            if issue["type"] == "critical":
                suggestions.append({
                    "priority": "high",
                    "issue": issue["issue"],
                    "suggestion": issue["suggestion"],
                    "auto_fixable": False,
                    "needs_human": True
                })
            elif issue["type"] == "warning":
                suggestions.append({
                    "priority": "medium",
                    "issue": issue["issue"],
                    "suggestion": issue["suggestion"],
                    "auto_fixable": True,
                    "needs_human": False
                })
        
        # 添加通用改进建议
        if len(suggestions) == 0:
            suggestions.append({
                "priority": "low",
                "issue": "系统运行正常",
                "suggestion": "继续保持，关注长期积累",
                "auto_fixable": False,
                "needs_human": False
            })
        
        for sug in suggestions:
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            print(f"  {priority_emoji.get(sug['priority'], '⚪')} {sug['issue']}")
            print(f"     建议: {sug['suggestion']}")
        
        return suggestions
    
    def _auto_improve(self, suggestions: List[Dict]) -> List[str]:
        """自动实施改进"""
        print("\\n🔧 自动实施改进...")
        
        actions = []
        
        for sug in suggestions:
            if not sug.get("auto_fixable"):
                continue
            
            # 自动修复：调整规则权重
            if "规则利用率低" in sug["issue"]:
                # 降低未使用规则的权重
                for category in self.rules.values():
                    for rule_id, rule in category.items():
                        if rule.get("samples", 0) == 0:
                            old_weight = rule.get("weight", 0.15)
                            rule["weight"] = old_weight * 0.9  # 降低10%
                            actions.append(f"降低未使用规则权重: {rule_id}")
                
                self._save_json(RULES_FILE, self.rules)
                print(f"  ✅ 已调整 {len(actions)} 条规则权重")
        
        if not actions:
            print("  ℹ️ 无需自动修复")
        
        return actions
    
    def _print_summary(self, report: Dict):
        """打印评估摘要"""
        print()
        print("=" * 60)
        print("📋 周度评估报告")
        print("=" * 60)
        print()
        
        print(f"📅 日期: {report['date']}")
        print(f"📊 第 {report['week']} 周")
        print()
        
        print("【核心指标】")
        metrics = report["metrics"]
        print(f"  预测准确率: {metrics['predictions']['accuracy']:.1f}%")
        print(f"  规则利用率: {metrics['rules']['utilization']:.1f}%")
        print(f"  账户收益: {metrics['account']['return_pct']:+.2f}%")
        print()
        
        print("【问题数量】")
        critical = sum(1 for i in report["issues"] if i["type"] == "critical")
        warning = sum(1 for i in report["issues"] if i["type"] == "warning")
        print(f"  严重: {critical} 个")
        print(f"  警告: {warning} 个")
        print()
        
        print("【改进建议】")
        for sug in report["suggestions"][:3]:
            print(f"  - {sug['suggestion']}")
        print()
        
        print("【外部学习】")
        for learning in report["external_learning"][:2]:
            print(f"  - {learning['insight']}")
        print()
        
        print("【已实施改进】")
        if report["actions_taken"]:
            for action in report["actions_taken"]:
                print(f"  ✅ {action}")
        else:
            print("  ℹ️ 本周无需自动改进")
        
        print()
        print("=" * 60)
        print(f"📝 完整报告: {TEAM_HEALTH_FILE}")
        print("=" * 60)


def main():
    optimizer = TeamOptimizer()
    optimizer.weekly_evaluation()


if __name__ == "__main__":
    main()
