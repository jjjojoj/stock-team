#!/usr/bin/env python3
"""
股票团队协调器 - 整合5个Agent的协作流程

职责：
1. 早上：研究员提案 → 量化师验证 → 风控官评估 → CIO决策 → 交易员执行
2. 盘中：交易员监控（30分钟）
3. 盘后：复盘 → 经验学习 → 规则晋升
4. 晚上：搜集官 → 学习官

运行时间：
- 早上：09:00
- 盘后：15:30
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# Agent角色
from scripts.ai_predictor import AIPredictor  # 量化师
from scripts.daily_stock_research import StockResearcher  # 研究员
from core.storage import load_watchlist
# 风控官、CIO、交易员 - 功能已分散在现有脚本中


class TeamCoordinator:
    """团队协调器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.positions = self._load_json("config/positions.json", {})
        self.watchlist = load_watchlist({})
        self.portfolio = self._load_json("config/portfolio.json", {})
        
    def _load_config(self):
        config_file = os.path.join(PROJECT_ROOT, "config", "trading_config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_json(self, path, default):
        full_path = os.path.join(PROJECT_ROOT, path)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def morning_workflow(self):
        """早上工作流：09:00"""
        print("=" * 60)
        print("🌅 早上工作流 - 09:00")
        print("=" * 60)
        print()
        
        print("【研究员】提交提案...")
        # 研究员：深度研究股票，生成提案
        researcher = StockResearcher()
        proposals = researcher.research_daily()
        
        if not proposals:
            print("  ⚠️ 无新提案")
            return
        
        print(f"  ✅ 提交了 {len(proposals)} 个提案")
        print()
        
        print("【量化师】验证提案...")
        # 量化师：技术分析 + 预测
        quant = AIPredictor()
        
        for proposal in proposals:
            code = proposal.get("code")
            print(f"  📊 验证: {proposal.get('name')} ({code})")
            
            # 生成预测（包含技术分析）
            prediction = quant.generate_prediction(code, force=True)
            
            if prediction:
                print(f"     方向: {prediction.get('direction')}")
                print(f"     置信度: {prediction.get('confidence')}%")
            else:
                print(f"     ❌ 验证失败")
        
        print()
        print("【风控官】评估风险...")
        # 风控官：检查仓位、止损、风险
        risk_report = self._risk_assessment()
        print(f"  总仓位: {risk_report['total_position']:.1%}")
        print(f"  可用现金: ¥{risk_report['available_cash']:,.0f}")
        print(f"  风险等级: {risk_report['risk_level']}")
        
        if risk_report['risk_level'] == 'High':
            print("  ⚠️ 风险过高，暂停新开仓")
            return
        
        print()
        print("【CIO】最终决策...")
        # CIO：综合决策
        decisions = self._cio_decision(proposals, risk_report)
        
        for decision in decisions:
            print(f"  {decision['action']}: {decision['stock']} ({decision['code']})")
            print(f"     理由: {decision['reason']}")
        
        print()
        print("【交易员】执行交易...")
        # 交易员：执行决策（实际执行由auto_trader.py处理）
        print("  ✅ 决策已记录，等待交易员执行")
        
        print()
        print("=" * 60)
        print("✅ 早上工作流完成")
        print("=" * 60)
    
    def intraday_workflow(self):
        """盘中监控：09:30-15:00（每30分钟）"""
        # 由 intraday_monitor.py 处理
        print("盘中监控由 intraday_monitor.py 处理")
    
    def afternoon_workflow(self):
        """盘后工作流：15:30"""
        print("=" * 60)
        print("🌆 盘后工作流 - 15:30")
        print("=" * 60)
        print()
        
        print("【量化师】复盘验证...")
        # 由 daily_review_closed_loop.py 处理
        print("  复盘由 daily_review_closed_loop.py 处理")
        
        print()
        print("【研究员】经验学习...")
        # 由 experience_learner.py 处理
        print("  经验学习由 experience_learner.py 处理")
        
        print()
        print("【CIO】规则晋升...")
        # 由 rule_promotion.py 处理
        print("  规则晋升由 rule_promotion.py 处理")
        
        print()
        print("=" * 60)
        print("✅ 盘后工作流完成")
        print("=" * 60)
    
    def evening_workflow(self):
        """晚上工作流：20:00-21:00"""
        print("=" * 60)
        print("🌙 晚上工作流 - 20:00")
        print("=" * 60)
        print()
        
        print("【研究员】深度学习...")
        # 由 daily_book_learning.py 处理
        print("  读书学习由 daily_book_learning.py 处理")
        
        print()
        print("【研究员】搜集官工作...")
        # 由 collector_agent.py 处理
        print("  搜集官由 collector_agent.py 处理")
        
        print()
        print("【研究员】学习官工作...")
        # 由 learner_agent.py 处理
        print("  学习官由 learner_agent.py 处理")
        
        print()
        print("=" * 60)
        print("✅ 晚上工作流完成")
        print("=" * 60)
    
    def _risk_assessment(self) -> Dict:
        """风控官：风险评估"""
        total_capital = self.portfolio.get("total_capital", 200000)
        available_cash = self.portfolio.get("available_cash", 0)
        
        # 计算当前仓位
        market_value = 0
        position_count = 0
        
        for code, pos in self.positions.items():
            if pos.get("status") == "holding":
                # 简化：使用成本价估算
                market_value += pos.get("cost_price", 0) * pos.get("shares", 0)
                position_count += 1
        
        total_asset = available_cash + market_value
        total_position = market_value / total_asset if total_asset > 0 else 0
        
        # 风险等级评估
        risk_level = "Low"
        if total_position > 0.7:
            risk_level = "High"
        elif total_position > 0.5:
            risk_level = "Medium"
        
        return {
            "total_capital": total_capital,
            "available_cash": available_cash,
            "market_value": market_value,
            "total_asset": total_asset,
            "total_position": total_position,
            "position_count": position_count,
            "risk_level": risk_level
        }
    
    def _cio_decision(self, proposals: List[Dict], risk_report: Dict) -> List[Dict]:
        """CIO：最终决策"""
        decisions = []
        
        for proposal in proposals[:3]:  # 最多3个
            code = proposal.get("code")
            name = proposal.get("name")
            reason = proposal.get("reason", "")
            
            # 简化决策逻辑（实际应该更复杂）
            # 这里应该综合：研究员提案 + 量化师验证 + 风控官评估
            
            # 如果现金充足且仓位不高
            if risk_report["total_position"] < 0.7 and risk_report["available_cash"] > 10000:
                decisions.append({
                    "action": "买入",
                    "stock": name,
                    "code": code,
                    "reason": reason,
                    "confidence": "Medium"
                })
            else:
                decisions.append({
                    "action": "观察",
                    "stock": name,
                    "code": code,
                    "reason": "资金不足或仓位过高",
                    "confidence": "Low"
                })
        
        return decisions


def main():
    coordinator = TeamCoordinator()
    
    # 根据时间选择工作流
    hour = datetime.now().hour
    
    if 9 <= hour < 12:
        coordinator.morning_workflow()
    elif 15 <= hour < 16:
        coordinator.afternoon_workflow()
    elif 20 <= hour < 22:
        coordinator.evening_workflow()
    else:
        print("⏰ 当前时间无需运行协调器")
        print(f"   当前时间: {datetime.now().strftime('%H:%M')}")
        print("   运行时间: 09:00-12:00, 15:00-16:00, 20:00-22:00")


if __name__ == "__main__":
    main()
