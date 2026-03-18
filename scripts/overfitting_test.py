#!/usr/bin/env python3
"""
过拟合测试工具 - 确保策略鲁棒性

功能：
1. 参数敏感性分析
2. 蒙特卡洛实战（1000 次）
3. 滚动窗口回测（Walk-Forward）
4. 过拟合风险报告
"""

import sys
import os
import json
import random
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 配置
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'overfitting_verify.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ParameterVerify:
    """参数测试结果"""
    parameter: str
    base_value: float
    verify_values: List[float]
    returns: List[float]
    avg_return: float
    std_return: float
    sensitivity: float


@dataclass
class MonteCarloResult:
    """蒙特卡洛实战结果"""
    simulations: int
    avg_return: float
    std_return: float
    min_return: float
    max_return: float
    percentile_5: float
    percentile_95: float
    positive_ratio: float


@dataclass
class WalkForwardResult:
    """滚动窗口回测结果"""
    windows: int
    avg_return: float
    std_return: float
    consistency: float  # 一致性（胜率）
    is_stable: bool


class OverfittingVerifyer:
    """过拟合测试器"""
    
    def __init__(self, base_strategy_params: Dict = None):
        self.base_params = base_strategy_params or {
            "market_cap_max": 200,  # 市值上限（亿）
            "pb_max": 2.5,  # PB 上限
            "roe_min": 10,  # ROE 下限
            "position_limit": 0.2,  # 单只仓位上限
            "stop_loss": -0.08,  # 止损线
        }
        self.results = {}
    
    def parameter_sensitivity_verify(self, parameter: str, verify_range: Tuple[float, float, float],
                                   backverify_func, base_result: float) -> ParameterVerify:
        """
        参数敏感性测试
        
        Args:
            parameter: 参数名称
            verify_range: (min, max, step)
            backverify_func: 回测函数
            base_result: 基准收益
        
        Returns:
            参数测试结果
        """
        min_val, max_val, step = verify_range
        verify_values = np.arange(min_val, max_val + step, step).tolist()
        returns = []
        
        logger.info(f"测试参数 {parameter}: {verify_values}")
        
        for value in verify_values:
            # 修改参数
            verify_params = self.base_params.copy()
            verify_params[parameter] = value
            
            # 运行回测
            result = backverify_func(verify_params)
            returns.append(result)
            logger.info(f"  {parameter}={value}: 收益={result:.2f}%")
        
        # 计算统计
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        # 敏感性：参数变化导致的收益波动
        sensitivity = std_return / abs(base_result) if base_result != 0 else 0
        
        verify_result = ParameterVerify(
            parameter=parameter,
            base_value=self.base_params.get(parameter, 0),
            verify_values=verify_values,
            returns=returns,
            avg_return=avg_return,
            std_return=std_return,
            sensitivity=sensitivity
        )
        
        self.results[f"sensitivity_{parameter}"] = verify_result
        
        return verify_result
    
    def monte_carlo_simulation(self, base_strategy_func, params_func, 
                               n_simulations: int = 1000) -> MonteCarloResult:
        """
        蒙特卡洛实战
        
        Args:
            base_strategy_func: 基础策略函数
            params_func: 参数扰动函数
            n_simulations: 实战次数
        
        Returns:
            蒙特卡洛实战结果
        """
        logger.info(f"开始蒙特卡洛实战：{n_simulations}次")
        
        returns = []
        
        for i in range(n_simulations):
            # 扰动参数
            perturbed_params = params_func(self.base_params, i)
            
            # 运行策略
            result = base_strategy_func(perturbed_params)
            returns.append(result)
            
            if (i + 1) % 100 == 0:
                logger.info(f"  进度：{i+1}/{n_simulations}, 平均收益={np.mean(returns):.2f}%")
        
        returns = np.array(returns)
        
        result = MonteCarloResult(
            simulations=n_simulations,
            avg_return=np.mean(returns),
            std_return=np.std(returns),
            min_return=np.min(returns),
            max_return=np.max(returns),
            percentile_5=np.percentile(returns, 5),
            percentile_95=np.percentile(returns, 95),
            positive_ratio=np.sum(returns > 0) / len(returns)
        )
        
        self.results["monte_carlo"] = result
        
        logger.info(f"实战完成：平均={result.avg_return:.2f}%, 标准差={result.std_return:.2f}%, "
                   f"正收益比例={result.positive_ratio:.1%}")
        
        return result
    
    def walk_forward_analysis(self, backverify_func, total_data: List, 
                             train_windows: int = 3, verify_windows: int = 1) -> WalkForwardResult:
        """
        滚动窗口回测（Walk-Forward Analysis）
        
        Args:
            backverify_func: 回测函数
            total_data: 总数据（按时间排序）
            train_windows: 训练窗口数
            verify_windows: 测试窗口数
        
        Returns:
            滚动窗口回测结果
        """
        logger.info(f"开始滚动窗口回测：训练{train_windows}窗口，测试{verify_windows}窗口")
        
        n_windows = len(total_data) // (train_windows + verify_windows)
        if n_windows < 3:
            logger.warning("数据不足，无法进行滚动窗口回测")
            return None
        
        returns = []
        
        for i in range(n_windows):
            # 分割训练集和测试集
            start_idx = i * (train_windows + verify_windows)
            train_end = start_idx + train_windows
            verify_end = train_end + verify_windows
            
            train_data = total_data[start_idx:train_end]
            verify_data = total_data[train_end:verify_end]
            
            # 在训练集上优化参数
            optimized_params = self._optimize_on_data(backverify_func, train_data)
            
            # 在测试集上验证
            verify_result = backverify_func(optimized_params, verify_data)
            returns.append(verify_result)
            
            logger.info(f"  窗口{i+1}/{n_windows}: 收益={verify_result:.2f}%")
        
        returns = np.array(returns)
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        # 一致性：盈利窗口比例
        consistency = np.sum(returns > 0) / len(returns)
        
        # 稳定性判断：如果标准差小且一致性高，则稳定
        is_stable = std_return < 10 and consistency > 0.6
        
        result = WalkForwardResult(
            windows=n_windows,
            avg_return=avg_return,
            std_return=std_return,
            consistency=consistency,
            is_stable=is_stable
        )
        
        self.results["walk_forward"] = result
        
        logger.info(f"滚动回测完成：平均={avg_return:.2f}%, 一致性={consistency:.1%}, "
                   f"稳定性={'✅' if is_stable else '❌'}")
        
        return result
    
    def _optimize_on_data(self, backverify_func, data: List) -> Dict:
        """在数据上优化参数（简化版）"""
        # 实际应用中应该使用网格搜索或贝叶斯优化
        # 这里简单返回基准参数
        return self.base_params.copy()
    
    def generate_report(self, output_file: str = None) -> str:
        """生成过拟合风险报告"""
        report = f"""
# 🧪 过拟合测试报告

**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**基准参数**：{json.dumps(self.base_params, indent=2)}

---

## 📊 测试结果

"""
        
        # 参数敏感性
        sensitivity_verifys = {k: v for k, v in self.results.items() if k.startswith("sensitivity_")}
        if sensitivity_verifys:
            report += "### 1. 参数敏感性分析\n\n"
            report += "| 参数 | 基准值 | 测试范围 | 平均收益 | 标准差 | 敏感性 |\n"
            report += "|------|--------|---------|---------|--------|--------|\n"
            
            for name, verify in sensitivity_verifys.items():
                param_name = name.replace("sensitivity_", "")
                range_str = f"{min(verify.verify_values):.1f}-{max(verify.verify_values):.1f}"
                sensitivity_level = "✅ 低" if verify.sensitivity < 0.3 else "⚠️ 中" if verify.sensitivity < 0.6 else "❌ 高"
                
                report += f"| {param_name} | {verify.base_value:.2f} | {range_str} | "
                report += f"{verify.avg_return:.2f}% | {verify.std_return:.2f}% | {sensitivity_level} |\n"
            
            report += "\n"
        
        # 蒙特卡洛实战
        if "monte_carlo" in self.results:
            mc = self.results["monte_carlo"]
            report += "### 2. 蒙特卡洛实战\n\n"
            report += f"- 实战次数：{mc.simulations}\n"
            report += f"- 平均收益：{mc.avg_return:.2f}%\n"
            report += f"- 收益标准差：{mc.std_return:.2f}%\n"
            report += f"- 最小收益：{mc.min_return:.2f}%\n"
            report += f"- 最大收益：{mc.max_return:.2f}%\n"
            report += f"- 5% 分位数：{mc.percentile_5:.2f}%\n"
            report += f"- 95% 分位数：{mc.percentile_95:.2f}%\n"
            report += f"- 正收益比例：{mc.positive_ratio:.1%}\n\n"
            
            # 风险评估
            if mc.positive_ratio > 0.7 and mc.std_return < 20:
                risk = "✅ 低风险"
            elif mc.positive_ratio > 0.5 and mc.std_return < 30:
                risk = "⚠️ 中风险"
            else:
                risk = "❌ 高风险"
            
            report += f"**过拟合风险**：{risk}\n\n"
        
        # 滚动窗口回测
        if "walk_forward" in self.results:
            wf = self.results["walk_forward"]
            report += "### 3. 滚动窗口回测\n\n"
            report += f"- 回测窗口数：{wf.windows}\n"
            report += f"- 平均收益：{wf.avg_return:.2f}%\n"
            report += f"- 收益标准差：{wf.std_return:.2f}%\n"
            report += f"- 一致性（胜率）：{wf.consistency:.1%}\n"
            report += f"- 稳定性：{'✅ 稳定' if wf.is_stable else '❌ 不稳定'}\n\n"
        
        # 总体评估
        report += "---\n\n## 💡 总体评估\n\n"
        
        # 计算总分
        score = 0
        max_score = 0
        
        if sensitivity_verifys:
            max_score += 3
            avg_sensitivity = np.mean([t.sensitivity for t in sensitivity_verifys.values()])
            if avg_sensitivity < 0.3:
                score += 3
            elif avg_sensitivity < 0.6:
                score += 2
            else:
                score += 1
        
        if "monte_carlo" in self.results:
            max_score += 4
            mc = self.results["monte_carlo"]
            if mc.positive_ratio > 0.7:
                score += 2
            if mc.std_return < 20:
                score += 2
        
        if "walk_forward" in self.results:
            max_score += 3
            wf = self.results["walk_forward"]
            if wf.is_stable:
                score += 3
            elif wf.consistency > 0.6:
                score += 2
            else:
                score += 1
        
        # 评估结论
        if max_score > 0:
            quality = score / max_score
            if quality > 0.8:
                conclusion = "✅ **策略鲁棒性强**：参数稳定，过拟合风险低，可以实盘"
            elif quality > 0.6:
                conclusion = "⚠️ **策略鲁棒性中等**：需要进一步优化参数"
            else:
                conclusion = "❌ **策略鲁棒性差**：存在过拟合风险，建议重新设计"
        else:
            conclusion = "⚠️ **测试不足**：需要运行更多测试"
        
        report += conclusion + f"\n\n**得分**：{score}/{max_score} ({quality:.0%} 如果 max_score>0 else 'N/A')\n"
        
        # 保存报告
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存：{output_file}")
        
        print(report)
        
        return report


