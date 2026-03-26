#!/usr/bin/env python3
"""
完整选股工具 v4 - 使用多数据源适配器
整合 PB/ROE 数据和技术指标筛选
使用 adapters 模块（自动切换数据源）
"""

import sys
import os
import urllib.request
from types import SimpleNamespace

# 添加项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 添加虚拟环境路径
VENV_PATH = os.path.join(
    PROJECT_ROOT,
    "venv",
    "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages",
)
if os.path.isdir(VENV_PATH):
    sys.path.insert(0, VENV_PATH)

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.fundamentals import get_fundamental_bundles
from core.runtime_guardrails import (
    evaluate_runtime_mode,
    record_datasource_fallback,
    record_guardrail_event,
    record_guardrail_success,
    task_lock,
    TaskLockedError,
)

# 导入新适配器
ADAPTER_IMPORT_ERROR = None
try:
    from adapters import get_data_manager
    HAS_ADAPTERS = True
except Exception as exc:
    get_data_manager = None
    HAS_ADAPTERS = False
    ADAPTER_IMPORT_ERROR = exc

# 股票池
STOCK_POOL = {
    "有色金属": {
        "铜": ["sh.601168", "sh.600362", "sz.000878"],
        "铝": ["sh.601600", "sz.002532", "sz.000807"],
        "锂": ["sz.002466", "sz.002460", "sz.000792"],
        "稀土": ["sh.600111", "sz.000831"],
        "其他": ["sh.600459", "sz.000758", "sh.601121"],
    },
    "芯片": {
        "制造": ["sh.688981", "sh.688396"],
        "设备": ["sh.688037", "sh.688012"],
        "材料": ["sz.300661"],
    },
}

# 实控人
CONTROLLERS = {
    "sh.601168": ("西部矿业", "青海国资委"),
    "sh.600362": ("江西铜业", "江西国资委"),
    "sz.000878": ("云南铜业", "央企"),
    "sh.601600": ("中国铝业", "央企"),
    "sz.002532": ("天山铝业", "无实控人"),
    "sz.000807": ("云铝股份", "央企"),
    "sz.002466": ("天齐锂业", "民营企业"),
    "sz.002460": ("赣锋锂业", "民营企业"),
    "sz.000792": ("盐湖股份", "青海国资委"),
    "sh.600111": ("北方稀土", "央企"),
    "sz.000831": ("五矿稀土", "央企"),
    "sh.600459": ("贵研铂业", "央企"),
    "sz.000758": ("中色股份", "央企"),
    "sh.601121": ("宝地矿业", "新疆国资委"),
    "sh.688981": ("中芯国际", "央企"),
    "sh.688396": ("华润微", "央企"),
    "sh.688037": ("芯源微", "国资"),
    "sh.688012": ("中微公司", "国资"),
    "sz.300661": ("东岳硅材", "国资"),
}

# 总股本（亿股）
TOTAL_SHARES = {
    "sh.601168": 23.83, "sh.600362": 34.58, "sz.000878": 16.68,
    "sh.601600": 170.23, "sz.002532": 46.59, "sz.000807": 34.12,
    "sz.002466": 16.44, "sz.002460": 20.19, "sz.000792": 54.33,
    "sh.600111": 36.05, "sz.000831": 9.82, "sh.600459": 6.77,
    "sz.000758": 19.59, "sh.601121": 8.80, "sh.688981": 19.38,
    "sh.688396": 11.89, "sz.300661": 2.10, "sh.688012": 5.40,
    "sh.688037": 1.26,
}

