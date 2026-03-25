#!/usr/bin/env python3
"""
每日绩效汇报 - 每个成员汇报当日工作，接收反馈
营造真实工作压力和竞争氛围
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List

# 项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from performance_tracker import PerformanceTracker

# 成员列表
MEMBERS = ["CIO", "Quant", "Trader", "Risk", "Research", "Learning"]

# 各成员 KPI 目标
KPI_TARGETS = {
    "CIO": {"组合收益率": 0.05, "最大回撤": -0.15, "夏普比率": 1.5},
    "Quant": {"选股胜率": 0.60, "推荐收益": 0.08, "因子 IC": 0.05},
    "Trader": {"成交率": 0.95, "滑点控制": 0.005, "择时胜率": 0.55},
    "Risk": {"预警准确率": 0.80, "止损执行": 1.0, "漏报次数": 0},
    "Research": {"信息条数": 10, "预测准确率": 0.65, "研报采用": 0.40},
    "Learning": {"学习案例": 5, "迭代成功": 0.50, "贡献评分": 70},
}


class DailyPerformanceReport:
    """每日绩效汇报系统"""
    
    def __init__(self):
        self.tracker = PerformanceTracker()
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.log_path = os.path.join(PROJECT_ROOT, "logs", "daily_performance")
        os.makedirs(self.log_path, exist_ok=True)
    
    def generate_member_report(self, member_name: str) -> Dict:
        """生成单个成员的日报"""
        # 获取实际数据（从各模块收集）
        actual_metrics = self._collect_actual_metrics(member_name)
        
        # 计算绩效
        report = {
            "member": member_name,
            "date": self.date,
            "metrics": {},
            "score": 0,
            "rating": "A",
            "warnings": [],
            "feedback": ""
        }
        
        # 对比 KPI
        targets = KPI_TARGETS.get(member_name, {})
        total_score = 0
        
        for metric, target in targets.items():
            actual = actual_metrics.get(metric, 0)
            
            # 计算达成率
            if metric in ["最大回撤", "漏报次数"]:
                # 越小越好的指标
                achievement = target / actual if actual > 0 else 1.0
            else:
                # 越大越好的指标
                achievement = actual / target if target > 0 else 0
            
            # 记录绩效
            status = self.tracker.record_performance(
                member_name, metric, actual, target,
                f"实际：{actual:.4f}, 目标：{target:.4f}"
            )
            
            report["metrics"][metric] = {
                "actual": actual,
                "target": target,
                "achievement": achievement,
                "status": status
            }
            
            # 累计分数
            if status == "S":
                total_score += 25
            elif status == "A":
                total_score += 20
            elif status == "B":
                total_score += 15
            elif status == "C":
                total_score += 10
            else:  # D
                total_score += 5
                report["warnings"].append(f"{metric} 表现 D 级")
        
        # 计算总分和评级
        report["score"] = total_score
        report["rating"] = self._calculate_rating(total_score, len(targets))
        
        # 生成反馈
        report["feedback"] = self._generate_feedback(member_name, report)
        
        return report
    
    def _collect_actual_metrics(self, member_name: str) -> Dict:
        """收集成员的实际工作数据"""
        # 这里从各模块读取实际数据
        # 目前返回模拟数据（后续对接真实数据）
        
        if member_name == "CIO":
            return {
                "组合收益率": 0.036,  # +3.6%
                "最大回撤": -0.08,     # -8%
                "夏普比率": 1.2
            }
        elif member_name == "Quant":
            return {
                "选股胜率": 0.65,      # 65%
                "推荐收益": 0.082,     # +8.2%
                "因子 IC": 0.048
            }
        elif member_name == "Trader":
            return {
                "成交率": 0.98,        # 98%
                "滑点控制": 0.003,     # 0.3%
                "择时胜率": 0.52
            }
        elif member_name == "Risk":
            return {
                "预警准确率": 0.75,    # 75%
                "止损执行": 1.0,       # 100%
                "漏报次数": 1
            }
        elif member_name == "Research":
            return {
                "信息条数": 12,         # 12 条
                "预测准确率": 0.68,    # 68%
                "研报采用": 0.45       # 45%
            }
        elif member_name == "Learning":
            return {
                "学习案例": 6,          # 6 个
                "迭代成功": 0.55,      # 55%
                "贡献评分": 75
            }
        else:
            return {}
    
    def _calculate_rating(self, score: int, max_score: int) -> str:
        """计算评级"""
        percentage = score / (max_score * 25)  # 满分是 25*指标数
        
        if percentage >= 0.9:
            return "S"
        elif percentage >= 0.7:
            return "A"
        elif percentage >= 0.5:
            return "B"
        elif percentage >= 0.3:
            return "C"
        else:
            return "D"
    
    def _generate_feedback(self, member_name: str, report: Dict) -> str:
        """生成个性化反馈"""
        rating = report["rating"]
        warnings = report["warnings"]
        
        if rating == "S":
            feedback = f"🏆 {member_name} 今日表现卓越！继续保持！"
        elif rating == "A":
            feedback = f"✅ {member_name} 表现良好，达成目标。"
        elif rating == "B":
            feedback = f"🟡 {member_name} 表现合格，但有提升空间。"
        elif rating == "C":
            feedback = f"⚠️ {member_name} 表现不佳，需要改进！"
        else:  # D
            feedback = f"🔴 {member_name} 表现危险！立即改进，否则淘汰！"
        
        if warnings:
            feedback += f"\n\n警告项：{', '.join(warnings)}"
        
        return feedback
    
    def generate_daily_report(self) -> str:
        """生成全员日报"""
        reports = []
        
        for member in MEMBERS:
            report = self.generate_member_report(member)
            reports.append(report)
        
        # 按评分排序
        reports.sort(key=lambda x: x["score"], reverse=True)
        
        # 生成格式化报告
        message = f"📊 **每日绩效汇报**\n"
        message += f"日期：{self.date}\n\n"
        
        # 排行榜
        message += "🏆 **绩效排行榜**\n\n"
        for i, report in enumerate(reports, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            emoji = "🟢" if report["rating"] in ["S", "A"] else "🟡" if report["rating"] == "B" else "🔴"
            message += f"{medal} {emoji} **{report['member']}**: {report['score']}分 "
            message += f"({report['rating']}级)\n"
        
        message += "\n---\n\n"
        
        # 详细汇报
        message += "📋 **详细汇报**\n\n"
        for report in reports:
            message += f"**{report['member']}** ({report['rating']}级)\n"
            message += f"得分：{report['score']} | 反馈：{report['feedback']}\n\n"
            
            # 关键指标
            message += "关键指标：\n"
            for metric, data in report['metrics'].items():
                status_emoji = "✅" if data['status'] in ['S', 'A'] else "⚠️" if data['status'] == 'B' else "❌"
                message += f"  {status_emoji} {metric}: {data['actual']:.4f} "
                message += f"(目标：{data['target']:.4f}, 达成：{data['achievement']:.1%})\n"
            
            message += "\n---\n\n"
        
        # 末位警告
        last_place = reports[-1]
        if last_place["rating"] in ["C", "D"]:
            message += f"🔴 **末位警告**：{last_place['member']} 连续末位将被淘汰！\n\n"
        
        # 淘汰预警
        message += "💀 **淘汰机制提醒**：\n"
        message += "- 连续 3 月 D 级 → 淘汰\n"
        message += "- 累计 2 张红牌 → 淘汰\n"
        message += "- 单次损失>15% → 立即淘汰\n\n"
        
        message += "---\n"
        message += "*要么出众，要么出局* 💀"
        
        # 保存报告
        report_file = os.path.join(self.log_path, f"{self.date}.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(message)
        
        # 保存为飞书通知格式
        notify_file = os.path.join(PROJECT_ROOT, "logs", "feishu_performance.txt")
        with open(notify_file, 'w', encoding='utf-8') as f:
            f.write(message)
        
        return message


def main():
    """生成今日绩效汇报"""
    reporter = DailyPerformanceReport()
    
    print("=" * 60)
    print("📊 每日绩效汇报系统")
    print("=" * 60)
    
    message = reporter.generate_daily_report()

    print("\n" + message)

    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
        from feishu_notifier import send_feishu_message

        clean_message = message.replace("**", "")
        send_feishu_message(
            title=f"📊 每日绩效汇报 - {reporter.date}",
            content=clean_message,
            level="info",
        )
        print("✅ 飞书通知已发送")
    except Exception as exc:
        print(f"⚠️ 飞书通知发送失败: {exc}")

    print("\n✅ 日报已生成并保存")
    print(f"📁 文件：{reporter.log_path}/{reporter.date}.md")
    print(f"📢 飞书通知：{PROJECT_ROOT}/logs/feishu_performance.txt")


if __name__ == "__main__":
    main()