def example_params_perturb(base_params: Dict, seed: int) -> Dict:
    """示例参数扰动函数"""
    random.seed(seed)
    perturbed = base_params.copy()
    
    # 对每个参数添加±10% 的随机扰动
    for key, value in perturbed.items():
        if isinstance(value, (int, float)):
            noise = random.uniform(-0.1, 0.1)
            perturbed[key] = value * (1 + noise)
    
    return perturbed


def example_backverify(params: Dict, data: List = None) -> float:
    """示例回测函数"""
    # 实际应用中应该调用真实的回测系统
    # 这里简单实战
    
    # 基于参数计算"收益"（实战）
    base_return = 15.0  # 基准收益 15%
    
    # 参数越接近最优值，收益越高
    optimal = {"market_cap_max": 200, "pb_max": 2.5, "roe_min": 10}
    
    deviation = 0
    for key, opt_val in optimal.items():
        if key in params:
            deviation += abs(params[key] - opt_val) / opt_val
    
    # 添加随机噪声
    noise = random.gauss(0, 5)
    
    return base_return - deviation * 10 + noise


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="过拟合测试")
    parser.add_argument("action", choices=["sensitivity", "montecarlo", "walkforward", "full", "verify"],
                       help="测试类型")
    parser.add_argument("--param", type=str, help="参数名称（敏感性测试用）")
    parser.add_argument("--range", type=str, help="测试范围 min,max,step")
    parser.add_argument("--simulations", type=int, default=100, help="实战次数")
    parser.add_argument("--output", type=str, help="输出报告文件")
    
    args = parser.parse_args()
    
    verifyer = OverfittingVerifyer()
    
    if args.action == "sensitivity":
        if not args.param or not args.range:
            print("❌ 用法：python3 overfitting_verify.py sensitivity --param <参数名> --range <min,max,step>")
            sys.exit(1)
        
        min_val, max_val, step = map(float, args.range.split(","))
        
        result = verifyer.parameter_sensitivity_verify(
            parameter=args.param,
            verify_range=(min_val, max_val, step),
            backverify_func=lambda p: example_backverify(p),
            base_result=15.0
        )
        
        print(f"\n参数 {args.param} 敏感性：{result.sensitivity:.3f}")
    
    elif args.action == "montecarlo":
        result = verifyer.monte_carlo_simulation(
            base_strategy_func=lambda p: example_backverify(p),
            params_func=example_params_perturb,
            n_simulations=args.simulations
        )
        
        print(f"\n蒙特卡洛实战完成：正收益比例={result.positive_ratio:.1%}")
    
    elif args.action == "walkforward":
        # 生成实战数据
        mock_data = list(range(100))  # 100 个时间窗口
        result = verifyer.walk_forward_analysis(
            backverify_func=lambda p, d: example_backverify(p),
            total_data=mock_data
        )
        
        print(f"\n滚动回测完成：稳定性={'✅' if result.is_stable else '❌'}")
    
    elif args.action == "full":
        print("\n🧪 完整过拟合测试")
        print("="*60)
        
        # 1. 参数敏感性
        print("\n1. 参数敏感性测试...")
        for param in ["market_cap_max", "pb_max", "roe_min"]:
            if param == "market_cap_max":
                verify_range = (100, 300, 25)
            elif param == "pb_max":
                verify_range = (1.5, 3.5, 0.25)
            else:
                verify_range = (5, 15, 1)
            
            verifyer.parameter_sensitivity_verify(
                parameter=param,
                verify_range=verify_range,
                backverify_func=lambda p: example_backverify(p),
                base_result=15.0
            )
        
        # 2. 蒙特卡洛实战
        print("\n2. 蒙特卡洛实战...")
        verifyer.monte_carlo_simulation(
            base_strategy_func=lambda p: example_backverify(p),
            params_func=example_params_perturb,
            n_simulations=args.simulations
        )
        
        # 3. 滚动窗口回测
        print("\n3. 滚动窗口回测...")
        mock_data = list(range(100))
        verifyer.walk_forward_analysis(
            backverify_func=lambda p, d: example_backverify(p),
            total_data=mock_data
        )
        
        # 4. 生成报告
        print("\n4. 生成报告...")
        output_file = args.output or os.path.join(REPORTS_DIR, f"overfitting_verify_{datetime.now().strftime('%Y%m%d')}.md")
        verifyer.generate_report(output_file)
    
    elif args.action == "verify":
        print("\n🧪 过拟合测试系统测试")
        print("="*60)
        
        # 简单测试
        result = verifyer.parameter_sensitivity_verify(
            parameter="verify_param",
            verify_range=(1, 5, 1),
            backverify_func=lambda p: random.uniform(5, 25),
            base_result=15.0
        )
        
        print(f"\n参数敏感性：{result.sensitivity:.3f}")
        print(f"平均收益：{result.avg_return:.2f}%")
        print(f"标准差：{result.std_return:.2f}%")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)


if __name__ == "__main__":
    main()