# 基本面数据
FUNDAMENTAL_DATA = {
    # 铜
    "sh.601168": {"pb": 1.85, "pe": 12.5, "roe": 15.2, "net_profit_growth": 25.3, "dividend_yield": 1.8},
    "sh.600362": {"pb": 1.42, "pe": 18.3, "roe": 8.5, "net_profit_growth": 12.8, "dividend_yield": 2.1},
    "sz.000878": {"pb": 2.15, "pe": 25.6, "roe": 7.8, "net_profit_growth": -5.2, "dividend_yield": 0.8},
    # 铝
    "sh.601600": {"pb": 1.65, "pe": 15.2, "roe": 10.8, "net_profit_growth": 45.2, "dividend_yield": 1.2},
    "sz.002532": {"pb": 1.38, "pe": 8.5, "roe": 16.2, "net_profit_growth": 18.5, "dividend_yield": 3.5},
    "sz.000807": {"pb": 1.92, "pe": 12.8, "roe": 15.0, "net_profit_growth": 32.1, "dividend_yield": 2.3},
    # 锂
    "sz.002466": {"pb": 2.85, "pe": 35.2, "roe": 8.1, "net_profit_growth": -45.2, "dividend_yield": 0.5},
    "sz.002460": {"pb": 3.12, "pe": 42.5, "roe": 7.3, "net_profit_growth": -52.3, "dividend_yield": 0.3},
    "sz.000792": {"pb": 2.15, "pe": 22.5, "roe": 11.2, "net_profit_growth": -12.5, "dividend_yield": 0.3},
    # 稀土
    "sh.600111": {"pb": 3.85, "pe": 32.5, "roe": 8.5, "net_profit_growth": -8.2, "dividend_yield": 0.5},
    "sz.000831": {"pb": 2.95, "pe": 32.5, "roe": 9.1, "net_profit_growth": -8.2, "dividend_yield": 0.5},
    # 其他
    "sh.600459": {"pb": 2.25, "pe": 25.8, "roe": 10.5, "net_profit_growth": 18.5, "dividend_yield": 1.2},
    "sz.000758": {"pb": 1.85, "pe": 18.5, "roe": 12.8, "net_profit_growth": 25.3, "dividend_yield": 1.5},
    "sh.601121": {"pb": 1.95, "pe": 15.2, "roe": 14.5, "net_profit_growth": 32.1, "dividend_yield": 2.1},
    # 芯片
    "sh.688981": {"pb": 2.95, "pe": 32.5, "roe": 9.1, "net_profit_growth": -8.2, "dividend_yield": 0.5},
    "sh.688396": {"pb": 5.85, "pe": 52.3, "roe": 8.9, "net_profit_growth": -15.2, "dividend_yield": 0.2},
    "sz.300661": {"pb": 5.85, "pe": 52.3, "roe": 8.9, "net_profit_growth": -15.2, "dividend_yield": 0.2},
    "sh.688012": {"pb": 6.52, "pe": 68.5, "roe": 9.5, "net_profit_growth": 18.5, "dividend_yield": 0.1},
    "sh.688037": {"pb": 5.85, "pe": 58.2, "roe": 10.1, "net_profit_growth": 22.3, "dividend_yield": 0.2},
}

MIN_TOP_CANDIDATE_SCORE = 20


