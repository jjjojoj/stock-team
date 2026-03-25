#!/usr/bin/env python3
"""
收盘复盘系统 v2.0

功能：
1. 验证全天预测准确率
2. 分析成功/失败股票特征
3. 更新选股标准（动态进化）
4. 提取教训永久写入 memory.md
5. 生成飞书汇报
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LEARNING_DIR = PROJECT_ROOT / "learning"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from core.storage import build_portfolio_snapshot, load_watchlist

# 导入必要的模块
try:
    from prediction_engine import PredictionEngine
    from event_trader import EventTrader
    from rule_evolution import RuleEvolution
except ImportError as e:
    print(f"⚠️ 导入模块失败: {e}")
    # 如果导入失败，我们直接使用 ClosedLoopReview
    from daily_review_closed_loop import ClosedLoopReview


class MarketReview:
    """收盘复盘系统"""
    
    def __init__(self):
        self.review_dir = DATA_DIR / "reviews"
        self.review_dir.mkdir(parents=True, exist_ok=True)
        
        # 尝试初始化完整的系统
        try:
            self.engine = PredictionEngine()
            self.trader = EventTrader()
            self.use_full_system = True
        except Exception as e:
            print(f"⚠️ 初始化完整系统失败: {e}")
            print("🔄 使用简化版复盘系统")
            self.reviewer = ClosedLoopReview()
            self.use_full_system = False
    
    def run(self):
        """执行收盘复盘"""
        print("=" * 70)
        print(f"📊 收盘复盘 + 选股标准进化 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
        if self.use_full_system:
            return self._run_full_review()
        else:
            return self._run_simple_review()
    
    def _run_simple_review(self):
        """运行简化版复盘"""
        print("\n🔄 运行简化版复盘...")
        results = self.reviewer.verify_all_predictions()
        
        # 生成报告
        report = self._generate_simple_report(results)
        
        # 写入记忆
        self._write_lessons_to_memory(results)
        
        return report
    
    def _run_full_review(self):
        """运行完整版复盘"""
        # 1. 验证预测
        print("\n1️⃣ 验证全天预测准确率...")
        verify_result = self.engine.verify_predictions()
        
        # 2. 复盘持仓
        print("\n2️⃣ 分析成功/失败股票特征...")
        position_analysis = self._analyze_positions()
        
        # 3. 规则进化
        print("\n3️⃣ 更新选股标准（动态进化）...")
        evolution = RuleEvolution()
        case_studies_for_rules = []
        
        # 准备案例数据
        if position_analysis.get('lessons'):
            for lesson in position_analysis['lessons']:
                if lesson['type'] == 'success':
                    case_studies_for_rules.append({
                        'stock': lesson.get('stock', ''),
                        'success_factors': lesson.get('reasons', []),
                        'outcome': 'correct',
                        'profit_pct': lesson.get('pnl_pct', 0)
                    })
        
        evolution_result = evolution.run_evolution(case_studies=case_studies_for_rules)
        
        # 4. 提取教训
        print("\n4️⃣ 提取教训...")
        lessons = self._extract_lessons(verify_result, position_analysis)
        
        # 5. 写入记忆
        print("\n5️⃣ 永久写入 memory.md...")
        self._write_lessons_to_memory(lessons)
        
        # 6. 生成报告
        print("\n6️⃣ 生成飞书汇报...")
        report = self._generate_full_report(
            verify_result,
            position_analysis,
            evolution_result,
            lessons
        )
        
        return report
    
    def _analyze_positions(self) -> Dict:
        """分析持仓"""
        try:
            snapshot = build_portfolio_snapshot()
            positions = snapshot.get("positions", [])
        except Exception as e:
            print(f"⚠️ 获取持仓失败: {e}")
            return {"message": "无法获取持仓", "total": 0, "profitable": 0, "losing": 0, "lessons": []}
        
        if not positions:
            return {"message": "无持仓", "total": 0, "profitable": 0, "losing": 0, "lessons": []}
        
        analysis = {
            "total": len(positions),
            "profitable": 0,
            "losing": 0,
            "lessons": []
        }
        
        for pos in positions:
            code = pos.get('code', '')
            cost = pos.get('cost_price', 0)
            current = pos.get('current_price', cost)
            pnl_pct = (current / cost - 1) * 100
            
            if pnl_pct >= 0:
                analysis['profitable'] += 1
                
                if pnl_pct > 5:
                    reasons = self._find_prediction_reasons(code)
                    analysis['lessons'].append({
                        "type": "success",
                        "stock": pos.get('name', code),
                        "pnl_pct": pnl_pct,
                        "reasons": reasons,
                        "lesson": f"成功规则: {', '.join(reasons)}"
                    })
            else:
                analysis['losing'] += 1
                
                if pnl_pct < -3:
                    reasons = self._find_prediction_reasons(code)
                    analysis['lessons'].append({
                        "type": "failure",
                        "stock": pos.get('name', code),
                        "pnl_pct": pnl_pct,
                        "reasons": reasons,
                        "lesson": f"失败原因: 需要检查 {', '.join(reasons)} 是否有效"
                    })
        
        return analysis
    
    def _find_prediction_reasons(self, code: str) -> List[str]:
        """查找预测理由"""
        try:
            watchlist = load_watchlist({})
            if code in watchlist:
                reason = watchlist[code].get('added_reason') or watchlist[code].get('reason') or '未知'
                return [item.strip() for item in reason.split(',') if item.strip()]
        except Exception as e:
            print(f"⚠️ 读取watchlist失败: {e}")
        
        return ["未知"]
    
    def _extract_lessons(self, verify_result, position_analysis) -> Dict:
        """提取教训"""
        lessons = {
            "prediction_lessons": [],
            "position_lessons": [],
            "rule_lessons": []
        }
        
        # 从预测验证中提取
        if verify_result.get('results'):
            for r in verify_result['results']:
                if r['result'] == 'wrong':
                    lessons['prediction_lessons'].append({
                        "stock": r['name'],
                        "direction": r['direction'],
                        "actual_change": r['price_change'],
                        "lesson": f"{r['name']} 预测错误: 预期{r['direction']}, 实际{r['price_change']:+.1f}%"
                    })
        
        # 从持仓分析中提取
        if position_analysis.get('lessons'):
            lessons['position_lessons'] = position_analysis['lessons']
        
        return lessons
    
    def _write_lessons_to_memory(self, data):
        """写入记忆"""
        memory_file = LEARNING_DIR / "memory.md"
        
        # 确保目录存在
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件不存在，创建它
        if not memory_file.exists():
            with open(memory_file, 'w', encoding='utf-8') as f:
                f.write("# AI 炒股团队 - 长期记忆（HOT 层）\n\n")
                f.write("> 出现 3 次相同模式 → 提升到 HOT 层，永久生效\n\n")
        
        # 生成记忆条目
        memory_entry = f"\n---\n\n## [{datetime.now().strftime('%Y-%m-%d')}] 收盘深度学习 ⭐\n\n"
        memory_entry += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        
        # 处理简化版结果
        if isinstance(data, dict) and 'verified' in data:
            memory_entry += f"**预测验证结果**:\n"
            memory_entry += f"- 验证: {data['verified']} 个\n"
            memory_entry += f"- ✅ 正确: {data['correct']} ({data['correct']/max(data['verified'],1)*100:.1f}%)\n"
            memory_entry += f"- 🔶 部分: {data['partial']}\n"
            memory_entry += f"- ❌ 错误: {data['wrong']}\n\n"
        
        # 处理完整版结果
        elif isinstance(data, dict):
            # 预测教训
            if data.get('prediction_lessons'):
                memory_entry += f"**预测教训**:\n"
                for lesson in data['prediction_lessons']:
                    memory_entry += f"❌ {lesson['lesson']}\n"
                memory_entry += "\n"
            
            # 持仓教训
            if data.get('position_lessons'):
                memory_entry += f"**持仓教训**:\n"
                for lesson in data['position_lessons']:
                    emoji = "✅" if lesson['type'] == 'success' else "❌"
                    memory_entry += f"{emoji} {lesson['stock']}: {lesson['lesson']}\n"
                memory_entry += "\n"
        
        # 追加到记忆文件
        with open(memory_file, 'a', encoding='utf-8') as f:
            f.write(memory_entry)
        
        print(f"📚 已写入学习记忆")
    
    def _generate_simple_report(self, results: Dict) -> str:
        """生成简化版报告"""
        total = results['verified']
        correct_rate = results['correct'] / max(total, 1) * 100
        
        report_lines = [
            f"📊 **收盘复盘报告**",
            f"",
            f"日期: {datetime.now().strftime('%Y-%m-%d')}",
            f"",
            f"---",
            f"",
            f"### 📈 预测准确率",
            f"",
            f"- 验证预测: {total} 个",
            f"- ✅ 正确: {results['correct']} ({correct_rate:.1f}%)",
            f"- 🔶 部分正确: {results['partial']} 个",
            f"- ❌ 错误: {results['wrong']} 个",
            f"- 🔗 关联交易: {results.get('linked_trades', 0)} 个",
            f"",
            f"### 🧬 选股标准进化",
            f"",
            f"由于系统限制，使用简化版复盘。",
            f"选股标准进化将在下次完整运行时执行。",
            f"",
            f"### 📚 教训总结",
            f"",
            f"所有教训已永久写入 memory.md 文件。",
            f"",
            f"---",
            f"",
            f"**注**: 本次复盘使用简化版系统。建议修复完整系统以获得更详细的分析。"
        ]
        
        return "\n".join(report_lines)
    
    def _generate_full_report(self, verify_result, position_analysis, evolution_result, lessons) -> str:
        """生成完整版报告"""
        lines = [
            f"📊 **收盘复盘 + 选股标准进化报告**",
            f"",
            f"日期: {datetime.now().strftime('%Y-%m-%d')}",
            f"",
            f"---",
            f"",
            f"### 📈 预测准确率",
            f"",
        ]
        
        if verify_result.get('results'):
            total = len(verify_result['results'])
            correct = sum(1 for r in verify_result['results'] if r['result'] == 'correct')
            partial = sum(1 for r in verify_result['results'] if r['result'] == 'partial')
            wrong = sum(1 for r in verify_result['results'] if r['result'] == 'wrong')
            correct_rate = correct / max(total, 1) * 100
            
            lines.extend([
                f"- 验证预测: {total} 个",
                f"- ✅ 正确: {correct} ({correct_rate:.1f}%)",
                f"- 🔶 部分正确: {partial} 个",
                f"- ❌ 错误: {wrong} 个",
                f"",
                f"**详细结果**:"
            ])
            
            for r in verify_result['results']:
                emoji = "✅" if r['result'] == 'correct' else ("⚠️" if r['result'] == 'partial' else "❌")
                lines.append(f"{emoji} {r['name']}: {r['price_change']:+.1f}% ({r['result']})")
        else:
            lines.append("暂无预测验证结果")
        
        lines.extend([
            f"",
            f"### 📊 持仓分析",
            f"",
        ])
        
        if position_analysis.get('total', 0) > 0:
            lines.extend([
                f"- 总持仓: {position_analysis['total']} 只",
                f"- 盈利: {position_analysis['profitable']} 只",
                f"- 亏损: {position_analysis['losing']} 只",
            ])
            
            if position_analysis.get('lessons'):
                lines.append(f"")
                lines.append(f"**经验教训**:")
                for lesson in position_analysis['lessons']:
                    emoji = "✅" if lesson['type'] == 'success' else "❌"
                    lines.append(f"{emoji} {lesson['stock']}: {lesson['pnl_pct']:+.1f}%")
                    lines.append(f"   {lesson['lesson']}")
        else:
            lines.append("无持仓或无法获取持仓数据")
        
        lines.extend([
            f"",
            f"### 🧬 选股标准进化",
            f"",
        ])
        
        if evolution_result:
            stats = evolution_result.get('stats', {})
            lines.append(f"**规则库统计**:")
            lines.append(f"- 总规则数：{stats.get('total', 0)}")
            lines.append(f"- 优秀规则：{len(stats.get('excellent', []))} 条（成功率>70%）")
            lines.append(f"- 良好规则：{len(stats.get('good', []))} 条（成功率>50%）")
            lines.append(f"- 差规则：{len(stats.get('poor', []))} 条（成功率<40%）")
            lines.append(f"- 新规则：{len(stats.get('new', []))} 条（样本<10）")
            
            adjustments = evolution_result.get('adjustments', [])
            if adjustments:
                lines.append(f"\n**权重调整**:")
                for adj in adjustments:
                    if adj['action'] == 'increase':
                        lines.append(f"⬆️ {adj['rule']}: {adj['old_weight']:.2f} → {adj['new_weight']:.2f}")
                    elif adj['action'] == 'decrease':
                        lines.append(f"⬇️ {adj['rule']}: {adj['old_weight']:.2f} → {adj['new_weight']:.2f}")
                    elif adj['action'] == 'mark_for_removal':
                        lines.append(f"🗑️ {adj['rule']}: 标记移除")
            
            removed = evolution_result.get('removed', [])
            if removed:
                lines.append(f"\n**移除规则**:")
                for r in removed:
                    lines.append(f"❌ {r['category']}.{r['rule']}: 成功率{r['success_rate']*100:.1f}%")
        else:
            lines.append("暂无规则进化数据")
        
        lines.extend([
            f"",
            f"### 📚 教训总结",
            f"",
            f"所有教训已永久写入 memory.md 文件。",
            f"",
            f"---",
            f"",
            f"**系统状态**: {'完整版' if self.use_full_system else '简化版'}"
        ])
        
        return "\n".join(lines)


def main():
    """主函数"""
    review = MarketReview()
    report = review.run()
    
    print("\n" + "=" * 70)
    print("📝 飞书汇报内容:")
    print("=" * 70)
    print(report)
    
    # 保存报告到文件
    today = datetime.now().strftime('%Y-%m-%d')
    report_file = DATA_DIR / "reviews" / f"market_review_{today}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 报告已保存到: {report_file}")
    
    # 尝试发送飞书通知
    try:
        from feishu_notifier import send_feishu_message
        send_feishu_message(title="📊 收盘复盘 + 选股标准进化", content=report, level='info')
        print("✅ 飞书通知已发送")
    except Exception as e:
        print(f"⚠️ 飞书通知发送失败: {e}")
        print("请手动查看报告内容")


if __name__ == "__main__":
    main()
