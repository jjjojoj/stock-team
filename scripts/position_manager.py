#!/usr/bin/env python3
"""
仓位管理优化 - 动态调整仓位

功能：
1. 根据市场风险动态调整仓位
2. 持仓股相关性计算
3. 凯利公式优化仓位
4. 行业集中度控制
"""

import sys
import os
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import logging

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'position_manager.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PositionManager:
    """仓位管理器"""
    
    # 风险等级对应的仓位上限
    RISK_POSITION_MAP = {
        (0, 20): 0.80,    # 极低风险：80%
        (20, 40): 0.70,   # 低风险：70%
        (40, 60): 0.50,   # 中风险：50%
        (60, 80): 0.30,   # 高风险：30%
        (80, 100): 0.10,  # 极高风险：10%
    }
    
    def __init__(self, total_capital: float = 1000000.0):
        self.total_capital = total_capital
        self.positions: Dict[str, Dict] = {}
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = os.path.join(CONFIG_DIR, "position_config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "single_stock_limit": 0.20,  # 单只股票上限 20%
            "industry_limit": 0.40,      # 单行业上限 40%
            "max_positions": 3,          # 最多持有 3 只
            "use_kelly": True,           # 使用凯利公式
            "kelly_cap": 0.20,           # 凯利仓位上限
        }
    
    def calculate_position_by_risk(self, market_risk_score: float) -> float:
        """
        根据市场风险计算总仓位
        
        Args:
            market_risk_score: 市场风险评分（0-100）
        
        Returns:
            建议仓位（0-1）
        """
        for (min_risk, max_risk), position in self.RISK_POSITION_MAP.items():
            if min_risk <= market_risk_score < max_risk:
                return position
        return 0.10
    
    def calculate_kelly_position(self, win_rate: float, profit_loss_ratio: float) -> float:
        """
        凯利公式计算最优仓位
        
        Args:
            win_rate: 胜率（0-1）
            profit_loss_ratio: 盈亏比（平均盈利/平均亏损）
        
        Returns:
            凯利仓位（0-1）
        """
        if not self.config.get("use_kelly", True):
            return self.config["single_stock_limit"]
        
        # 凯利公式：f* = (p * b - q) / b
        # p = 胜率，q = 1-p，b = 盈亏比
        p = win_rate
        q = 1 - p
        b = profit_loss_ratio
        
        if b <= 0:
            return 0.05  # 最小仓位
        
        kelly_fraction = (p * b - q) / b
        
        # 应用凯利分数的一半（保守凯利）
        kelly_fraction = kelly_fraction / 2
        
        # 限制在合理范围内
        kelly_fraction = max(0.05, min(kelly_fraction, self.config["kelly_cap"]))
        
        logger.info(f"凯利仓位：胜率={win_rate:.1%}, 盈亏比={profit_loss_ratio:.2f}, "
                   f"凯利值={kelly_fraction:.1%}")
        
        return kelly_fraction
    
    def calculate_correlation(self, returns1: List[float], returns2: List[float]) -> float:
        """计算相关性"""
        if len(returns1) != len(returns2) or len(returns1) < 5:
            return 0.0
        
        return np.corrcoef(returns1, returns2)[0, 1]
    
    def check_industry_concentration(self, positions: Dict[str, Dict]) -> Dict[str, float]:
        """
        检查行业集中度
        
        Args:
            positions: 持仓字典
        
        Returns:
            行业分布
        """
        industry_exposure = {}
        
        for code, pos in positions.items():
            industry = pos.get("industry", "未知")
            market_value = pos.get("market_value", 0)
            
            if industry not in industry_exposure:
                industry_exposure[industry] = 0
            industry_exposure[industry] += market_value
        
        # 转换为比例
        total_value = sum(industry_exposure.values())
        if total_value > 0:
            industry_exposure = {k: v/total_value for k, v in industry_exposure.items()}
        
        return industry_exposure
    
    def can_buy(self, stock_code: str, stock_industry: str, 
                target_position: float, current_positions: Dict[str, Dict]) -> Tuple[bool, str]:
        """
        检查是否可以买入
        
        Args:
            stock_code: 股票代码
            stock_industry: 所属行业
            target_position: 目标仓位
            current_positions: 当前持仓
        
        Returns:
            (是否允许，原因)
        """
        # 检查持仓数量限制
        if len(current_positions) >= self.config["max_positions"]:
            return False, f"已达最大持仓数限制（{self.config['max_positions']}只）"
        
        # 检查单只股票仓位
        if target_position > self.config["single_stock_limit"]:
            return False, f"超过单只股票仓位限制（{self.config['single_stock_limit']*100:.0f}%）"
        
        # 检查行业集中度
        industry_exposure = self.check_industry_concentration(current_positions)
        current_industry = industry_exposure.get(stock_industry, 0)
        
        if current_industry + target_position > self.config["industry_limit"]:
            return False, f"超过行业集中度限制（{self.config['industry_limit']*100:.0f}%）"
        
        # 检查是否已持有
        if stock_code in current_positions:
            return False, f"已持有该股票"
        
        return True, "可以买入"
    
    def optimize_positions(self, market_risk: float, opportunities: List[Dict],
                          win_rates: Dict[str, float], profit_loss_ratios: Dict[str, float]) -> List[Dict]:
        """
        优化仓位配置
        
        Args:
            market_risk: 市场风险评分
            opportunities: 投资机会列表
            win_rates: 各股票胜率
            profit_loss_ratios: 各股票盈亏比
        
        Returns:
            优化后的仓位配置
        """
        # 1. 计算总仓位
        total_position = self.calculate_position_by_risk(market_risk)
        
        # 2. 筛选机会
        valid_opportunities = []
        for opp in opportunities:
            code = opp["code"]
            win_rate = win_rates.get(code, 0.5)
            pl_ratio = profit_loss_ratios.get(code, 1.5)
            
            # 凯利仓位
            kelly = self.calculate_kelly_position(win_rate, pl_ratio)
            
            valid_opportunities.append({
                **opp,
                "kelly_position": kelly,
                "score": win_rate * pl_ratio,  # 简单评分
            })
        
        # 3. 按评分排序
        valid_opportunities.sort(key=lambda x: x["score"], reverse=True)
        
        # 4. 分配仓位
        allocations = []
        remaining_position = total_position
        
        for opp in valid_opportunities[:self.config["max_positions"]]:
            # 计算该股票可分配仓位
            position = min(
                opp["kelly_position"],
                self.config["single_stock_limit"],
                remaining_position
            )
            
            if position >= 0.05:  # 最小 5% 仓位
                allocations.append({
                    "code": opp["code"],
                    "name": opp["name"],
                    "position": position,
                    "reason": f"凯利={opp['kelly_position']:.1%}, 评分={opp['score']:.2f}",
                })
                remaining_position -= position
        
        logger.info(f"仓位优化完成：总仓位={total_position:.1%}, 分配{len(allocations)}只股票")
        
        return allocations


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="仓位管理")
    parser.add_argument("action", choices=["verify", "optimize"], help="verify=测试，optimize=优化")
    parser.add_argument("--risk", type=float, default=50, help="市场风险评分")
    
    args = parser.parse_args()
    
    manager = PositionManager()
    
    if args.action == "verify":
        print("\n🧪 仓位管理系统测试")
        print("="*60)
        
        # 测试 1：风险仓位
        print("\n1. 测试风险仓位计算...")
        for risk in [15, 35, 55, 75, 90]:
            position = manager.calculate_position_by_risk(risk)
            print(f"   风险={risk}: 仓位={position*100:.0f}%")
        
        # 测试 2：凯利公式
        print("\n2. 测试凯利公式...")
        verify_cases = [
            (0.6, 2.0, "胜率 60%, 盈亏比 2:1"),
            (0.5, 1.5, "胜率 50%, 盈亏比 1.5:1"),
            (0.4, 3.0, "胜率 40%, 盈亏比 3:1"),
        ]
        for win_rate, pl_ratio, desc in verify_cases:
            kelly = manager.calculate_kelly_position(win_rate, pl_ratio)
            print(f"   {desc}: 凯利仓位={kelly*100:.1f}%")
        
        # 测试 3：行业集中度
        print("\n3. 测试行业集中度...")
        mock_positions = {
            "sh.600459": {"industry": "有色金属", "market_value": 200000},
            "sz.000758": {"industry": "有色金属", "market_value": 150000},
            "sh.600000": {"industry": "银行", "market_value": 100000},
        }
        industry_dist = manager.check_industry_concentration(mock_positions)
        for industry, ratio in industry_dist.items():
            print(f"   {industry}: {ratio*100:.1f}%")
        
        # 测试 4：买入检查
        print("\n4. 测试买入检查...")
        can_buy, reason = manager.can_buy(
            stock_code="sh.600001",
            stock_industry="房地产",
            target_position=0.15,
            current_positions=mock_positions
        )
        print(f"   可以买入：{can_buy}, 原因：{reason}")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)
    
    elif args.action == "optimize":
        print("\n📊 仓位优化")
        print("="*60)
        
        # 实战投资机会
        opportunities = [
            {"code": "sh.600459", "name": "贵研铂业"},
            {"code": "sz.000758", "name": "中色股份"},
            {"code": "sh.600000", "name": "浦发银行"},
        ]
        
        win_rates = {
            "sh.600459": 0.65,
            "sz.000758": 0.55,
            "sh.600000": 0.50,
        }
        
        pl_ratios = {
            "sh.600459": 2.0,
            "sz.000758": 1.8,
            "sh.600000": 1.5,
        }
        
        allocations = manager.optimize_positions(
            market_risk=args.risk,
            opportunities=opportunities,
            win_rates=win_rates,
            profit_loss_ratios=pl_ratios
        )
        
        print(f"\n市场风险：{args.risk}")
        print(f"\n建议配置：")
        for alloc in allocations:
            print(f"  - {alloc['name']} ({alloc['code']}): {alloc['position']*100:.1f}%")
            print(f"    理由：{alloc['reason']}")
        
        print("="*60)


if __name__ == "__main__":
    main()