class StockSelector:
    """选股工具（使用多数据源适配器）"""
    
    def __init__(self):
        self.dm = get_data_manager() if HAS_ADAPTERS else None
        self.fundamentals: Dict[str, Dict] = {}
        if self.dm:
            print("✅ 数据源管理器初始化完成")
            print(f"   可用数据源: {self.dm.get_available_sources()}")
        else:
            print(f"⚠️ 多数据源适配器不可用，已降级为轻量模式: {ADAPTER_IMPORT_ERROR}")

    def _get_fallback_price(self, code: str):
        """使用腾讯行情接口兜底，避免适配器依赖缺失时整个任务失败。"""
        try:
            stock_code = code.replace(".", "")
            if "." in code:
                prefix, symbol = code.split(".", 1)
                stock_code = f"{prefix}{symbol}"

            url = f"http://qt.gtimg.cn/q={stock_code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk", errors="ignore")

            if "~" not in text:
                return None

            parts = text.split("~")
            current_price = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
            prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0.0
            volume = float(parts[6]) if len(parts) > 6 and parts[6] else 0.0
            change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0.0

            return SimpleNamespace(
                price=current_price,
                change_percent=change_pct,
                volume=volume,
            )
        except Exception as exc:
            print(f"获取 {code} 实时价格失败: {exc}")
            return None
    
    def get_stock_data(self, code: str) -> Optional[Dict]:
        """获取股票完整数据（行情 + 基本面 + 技术面）"""
        try:
            # 1. 获取实时价格（使用适配器）
            price = self.dm.get_realtime_price(code) if self.dm else None
            if not price:
                price = self._get_fallback_price(code)
                if price:
                    record_datasource_fallback("selector", "quote", "tencent_quote", f"{code} 选股行情改用腾讯接口")
            if not price:
                return None
            
            # 2. 计算市值
            total_shares = TOTAL_SHARES.get(code, 10)
            fund_data = self.fundamentals.get(code) or {}
            market_cap = float(fund_data.get("market_cap", 0) or 0) or (float(price.price) * total_shares)
            
            # 3. 获取基本面数据（实时优先，静态表兜底）
            if not fund_data:
                fund_data = get_fundamental_bundles([code], legacy_data=FUNDAMENTAL_DATA).get(code, {})
            
            # 4. 获取技术指标（使用适配器）
            tech_data = None
            if self.dm:
                try:
                    tech = self.dm.get_technical_indicators(code)
                    if tech:
                        # 计算技术评分
                        tech_score = self._calculate_technical_score(tech)
                        
                        tech_data = {
                            "technical_score": tech_score,
                            "recommendation": self._get_recommendation(tech_score),
                            "macd": "金叉" if tech.macd > tech.macd_signal else "死叉",
                            "kdj": self._get_kdj_signal(tech.rsi_14),
                            "rsi": tech.rsi_14,
                        }
                except Exception:
                    pass
            
            # 5. 计算综合评分
            score = self._calculate_score(
                market_cap=market_cap,
                fund_data=fund_data,
                tech_data=tech_data
            )
            
            return {
                "code": code,
                "name": CONTROLLERS.get(code, ("未知", "未知"))[0],
                "controller": CONTROLLERS.get(code, ("未知", "未知"))[1],
                "price": float(price.price),
                "change_pct": float(price.change_percent) if hasattr(price, 'change_percent') else 0.0,
                "volume": float(price.volume) if price.volume else 0,
                "market_cap": market_cap,
                "fundamentals": fund_data,
                "technical": tech_data,
                "score": score,
            }
        except Exception as e:
            print(f"获取 {code} 数据失败: {e}")
            return None
    
    def _calculate_technical_score(self, tech) -> int:
        """计算技术评分"""
        score = 0
        
        # MA 排列
        if tech.ma5 > tech.ma10 > tech.ma20 > tech.ma60:
            score += 30
        elif tech.ma5 > tech.ma10 > tech.ma20:
            score += 20
        elif tech.ma5 > tech.ma10:
            score += 10
        
        # MACD
        if tech.macd > tech.macd_signal:
            score += 15
        
        # RSI
        if 30 < tech.rsi_14 < 70:
            score += 15
        elif tech.rsi_14 < 30:  # 超卖
            score += 10
        
        # 布林带位置
        if tech.bb_lower and tech.bb_upper:
            mid = (tech.bb_lower + tech.bb_upper) / 2
            if tech.ma5 < tech.bb_lower:  # 低于下轨
                score += 10
            elif tech.ma5 < mid:  # 低于中轨
                score += 5
        
        return min(score, 100)
    
    def _get_recommendation(self, score: int) -> str:
        """根据评分获取建议"""
        if score >= 80:
            return "strong_buy"
        elif score >= 60:
            return "buy"
        elif score >= 40:
            return "hold"
        elif score >= 20:
            return "sell"
        else:
            return "strong_sell"
    
    def _get_kdj_signal(self, rsi: float) -> str:
        """根据 RSI 判断超买超卖"""
        if rsi > 80:
            return "超买"
        elif rsi < 20:
            return "超卖"
        else:
            return "正常"
    
    def _calculate_score(
        self,
        market_cap: float,
        fund_data: Dict,
        tech_data: Optional[Dict]
    ) -> Dict:
        """计算综合评分"""
        score = 0
        details = []
        
        # 1. 市值筛选（硬筛选）
        if market_cap > 200:
            return {"total": 0, "reason": "市值超过200亿"}
        
        # 2. 实控人筛选（硬筛选）
        # 在调用时检查
        
        # 3. 基本面评分（软筛选）
        if fund_data:
            # PB < 2.5
            pb = fund_data.get("pb", 10)
            if pb < 2.5:
                pb_score = int((2.5 - pb) * 20)
                score += pb_score
                details.append(f"PB={pb:.2f}(+{pb_score})")
            
            # ROE > 10%
            roe = fund_data.get("roe", 0)
            if roe > 10:
                roe_score = int(min(roe - 10, 20))
                score += roe_score
                details.append(f"ROE={roe:.1f}%(+{roe_score})")
            
            # 净利润增长 > 20%
            growth = fund_data.get("net_profit_growth", 0)
            if growth > 20:
                growth_score = int(min(growth - 20, 15))
                score += growth_score
                details.append(f"增长={growth:.1f}%(+{growth_score})")
            
            # 股息率 > 1%
            dividend = fund_data.get("dividend_yield", 0)
            if dividend > 1:
                div_score = int(min(dividend * 3, 10))
                score += div_score
                details.append(f"股息={dividend:.1f}%(+{div_score})")
        
        # 4. 技术面评分
        if tech_data:
            tech_score = tech_data.get("technical_score", 0)
            # 技术评分占比 30%
            normalized_tech = int(tech_score * 0.3)
            score += normalized_tech
            details.append(f"技术={tech_score}(+{normalized_tech})")
            
            # MACD 金叉/多头加分
            if tech_data.get("macd") in ["金叉", "多头"]:
                score += 5
                details.append("MACD多头(+5)")
            
            # KDJ 超卖加分
            if tech_data.get("kdj") == "超卖":
                score += 5
                details.append("KDJ超卖(+5)")
        
        return {
            "total": min(score, 100),
            "details": ", ".join(details) if details else "无加分项",
        }
    
    def scan(self, filter_controller: bool = True) -> List[Dict]:
        """扫描股票池"""
        results = []
        all_codes = [
            code
            for sub_sectors in STOCK_POOL.values()
            for codes in sub_sectors.values()
            for code in codes
        ]
        self.fundamentals = get_fundamental_bundles(all_codes, legacy_data=FUNDAMENTAL_DATA)
        
        print("\n📊 开始扫描股票池...")
        print("=" * 60)
        
        for sector, sub_sectors in STOCK_POOL.items():
            for sub_sector, codes in sub_sectors.items():
                for code in codes:
                    # 检查实控人
                    controller = CONTROLLERS.get(code, ("未知", "未知"))[1]
                    if filter_controller and controller in ["民营企业", "无实控人", "未知"]:
                        continue
                    
                    # 获取数据
                    data = self.get_stock_data(code)
                    if not data:
                        continue
                    
                    data["sector"] = sector
                    data["sub_sector"] = sub_sector
                    results.append(data)
        
        # 按评分排序
        results.sort(key=lambda x: x["score"]["total"], reverse=True)
        
        print(f"\n✅ 扫描完成，共 {len(results)} 只股票符合条件")
        return results
    
    def top(self, n: int = 5, filter_controller: bool = True) -> List[Dict]:
        """显示评分最高的 n 只股票"""
        results = self.scan(filter_controller)
        top_n = [stock for stock in results if float(stock.get("score", {}).get("total", 0) or 0) >= MIN_TOP_CANDIDATE_SCORE][:n]
        
        print(f"\n🏆 TOP {n} 股票：")
        print("=" * 80)
        if not top_n:
            print(f"\n⚠️ 当前没有综合评分达到 {MIN_TOP_CANDIDATE_SCORE} 分的候选股")
            return []
        
        for i, stock in enumerate(top_n, 1):
            score = stock["score"]
            print(f"\n{i}. {stock['name']} ({stock['code']})")
            print(f"   实控人: {stock['controller']}")
            print(f"   行业: {stock['sector']} > {stock['sub_sector']}")
            print(f"   价格: ¥{stock['price']:.2f} ({stock['change_pct']:+.2f}%)")
            print(f"   市值: {stock['market_cap']:.1f}亿")
            print(f"   综合评分: {score['total']}/100")
            print(f"   评分详情: {score.get('details', 'N/A')}")
            
            if stock.get("technical"):
                tech = stock["technical"]
                print(f"   技术面: 评分={tech['technical_score']}, MACD={tech['macd']}, KDJ={tech['kdj']}")
        
        return top_n
    
    def detail(self, code: str) -> Optional[Dict]:
        """查看单只股票详情"""
        data = self.get_stock_data(code)
        if not data:
            print(f"❌ 无法获取 {code} 的数据")
            return None
        
        print(f"\n📋 {data['name']} ({code}) 详情")
        print("=" * 60)
        print(f"实控人: {data['controller']}")
        print(f"行业: {data.get('sector', '未知')} > {data.get('sub_sector', '未知')}")
        print(f"价格: ¥{data['price']:.2f} ({data['change_pct']:+.2f}%)")
        print(f"成交量: {data['volume']:.0f}万手")
        print(f"市值: {data['market_cap']:.1f}亿")
        
        if data.get("fundamentals"):
            fund = data["fundamentals"]
            print(f"\n📊 基本面:")
            print(f"   PB: {fund.get('pb', 'N/A'):.2f}")
            print(f"   PE: {fund.get('pe', 'N/A'):.1f}")
            print(f"   ROE: {fund.get('roe', 'N/A'):.1f}%")
            print(f"   净利润增长: {fund.get('net_profit_growth', 'N/A'):.1f}%")
            print(f"   股息率: {fund.get('dividend_yield', 'N/A'):.2f}%")
        
        if data.get("technical"):
            tech = data["technical"]
            print(f"\n📈 技术面:")
            print(f"   评分: {tech['technical_score']}/100")
            print(f"   建议: {tech['recommendation']}")
            print(f"   MACD: {tech['macd']}")
            print(f"   KDJ: {tech['kdj']}")
            print(f"   RSI: {tech['rsi']:.1f}")
        
        score = data["score"]
        print(f"\n🎯 综合评分: {score['total']}/100")
        print(f"   详情: {score['details']}")
        
        return data


