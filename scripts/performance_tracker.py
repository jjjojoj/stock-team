#!/usr/bin/env python3
"""
绩效追踪系统 - 记录每个成员的 KPI 和表现
用于末位淘汰和绩效评级
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 数据库路径
DB_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/database/performance.db")

class PerformanceTracker:
    """绩效追踪器"""
    
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 成员绩效表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS member_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT NOT NULL,
                date TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                target_value REAL NOT NULL,
                status TEXT NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 警告记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT NOT NULL,
                warning_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                level TEXT NOT NULL,
                date TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 淘汰记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS eliminations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                trigger_condition TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def record_performance(self, member_name: str, metric_name: str, 
                          value: float, target: float, note: str = ""):
        """记录绩效数据"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 计算状态
        if value >= target * 1.2:
            status = "S"
        elif value >= target:
            status = "A"
        elif value >= target * 0.8:
            status = "B"
        elif value >= target * 0.6:
            status = "C"
        else:
            status = "D"
        
        cursor.execute('''
            INSERT INTO member_performance 
            (member_name, date, metric_name, metric_value, target_value, status, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            member_name,
            datetime.now().strftime("%Y-%m-%d"),
            metric_name,
            value,
            target,
            status,
            note
        ))
        
        conn.commit()
        conn.close()
        
        # 检查是否需要警告
        self._check_warning(member_name, status, metric_name, value, target)
        
        return status
    
    def _check_warning(self, member_name: str, status: str, 
                       metric_name: str, value: float, target: float):
        """检查是否需要发出警告"""
        if status in ["C", "D"]:
            # 检查连续表现
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 获取最近 7 天的记录
            cursor.execute('''
                SELECT status, date FROM member_performance
                WHERE member_name = ? AND metric_name = ?
                ORDER BY date DESC LIMIT 7
            ''', (member_name, metric_name))
            
            records = cursor.fetchall()
            conn.close()
            
            # 连续 3 天 D 级 → 严重警告
            if len(records) >= 3 and all(r[0] == "D" for r in records[:3]):
                self.issue_warning(
                    member_name, 
                    "performance",
                    f"连续 3 天{metric_name}表现 D 级（{value:.2f} < {target:.2f}）",
                    "red"
                )
            # 连续 2 天 C 级 → 警告
            elif len(records) >= 2 and all(r[0] == "C" for r in records[:2]):
                self.issue_warning(
                    member_name,
                    "performance",
                    f"连续 2 天{metric_name}表现 C 级（{value:.2f} < {target:.2f}）",
                    "yellow"
                )
    
    def issue_warning(self, member_name: str, warning_type: str, 
                      reason: str, level: str = "yellow"):
        """发出警告"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO warnings 
            (member_name, warning_type, reason, level, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (member_name, warning_type, reason, level, 
              datetime.now().strftime("%Y-%m-%d")))
        
        conn.commit()
        conn.close()
        
        # 发送飞书通知
        self._send_warning_notification(member_name, reason, level)
    
    def _send_warning_notification(self, member_name: str, reason: str, level: str):
        """发送警告通知到飞书"""
        emoji = "🟡" if level == "yellow" else "🔴"
        
        message = f"{emoji} **绩效警告**\n\n"
        message += f"成员：{member_name}\n"
        message += f"原因：{reason}\n"
        message += f"等级：{'警告' if level == 'yellow' else '严重警告'}\n\n"
        
        if level == "red":
            message += "⚠️ **再犯将被淘汰**"
        
        # 保存到通知文件（由外部系统发送）
        notify_file = os.path.expanduser(
            "~/.openclaw/workspace/china-stock-team/logs/performance_warning.txt"
        )
        os.makedirs(os.path.dirname(notify_file), exist_ok=True)
        
        with open(notify_file, 'w', encoding='utf-8') as f:
            f.write(message)
        
        print(f"⚠️ 警告通知已保存：{notify_file}")
    
    def get_member_stats(self, member_name: str, days: int = 30) -> Dict:
        """获取成员统计数据"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 获取绩效记录
        cursor.execute('''
            SELECT metric_name, AVG(metric_value), AVG(target_value), 
                   COUNT(*) as count,
                   SUM(CASE WHEN status='S' THEN 1 ELSE 0 END) as s_count,
                   SUM(CASE WHEN status='D' THEN 1 ELSE 0 END) as d_count
            FROM member_performance
            WHERE member_name = ? 
            AND date >= date('now', ?)
            GROUP BY metric_name
        ''', (member_name, f'-{days} days'))
        
        metrics = cursor.fetchall()
        
        # 获取警告记录
        cursor.execute('''
            SELECT level, COUNT(*) FROM warnings
            WHERE member_name = ? 
            AND date >= date('now', ?)
            AND is_active = 1
            GROUP BY level
        ''', (member_name, f'-{days} days'))
        
        warnings = cursor.fetchall()
        conn.close()
        
        # 计算综合评分
        total_records = sum(m[3] for m in metrics)
        s_count = sum(m[4] for m in metrics)
        d_count = sum(m[5] for m in metrics)
        
        if total_records > 0:
            score = (s_count * 100 - d_count * 50) / total_records
        else:
            score = 0
        
        return {
            "member_name": member_name,
            "period_days": days,
            "metrics": [
                {
                    "name": m[0],
                    "avg_value": m[1],
                    "avg_target": m[2],
                    "count": m[3],
                    "s_count": m[4],
                    "d_count": m[5],
                    "achievement": m[1] / m[2] if m[2] > 0 else 0
                }
                for m in metrics
            ],
            "warnings": {
                "yellow": sum(1 for w in warnings if w[0] == "yellow"),
                "red": sum(1 for w in warnings if w[0] == "red")
            },
            "score": score,
            "rating": self._calculate_rating(score, warnings)
        }
    
    def _calculate_rating(self, score: float, warnings: List) -> str:
        """计算绩效评级"""
        red_count = sum(1 for w in warnings if w[0] == "red")
        yellow_count = sum(1 for w in warnings if w[0] == "yellow")
        
        if red_count >= 2:
            return "D"
        elif red_count >= 1 or yellow_count >= 3:
            return "C"
        elif score >= 90:
            return "S"
        elif score >= 70:
            return "A"
        elif score >= 50:
            return "B"
        else:
            return "C"
    
    def get_ranking(self, days: int = 30) -> List[Dict]:
        """获取绩效排行榜"""
        members = ["CIO", "Quant", "Trader", "Risk", "Research", "Learning"]
        rankings = []
        
        for member in members:
            stats = self.get_member_stats(member, days)
            rankings.append(stats)
        
        # 按评分排序
        rankings.sort(key=lambda x: x["score"], reverse=True)
        
        return rankings
    
    def check_elimination(self, member_name: str) -> Optional[Dict]:
        """检查是否应该淘汰某成员"""
        stats = self.get_member_stats(member_name, days=90)
        
        # 淘汰条件检查
        reasons = []
        
        # 条件 1：连续 3 个月 D 级
        if stats["rating"] == "D":
            reasons.append("连续绩效 D 级")
        
        # 条件 2：红牌≥2
        if stats["warnings"]["red"] >= 2:
            reasons.append("累计 2 张红牌")
        
        # 条件 3：综合评分<30
        if stats["score"] < 30:
            reasons.append("综合评分过低")
        
        if reasons:
            elimination = {
                "member_name": member_name,
                "reasons": reasons,
                "stats": stats,
                "should_eliminate": True
            }
            
            # 记录淘汰决定
            self._record_elimination(elimination)
            
            return elimination
        
        return None
    
    def _record_elimination(self, elimination: Dict):
        """记录淘汰决定"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO eliminations 
            (member_name, reason, trigger_condition, date, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            elimination["member_name"],
            ", ".join(elimination["reasons"]),
            json.dumps(elimination["stats"]),
            datetime.now().strftime("%Y-%m-%d"),
            "pending"
        ))
        
        conn.commit()
        conn.close()
        
        # 发送淘汰预警通知
        self._send_elimination_warning(elimination)
    
    def _send_elimination_warning(self, elimination: Dict):
        """发送淘汰预警通知"""
        message = f"🔴 **淘汰预警**\n\n"
        message += f"成员：{elimination['member_name']}\n"
        message += f"原因：{', '.join(elimination['reasons'])}\n\n"
        message += f"综合评分：{elimination['stats']['score']:.1f}\n"
        message += f"绩效评级：{elimination['stats']['rating']}\n\n"
        message += "⚠️ **进入 7 天观察期，无改善将执行淘汰**"
        
        notify_file = os.path.expanduser(
            "~/.openclaw/workspace/china-stock-team/logs/elimination_warning.txt"
        )
        os.makedirs(os.path.dirname(notify_file), exist_ok=True)
        
        with open(notify_file, 'w', encoding='utf-8') as f:
            f.write(message)
        
        print(f"🔴 淘汰预警已保存：{notify_file}")


def main():
    """测试功能"""
    tracker = PerformanceTracker()
    
    # 测试记录绩效
    print("📊 绩效追踪系统测试")
    print("=" * 50)
    
    # 实战记录
    tracker.record_performance("Quant", "选股胜率", 0.65, 0.60, "今日推荐 10 只，6 只上涨")
    tracker.record_performance("Trader", "成交率", 0.98, 0.95, "执行 20 笔交易，1 笔失败")
    tracker.record_performance("Risk", "预警准确率", 0.75, 0.80, "漏报 1 次风险")
    
    # 获取排行榜
    ranking = tracker.get_ranking(days=7)
    
    print("\n🏆 绩效排行榜（近 7 天）")
    print("=" * 50)
    for i, member in enumerate(ranking, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        print(f"{i}. {emoji} {member['member_name']}: {member['score']:.1f}分 "
              f"({member['rating']}级)")
    
    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
