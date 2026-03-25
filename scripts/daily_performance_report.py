#!/usr/bin/env python3
"""
每日绩效汇报 - 每个成员汇报当日工作，接收反馈
营造真实工作压力和竞争氛围
"""

import os
import sys
import json
import math
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List

# 项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from performance_tracker import PerformanceTracker
from core.predictions import normalize_prediction_collection, prediction_result_status
from core.storage import build_portfolio_snapshot, load_json, load_rule_state

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


def _safe_parse_datetime(value: str) -> datetime:
    """Parse mixed timestamp formats from historical logs."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


class DailyPerformanceReport:
    """每日绩效汇报系统"""
    
    def __init__(self):
        self.tracker = PerformanceTracker()
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.log_path = os.path.join(PROJECT_ROOT, "logs", "daily_performance")
        os.makedirs(self.log_path, exist_ok=True)
        self.db_path = os.path.join(PROJECT_ROOT, "database", "stock_team.db")
        self.predictions_path = os.path.join(PROJECT_ROOT, "data", "predictions.json")
        self.trade_history_path = os.path.join(PROJECT_ROOT, "data", "trade_history.json")
        self.accuracy_path = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
        self.daily_search_dir = os.path.join(PROJECT_ROOT, "data", "daily_search")
        self.learning_log_path = os.path.join(PROJECT_ROOT, "learning", "daily_learning_log.json")
        self.book_progress_path = os.path.join(PROJECT_ROOT, "learning", "book_learning_progress.json")
        self.window_start = datetime.now() - timedelta(days=30)
    
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
        collectors = {
            "CIO": self._collect_cio_metrics,
            "Quant": self._collect_quant_metrics,
            "Trader": self._collect_trader_metrics,
            "Risk": self._collect_risk_metrics,
            "Research": self._collect_research_metrics,
            "Learning": self._collect_learning_metrics,
        }
        collector = collectors.get(member_name)
        return collector() if collector else {}

    def _query_rows(self, sql: str, params=()) -> List[sqlite3.Row]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return rows
        except sqlite3.Error:
            return []

    def _query_value(self, sql: str, params=(), default: float = 0.0) -> float:
        rows = self._query_rows(sql, params)
        if not rows:
            return default
        first_row = rows[0]
        if isinstance(first_row, sqlite3.Row):
            values = list(first_row)
            return float(values[0] if values and values[0] is not None else default)
        return default

    def _load_predictions(self) -> List[Dict]:
        predictions = normalize_prediction_collection(
            load_json(self.predictions_path, {"active": {}, "history": []})
        )
        return list(predictions.get("history", [])) + list(predictions.get("active", {}).values())

    def _verified_predictions(self) -> List[Dict]:
        return [
            prediction for prediction in self._load_predictions()
            if prediction_result_status(prediction) != "pending"
        ]

    def _prediction_score(self, prediction: Dict) -> float:
        status = prediction_result_status(prediction)
        if status == "correct":
            return 1.0
        if status == "partial":
            return 0.5
        if status == "wrong":
            return 0.0
        return 0.0

    def _aligned_prediction_return(self, prediction: Dict) -> float:
        result = prediction.get("result") or {}
        price_change = float(result.get("price_change_pct", 0.0) or 0.0) / 100
        direction = prediction.get("direction", "neutral")
        if direction == "down":
            return -price_change
        if direction == "neutral":
            return -abs(price_change)
        return price_change

    def _pearson(self, xs: List[float], ys: List[float]) -> float:
        if len(xs) < 2 or len(xs) != len(ys):
            return 0.0
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        if denominator_x == 0 or denominator_y == 0:
            return 0.0
        return numerator / (denominator_x * denominator_y)

    def _latest_daily_search_count(self) -> int:
        if not os.path.isdir(self.daily_search_dir):
            return 0
        json_files = sorted(
            filename for filename in os.listdir(self.daily_search_dir)
            if filename.endswith(".json") and filename[:8].isdigit()
        )
        if not json_files:
            return 0
        payload = load_json(os.path.join(self.daily_search_dir, json_files[-1]), {})
        total = 0
        for section_name in ("market_overview", "holdings", "watchlist"):
            section = payload.get(section_name, {})
            if isinstance(section, dict):
                for items in section.values():
                    if isinstance(items, list):
                        total += len(items)
                    elif items:
                        total += 1
        return total

    def _load_trade_history(self) -> List[Dict]:
        history = load_json(self.trade_history_path, [])
        return history if isinstance(history, list) else []

    def _load_learning_logs(self) -> List[Dict]:
        logs = load_json(self.learning_log_path, [])
        return logs if isinstance(logs, list) else []

    def _normalize_drawdown(self, value: float) -> float:
        if value is None:
            return 0.0
        drawdown = float(value or 0.0)
        if abs(drawdown) > 1:
            drawdown /= 100
        return -abs(drawdown)

    def _collect_cio_metrics(self) -> Dict:
        snapshot = build_portfolio_snapshot()
        account_rows = self._query_rows(
            """
            SELECT daily_profit_pct
            FROM account
            WHERE daily_profit_pct IS NOT NULL
            ORDER BY date DESC
            LIMIT 30
            """
        )
        returns = [float(row["daily_profit_pct"] or 0.0) / 100 for row in account_rows]
        sharpe = 0.0
        if len(returns) >= 2:
            mean_return = sum(returns) / len(returns)
            variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
            std = math.sqrt(variance)
            if std > 0:
                sharpe = mean_return / std * math.sqrt(252)

        account = snapshot.get("account", {})
        return {
            "组合收益率": float(snapshot.get("total_profit_pct", 0.0) or 0.0) / 100,
            "最大回撤": self._normalize_drawdown(account.get("max_drawdown", 0.0)),
            "夏普比率": sharpe,
        }

    def _collect_quant_metrics(self) -> Dict:
        predictions = self._verified_predictions()
        if predictions:
            confidence_values = [float(pred.get("confidence", 0.0) or 0.0) / 100 for pred in predictions]
            outcome_values = [self._prediction_score(pred) for pred in predictions]
            win_rate = sum(outcome_values) / len(outcome_values)
            recommendation_return = sum(self._aligned_prediction_return(pred) for pred in predictions) / len(predictions)
            factor_ic = self._pearson(confidence_values, outcome_values)
        else:
            win_rate = 0.0
            recommendation_return = 0.0
            factor_ic = 0.0

        return {
            "选股胜率": win_rate,
            "推荐收益": recommendation_return,
            "因子 IC": factor_ic,
        }

    def _collect_trader_metrics(self) -> Dict:
        approved_proposals = self._query_value(
            "SELECT COUNT(*) FROM proposals WHERE status IN ('approved', 'executed')"
        )
        executed_trades = self._query_value("SELECT COUNT(*) FROM trades")
        trade_rows = self._query_rows("SELECT amount, commission FROM trades WHERE amount IS NOT NULL AND amount > 0")
        sell_trades = [
            trade for trade in self._load_trade_history()
            if str(trade.get("type") or trade.get("action") or "").lower() == "sell"
        ]

        execution_rate = min(1.0, executed_trades / approved_proposals) if approved_proposals else 0.0
        friction_samples = [
            float(row["commission"] or 0.0) / float(row["amount"] or 1.0)
            for row in trade_rows
            if float(row["amount"] or 0.0) > 0
        ]
        timing_win_rate = (
            sum(1 for trade in sell_trades if float(trade.get("pnl_pct", 0.0) or 0.0) > 0) / len(sell_trades)
            if sell_trades else 0.0
        )

        return {
            "成交率": execution_rate,
            "滑点控制": sum(friction_samples) / len(friction_samples) if friction_samples else 0.0,
            "择时胜率": timing_win_rate,
        }

    def _collect_risk_metrics(self) -> Dict:
        sell_trades = [
            trade for trade in self._load_trade_history()
            if str(trade.get("type") or trade.get("action") or "").lower() == "sell"
        ]
        risk_keywords = ("止损", "风险", "减仓", "回避")
        risk_sells = [
            trade for trade in sell_trades
            if any(keyword in str(trade.get("reason", "")) for keyword in risk_keywords)
        ]
        losing_sells = [
            trade for trade in sell_trades
            if float(trade.get("pnl_pct", 0.0) or 0.0) < 0
        ]

        warning_accuracy = (
            sum(1 for trade in risk_sells if float(trade.get("pnl_pct", 0.0) or 0.0) < 0) / len(risk_sells)
            if risk_sells else 0.0
        )
        stop_loss_execution = (
            sum(
                1 for trade in losing_sells
                if any(keyword in str(trade.get("reason", "")) for keyword in risk_keywords)
            ) / len(losing_sells)
            if losing_sells else 0.0
        )
        missed_alerts = sum(
            1 for trade in losing_sells
            if not any(keyword in str(trade.get("reason", "")) for keyword in risk_keywords)
        )

        return {
            "预警准确率": warning_accuracy,
            "止损执行": stop_loss_execution,
            "漏报次数": missed_alerts,
        }

    def _collect_research_metrics(self) -> Dict:
        proposals = self._query_rows(
            """
            SELECT status
            FROM proposals
            WHERE source_agent = 'Research'
            """
        )
        verified_predictions = self._verified_predictions()
        accuracy = (
            sum(self._prediction_score(prediction) for prediction in verified_predictions) / len(verified_predictions)
            if verified_predictions else 0.0
        )
        adopted_reports = sum(1 for row in proposals if row["status"] in {"approved", "executed"})

        return {
            "信息条数": self._latest_daily_search_count(),
            "预测准确率": accuracy,
            "研报采用": (adopted_reports / len(proposals)) if proposals else 0.0,
        }

    def _collect_learning_metrics(self) -> Dict:
        learning_logs = self._load_learning_logs()
        recent_learning_logs = [
            item for item in learning_logs
            if item.get("date") and _safe_parse_datetime(item["date"]) >= self.window_start
        ]
        rules, validation_pool, rejected_rules, _ = load_rule_state({}, {}, {})
        active_rules = [
            rule
            for category_rules in rules.values()
            for rule in category_rules.values()
        ]
        validated_rules = [
            rule for rule in active_rules
            if int(rule.get("samples", 0) or 0) >= 5 and float(rule.get("success_rate", 0.0) or 0.0) >= 0.5
        ]
        book_progress = load_json(self.book_progress_path, {})
        books_completed = book_progress.get("books_completed", [])
        books_completed_count = len(books_completed) if isinstance(books_completed, list) else int(bool(books_completed))
        contribution_score = min(
            100,
            books_completed_count * 20 + len(recent_learning_logs) * 3 + len(active_rules),
        )

        return {
            "学习案例": len(recent_learning_logs),
            "迭代成功": (
                len(validated_rules) / (len(validated_rules) + len(rejected_rules))
                if (len(validated_rules) + len(rejected_rules)) else 0.0
            ),
            "贡献评分": contribution_score,
        }
    
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
        message += "口径：当前资产快照 + 累计闭环预测/交易/学习数据\n\n"
        
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