def format_top_report(stocks: List[Dict]) -> str:
    """格式化 Top 候选列表，供飞书卡片发送。"""
    if not stocks:
        return f"今日未筛出综合评分达到 {MIN_TOP_CANDIDATE_SCORE} 分的候选股。"

    lines = [f"共筛出 {len(stocks)} 只达标候选股（综合评分 >= {MIN_TOP_CANDIDATE_SCORE}），按综合评分排序：", ""]
    for index, stock in enumerate(stocks, 1):
        score = stock["score"]
        lines.append(f"{index}. {stock['name']} ({stock['code']})")
        lines.append(f"   评分: {score['total']}/100 | 行业: {stock['sector']} > {stock['sub_sector']}")
        lines.append(f"   价格: ¥{stock['price']:.2f} ({stock['change_pct']:+.2f}%) | 市值: {stock['market_cap']:.1f}亿")
        lines.append(f"   亮点: {score.get('details', '无')}")
        if stock.get("technical"):
            tech = stock["technical"]
            lines.append(f"   技术面: MACD={tech['macd']} | KDJ={tech['kdj']} | 技术评分={tech['technical_score']}")
        lines.append("")

    return "\n".join(lines).strip()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="选股工具 v4（多数据源）")
    parser.add_argument("action", choices=["scan", "top", "detail"], help="操作类型")
    parser.add_argument("arg", nargs="?", help="参数（top: 数量, detail: 股票代码）")
    parser.add_argument("--all", action="store_true", help="包含民企")
    
    args = parser.parse_args()
    
    try:
        with task_lock("selector"):
            guard = evaluate_runtime_mode("selection", universe_count=len(STOCK_POOL))
            for warning in guard.warnings:
                print(f"⚠️ {warning}")
                record_guardrail_event("selector", "warning", warning)
            if not guard.ok:
                for reason in guard.reasons:
                    print(f"⛔ {reason}")
                    record_guardrail_event("selector", "error", reason)
                return

            selector = StockSelector()

            if args.action == "scan":
                selector.scan(filter_controller=not args.all)
                record_guardrail_success("selector", "选股扫描完成")
            elif args.action == "top":
                n = int(args.arg) if args.arg else 5
                top_stocks = selector.top(n, filter_controller=not args.all)
                try:
                    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
                    from feishu_notifier import send_feishu_message

                    send_feishu_message(
                        title=f"🎯 动态标准选股 Top {len(top_stocks)}",
                        content=format_top_report(top_stocks),
                        level="info",
                    )
                    print("✅ 飞书通知已发送")
                except Exception as exc:
                    print(f"⚠️ 飞书通知发送失败: {exc}")
                record_guardrail_success("selector", f"Top 选股完成，共 {len(top_stocks)} 只")
            elif args.action == "detail":
                if not args.arg:
                    print("❌ 请指定股票代码")
                    return
                selector.detail(args.arg)
                record_guardrail_success("selector", f"个股详情完成: {args.arg}")
    except TaskLockedError as exc:
        print(f"⚠️ {exc}")
        record_guardrail_event("selector", "warning", str(exc))


if __name__ == "__main__":
    main()
