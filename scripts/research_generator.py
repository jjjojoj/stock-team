#!/usr/bin/env python3
"""
研究报告生成器 v2
使用多数据源适配器和知识库
记录每次研究过程到知识库
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import json

# 添加虚拟环境路径
VENV_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)

# 项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 导入新模块
from adapters import get_data_manager
from knowledge import get_knowledge_base

# 模板路径
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "templates", "stock_research.md")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "research/")

# 股票详细信息（手动维护）
STOCK_DETAILS = {
    "sh.600459": {
        "name": "贵研铂业",
        "main_business": "铂族金属资源回收、加工、销售",
        "industry": "有色金属-稀贵金属",
        "resource_info": {
            "resources": [
                {"type": "铂族金属", "reserve": "国内最大回收基地", "grade": "-", "years": "-"},
            ],
            "products": [
                {"product": "铂族金属", "capacity": "年回收300吨", "output": "280吨", "utilization": "93%"},
            ],
            "costs": [
                {"item": "回收成本", "company": "行业最低", "industry": "平均水平", "advantage": "技术领先"},
            ],
            "summary": "国内铂族金属回收龙头，技术壁垒高，成本优势明显",
        },
    },
    "sh.601121": {
        "name": "宝地矿业",
        "main_business": "铁矿石开采、选矿、销售",
        "industry": "有色金属-铁矿",
        "resource_info": {
            "resources": [
                {"type": "铁矿石", "reserve": "1.5亿吨", "grade": "平均品位32%", "years": "30年+"},
            ],
            "products": [
                {"product": "铁精粉", "capacity": "200万吨/年", "output": "180万吨", "utilization": "90%"},
            ],
            "costs": [
                {"item": "开采成本", "company": "350元/吨", "industry": "450元/吨", "advantage": "成本领先22%"},
            ],
            "summary": "新疆铁矿龙头，资源禀赋好，成本低",
        },
    },
    "sz.000758": {
        "name": "中色股份",
        "main_business": "有色金属工程承包、资源开发",
        "industry": "有色金属-综合",
        "resource_info": {
            "resources": [
                {"type": "锌", "reserve": "200万吨", "grade": "8-12%", "years": "20年+"},
                {"type": "铅", "reserve": "100万吨", "grade": "3-5%", "years": "20年+"},
            ],
            "products": [
                {"product": "锌精矿", "capacity": "15万吨/年", "output": "14万吨", "utilization": "93%"},
                {"product": "铅精矿", "capacity": "5万吨/年", "output": "4.5万吨", "utilization": "90%"},
            ],
            "costs": [
                {"item": "开采成本", "company": "行业平均", "industry": "行业平均", "advantage": "无明显优势"},
            ],
            "summary": "央企背景，海外资源丰富，工程承包稳定"
        },
    },
}


def ensure_output_dir():
    """确保输出目录存在"""
    os.makedirs(OUTPUT_PATH, exist_ok=True)


def calculate_score_breakdown(stock: Dict) -> Dict:
    """计算各维度评分"""
    scores = {
        "controller_score": 20 if stock.get("controller") in ["央企", "省国资委", "市国资委", "国资"] else 0,
        "resource_score": 20 if stock.get("market_cap", 100) < 200 else 10,
        "valuation_score": 15 if stock.get("pb", 3) < 2.5 else 10,
        "growth_score": 15 if stock.get("net_profit_growth", 0) > 20 else 10,
        "tech_score": stock.get("tech_score", 50) // 5,
    }
    
    # 加权得分
    scores["controller_weighted"] = scores["controller_score"] * 0.2
    scores["resource_weighted"] = scores["resource_score"] * 0.25
    scores["valuation_weighted"] = scores["valuation_score"] * 0.2
    scores["growth_weighted"] = scores["growth_score"] * 0.15
    scores["tech_weighted"] = scores["tech_score"] * 0.2
    
    scores["total_score"] = (
        scores["controller_weighted"] +
        scores["resource_weighted"] +
        scores["valuation_weighted"] +
        scores["growth_weighted"] +
        scores["tech_weighted"]
    )
    
    return scores


class ResearchGenerator:
    """研究报告生成器 v2"""
    
    def __init__(self):
        self.dm = get_data_manager()
        self.kb = get_knowledge_base()
        print("✅ 研究报告生成器初始化完成")
        print(f"   数据源: {self.dm.get_available_sources()}")
    
    def get_stock_data(self, code: str) -> Optional[Dict]:
        """获取股票数据（使用新模块）"""
        try:
            # 获取实时价格
            price = self.dm.get_realtime_price(code)
            if not price:
                return None
            
            # 获取技术指标
            tech = self.dm.get_technical_indicators(code)
            
            # 获取详细信息
            details = STOCK_DETAILS.get(code, {})
            
            # 计算市值
            total_shares = {
                "sh.601168": 23.83, "sh.600362": 34.58, "sz.000878": 16.68,
                "sh.601600": 170.23, "sz.002532": 46.59, "sz.000807": 34.12,
                "sz.002466": 16.44, "sz.002460": 20.19, "sz.000792": 54.33,
                "sh.600111": 36.05, "sz.000831": 9.82, "sh.600459": 6.77,
                "sz.000758": 19.59, "sh.601121": 8.80,
            }
            market_cap = float(price.price) * total_shares.get(code, 10)
            
            # 基本面数据
            fundamentals = {
                "sh.601168": {"pb": 1.85, "pe": 12.5, "roe": 15.2, "net_profit_growth": 25.3},
                "sh.600362": {"pb": 1.42, "pe": 18.3, "roe": 8.5, "net_profit_growth": 12.8},
                "sz.000878": {"pb": 2.15, "pe": 25.6, "roe": 7.8, "net_profit_growth": -5.2},
                "sh.601600": {"pb": 1.65, "pe": 15.2, "roe": 10.8, "net_profit_growth": 45.2},
                "sz.000807": {"pb": 1.92, "pe": 12.8, "roe": 15.0, "net_profit_growth": 32.1},
                "sz.000792": {"pb": 2.15, "pe": 22.5, "roe": 11.2, "net_profit_growth": -12.5},
                "sh.600111": {"pb": 3.85, "pe": 32.5, "roe": 8.5, "net_profit_growth": -8.2},
                "sz.000831": {"pb": 2.95, "pe": 32.5, "roe": 9.1, "net_profit_growth": -8.2},
                "sh.600459": {"pb": 2.25, "pe": 25.8, "roe": 10.5, "net_profit_growth": 18.5},
                "sz.000758": {"pb": 1.85, "pe": 18.5, "roe": 12.8, "net_profit_growth": 25.3},
                "sh.601121": {"pb": 1.95, "pe": 15.2, "roe": 14.5, "net_profit_growth": 32.1},
            }
            
            fund = fundamentals.get(code, {})
            
            # 技术评分
            tech_score = 0
            if tech:
                if tech.ma5 > tech.ma10 > tech.ma20:
                    tech_score += 20
                elif tech.ma5 > tech.ma10:
                    tech_score += 10
                
                if tech.macd > tech.macd_signal:
                    tech_score += 15
                
                if 30 < tech.rsi_14 < 70:
                    tech_score += 10
                elif tech.rsi_14 < 30:
                    tech_score += 5
            
            return {
                "code": code,
                "name": details.get("name", price.ticker if hasattr(price, 'ticker') else code),
                "controller": details.get("controller", "未知"),
                "main_business": details.get("main_business", "未知"),
                "industry": details.get("industry", "未知"),
                "close": float(price.price),
                "market_cap": market_cap,
                "pb": fund.get("pb", "N/A"),
                "pe": fund.get("pe", "N/A"),
                "roe": fund.get("roe", "N/A"),
                "net_profit_growth": fund.get("net_profit_growth", 0),
                "tech_score": tech_score,
                "tech_data": tech,
                "resource_info": details.get("resource_info"),
            }
        except Exception as e:
            print(f"获取 {code} 数据失败: {e}")
            return None
    
    def generate_report(self, code: str) -> Optional[str]:
        """生成研究报告"""
        ensure_output_dir()
        
        stock = self.get_stock_data(code)
        if not stock:
            print(f"❌ 无法获取 {code} 的数据")
            return None
        
        # 读取模板
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # 计算评分
        scores = calculate_score_breakdown(stock)
        
        # 替换模板变量
        report = template
        for key, value in stock.items():
            if isinstance(value, (list, dict)):
                continue
            report = report.replace(f"{{{key}}}", str(value))
        
        # 添加评分
        report = report.replace("{total_score}", str(int(scores["total_score"])))
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{stock['name']}_{timestamp}.md"
        filepath = os.path.join(OUTPUT_PATH, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"✅ 研究报告已生成: {filepath}")
        
        # 记录到知识库
        self._save_to_knowledge_base(code, stock, scores, filepath)
        
        return filepath
    
    def _save_to_knowledge_base(self, code: str, stock: Dict, scores: Dict, filepath: str):
        """保存研究记录到知识库"""
        try:
            content = f"""
股票: {stock.get('name', '')} ({code})
研究时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
综合评分: {int(scores.get('total_score', 0))}/100
建议操作: {'买入' if scores.get('total_score', 0) >= 70 else '观望'}
报告路径: {filepath}
"""
            
            self.kb.add_decision(
                content=content,
                metadata={
                    "type": "research",
                    "stock": code,
                    "score": int(scores.get("total_score", 0)),
                    "report_path": filepath,
                }
            )
            
            print(f"✅ 研究记录已保存到知识库")
        except Exception as e:
            print(f"⚠️ 保存到知识库失败: {e}")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 research_generator.py <股票代码>")
        print("示例: python3 research_generator.py sh.600459")
        sys.exit(1)
    
    code = sys.argv[1]
    generator = ResearchGenerator()
    generator.generate_report(code)


if __name__ == "__main__":
    main()
