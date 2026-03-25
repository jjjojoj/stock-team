#!/usr/bin/env python3
"""
A 股特殊风险监控系统

功能：
1. 涨跌停监控（价格=涨跌停价）
2. 停牌监控（交易状态=停牌）
3. T+1 仓位管理（当日买入不可卖出）
4. 政策风险监控（证监会/交易所公告）
5. 飞书通知

A 股特殊规则：
- 主板涨跌停：±10%
- 科创板/创业板：±20%
- ST 股票：±5%
- T+1 交易：当日买入不可卖出
- 临时停牌：涨幅偏离值达 7% 等
"""

import sys
import os
import json
import glob
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

from core.storage import load_positions, load_watchlist

# 配置
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'a_share_risk.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AShareRiskMonitor:
    """A 股风险监控器"""
    
    # 涨跌停限制
    PRICE_LIMITS = {
        "main": 0.10,       # 主板 10%
        "star": 0.20,       # 科创板 20%
        "chinext": 0.20,    # 创业板 20%
        "st": 0.05,         # ST 股票 5%
    }
    POLICY_KEYWORDS = [
        "证监会", "交易所", "上交所", "深交所", "监管", "问询", "调查", "处罚",
        "停牌", "退市", "减持", "出口管制", "关税", "限制", "整顿", "核查",
    ]
    POLICY_RISK_TERMS = [
        "调查", "处罚", "退市", "停牌", "问询", "核查", "减持", "出口管制", "关税", "限制",
    ]
    POLICY_SOURCE_KEYWORDS = ["证监会", "交易所", "上交所", "深交所", "公告", "监管"]
    
    def __init__(self):
        self.config = self._load_config()
        self.positions_file = os.path.join(DATA_DIR, "positions_today.json")
        self.positions_today = self._load_positions()
    
    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = os.path.join(CONFIG_DIR, "a_share_risk.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "enabled": True,
            "monitor_limit_down": True,
            "monitor_suspension": True,
            "monitor_policy": True,
        }
    
    def _load_positions(self) -> Dict:
        """加载今日持仓（T+1 管理）"""
        if os.path.exists(self.positions_file):
            with open(self.positions_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"buys": []}  # 今日买入列表
    
    def _save_positions(self):
        """保存今日持仓"""
        with open(self.positions_file, 'w', encoding='utf-8') as f:
            json.dump(self.positions_today, f, ensure_ascii=False, indent=2)
    
    def get_stock_info(self, stock_code: str) -> Dict:
        """
        获取股票信息（判断板块、是否 ST 等）
        
        Args:
            stock_code: 股票代码（如 sh.600459）
        
        Returns:
            股票信息
        """
        try:
            # 解析股票代码
            if stock_code.startswith("sh.60") or stock_code.startswith("sz.00"):
                board = "main"
            elif stock_code.startswith("sh.68"):
                board = "star"  # 科创板
            elif stock_code.startswith("sz.30"):
                board = "chinext"  # 创业板
            else:
                board = "main"
            
            # 获取股票名称（判断是否 ST）
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": stock_code.replace(".", ""),
                "fields": "f58"
            }
            response = requests.get(url, params=params, timeout=10)
            
            name = ""
            is_st = False
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    name = data["data"].get("f58", "")
                    is_st = "ST" in name or "*ST" in name
            
            # 确定涨跌停限制
            if is_st:
                limit = self.PRICE_LIMITS["st"]
            else:
                limit = self.PRICE_LIMITS.get(board, 0.10)
            
            return {
                "code": stock_code,
                "name": name,
                "board": board,
                "is_st": is_st,
                "price_limit": limit,
            }
        except Exception as e:
            logger.error(f"获取股票信息失败：{stock_code} - {e}")
            return {
                "code": stock_code,
                "name": "",
                "board": "main",
                "is_st": False,
                "price_limit": 0.10,
            }
    
    def check_limit_up_down(self, stock_code: str, current_price: float, 
                            prev_close: float) -> Dict:
        """
        检查涨跌停
        
        Returns:
            {
                "status": "normal" | "limit_up" | "limit_down" | "near_limit",
                "limit_price": 涨跌停价，
                "distance": 距离涨跌停的百分比，
            }
        """
        stock_info = self.get_stock_info(stock_code)
        limit = stock_info["price_limit"]
        
        # 计算涨跌停价
        limit_up = prev_close * (1 + limit)
        limit_down = prev_close * (1 - limit)
        
        # 计算距离
        distance_to_up = (limit_up - current_price) / current_price * 100
        distance_to_down = (current_price - limit_down) / current_price * 100
        
        # 判断状态
        if abs(distance_to_up) < 0.5:  # 距离涨停<0.5%
            status = "limit_up"
        elif abs(distance_to_down) < 0.5:  # 距离跌停<0.5%
            status = "limit_down"
        elif distance_to_up < 2:  # 距离涨停<2%
            status = "near_limit_up"
        elif distance_to_down < 2:  # 距离跌停<2%
            status = "near_limit_down"
        else:
            status = "normal"
        
        return {
            "status": status,
            "limit_up": round(limit_up, 2),
            "limit_down": round(limit_down, 2),
            "distance_to_up": round(distance_to_up, 2),
            "distance_to_down": round(distance_to_down, 2),
            "stock_info": stock_info,
        }
    
    def check_suspension(self, stock_code: str) -> bool:
        """
        检查是否停牌
        
        Returns:
            是否停牌
        """
        try:
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": stock_code.replace(".", ""),
                "fields": "f168"  # 交易状态
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    # f168: 0=交易，1=停牌
                    status = data["data"].get("f168", 0)
                    return status == 1
            return False
        except Exception as e:
            logger.error(f"检查停牌失败：{stock_code} - {e}")
            return False
    
    def record_buy(self, stock_code: str, stock_name: str, price: float, shares: int):
        """
        记录今日买入（用于 T+1 管理）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            price: 买入价格
            shares: 买入数量
        """
        self.positions_today["buys"].append({
            "code": stock_code,
            "name": stock_name,
            "price": price,
            "shares": shares,
            "time": datetime.now().isoformat(),
        })
        self._save_positions()
        logger.info(f"记录买入：{stock_name} ({stock_code}) {shares}股 @ {price}")
    
    def can_sell(self, stock_code: str) -> Tuple[bool, str]:
        """
        检查是否可以卖出（T+1 规则）
        
        Returns:
            (是否可以卖出，原因)
        """
        # 检查是否是今日买入
        for buy in self.positions_today.get("buys", []):
            if buy["code"] == stock_code:
                return False, f"T+1 限制：{buy['name']} 今日买入，不可卖出"
        
        # 检查是否停牌
        if self.check_suspension(stock_code):
            return False, "股票停牌，不可卖出"
        
        return True, "可以卖出"
    
    def check_policy_risk(self) -> List[Dict]:
        """
        检查政策风险（监控证监会/交易所公告）
        
        Returns:
            政策风险列表
        """
        risks = []

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            logger.info(f"检查政策风险 ({today})...")

            watchlist = load_watchlist({})
            positions = load_positions({})
            tracked_targets = {
                **{
                    code: {
                        "name": info.get("name", code),
                        "industry": info.get("industry", ""),
                    }
                    for code, info in watchlist.items()
                },
                **{
                    code: {
                        "name": info.get("name", code),
                        "industry": info.get("industry", ""),
                    }
                    for code, info in positions.items()
                },
            }

            news_items = self._load_recent_policy_news()
            for item in news_items:
                title = str(item.get("title", "") or "")
                content = str(item.get("content", "") or "")
                signal_text = f"{title} {content[:240]}"
                source = str(item.get("source", "") or "")

                title_has_policy_term = any(keyword in title for keyword in self.POLICY_KEYWORDS)
                source_is_policy = any(keyword in source for keyword in self.POLICY_SOURCE_KEYWORDS)
                text_has_risk_term = any(keyword in signal_text for keyword in self.POLICY_RISK_TERMS)

                if not (title_has_policy_term or (source_is_policy and text_has_risk_term)):
                    continue

                affected = []
                for code, info in tracked_targets.items():
                    name = str(info.get("name", "") or "")
                    industry = str(info.get("industry", "") or "")
                    if (name and name in signal_text) or (industry and industry in signal_text):
                        affected.append({"code": code, "name": name, "industry": industry})

                if not affected:
                    continue

                severity = "high" if any(term in signal_text for term in self.POLICY_RISK_TERMS) else "warning"
                risks.append(
                    {
                        "title": title or "政策相关风险",
                        "source": source,
                        "url": item.get("url", ""),
                        "severity": severity,
                        "affected": affected,
                    }
                )

        except Exception as e:
            logger.error(f"检查政策风险失败：{e}")

        return risks

    def _load_recent_policy_news(self) -> List[Dict]:
        """Load recent searchable news from daily_search artifacts."""
        items: List[Dict] = []
        daily_search_dir = os.path.join(DATA_DIR, "daily_search")
        json_files = sorted(glob.glob(os.path.join(daily_search_dir, "[0-9]" * 8 + ".json")))
        if not json_files:
            return items

        latest_file = json_files[-1]
        with open(latest_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        for bucket_name, bucket in payload.items():
            if not isinstance(bucket, dict):
                continue
            for keyword, rows in bucket.items():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    items.append(
                        {
                            "source_bucket": bucket_name,
                            "source": keyword,
                            "title": row.get("title", ""),
                            "content": row.get("content", ""),
                            "url": row.get("url", ""),
                        }
                    )

        return items
    
    def send_feishu_notification(self, message: str, level: str = "warning"):
        """发送飞书通知"""
        try:
            emoji = "⚠️" if level == "warning" else "🚨"
            sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
            from feishu_notifier import send_alert_card

            send_alert_card(title=f"{emoji} A 股风险预警", content=message, level=level)
            logger.info("飞书通知发送成功")
        except Exception as e:
            logger.error(f"发送飞书通知失败：{e}")
    
    def run_check(self, stock_list: List[str] = None) -> Dict:
        """
        运行风险检查
        
        Args:
            stock_list: 要检查的股票列表
        
        Returns:
            检查结果
        """
        if not stock_list:
            # 从持仓和自选股加载
            stock_list = self._load_watchlist()
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "stocks_checked": len(stock_list),
            "limit_down": [],
            "limit_up": [],
            "suspended": [],
            "policy_risks": [],
            "t1_restrictions": [],
        }
        
        for stock_code in stock_list:
            try:
                # 获取股票数据
                url = "http://push2.eastmoney.com/api/qt/stock/get"
                params = {
                    "secid": stock_code.replace(".", ""),
                    "fields": "f43,f107,f168"
                }
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        price = data["data"].get("f43", 0) / 100
                        change_pct = data["data"].get("f107", 0)
                        
                        # 检查涨跌停
                        limit_result = self.check_limit_up_down(stock_code, price, price / (1 + change_pct/100))
                        
                        if limit_result["status"] == "limit_down":
                            results["limit_down"].append({
                                "code": stock_code,
                                "name": limit_result["stock_info"]["name"],
                                "price": price,
                                "change_pct": change_pct,
                            })
                            # 发送通知
                            self.send_feishu_notification(
                                f"跌停预警：{limit_result['stock_info']['name']} ({stock_code})\n"
                                f"当前价：¥{price:.2f} ({change_pct:+.1f}%)\n"
                                f"跌停价：¥{limit_result['limit_down']:.2f}\n"
                                f"⚠️ 如持仓，明日可能无法卖出"
                            )
                        
                        elif limit_result["status"] == "limit_up":
                            results["limit_up"].append({
                                "code": stock_code,
                                "name": limit_result["stock_info"]["name"],
                                "price": price,
                                "change_pct": change_pct,
                            })
                        
                        # 检查停牌
                        if self.check_suspension(stock_code):
                            results["suspended"].append({
                                "code": stock_code,
                                "name": limit_result["stock_info"]["name"],
                            })
                            self.send_feishu_notification(
                                f"停牌预警：{limit_result['stock_info']['name']} ({stock_code})\n"
                                f"⚠️ 停牌期间无法交易"
                            )
                        
                        # 检查 T+1 限制
                        can_sell, reason = self.can_sell(stock_code)
                        if not can_sell:
                            results["t1_restrictions"].append({
                                "code": stock_code,
                                "reason": reason,
                            })
            except Exception as e:
                logger.error(f"检查股票失败：{stock_code} - {e}")
        
        # 检查政策风险
        results["policy_risks"] = self.check_policy_risk()
        for policy_risk in results["policy_risks"]:
            affected_names = "、".join(item["name"] or item["code"] for item in policy_risk.get("affected", [])[:5])
            self.send_feishu_notification(
                f"政策/监管风险：{policy_risk['title']}\n"
                f"影响标的：{affected_names}\n"
                f"来源：{policy_risk.get('source', '未知')}\n"
                f"{policy_risk.get('url', '')}".strip(),
                level=policy_risk.get("severity", "warning"),
            )
        
        logger.info(f"A 股风险检查完成：跌停{len(results['limit_down'])}只，停牌{len(results['suspended'])}只")
        
        return results
    
    def _load_watchlist(self) -> List[str]:
        """加载持仓和自选股"""
        stocks = []

        positions = load_positions({})
        stocks.extend(list(positions.keys()))
        logger.info(f"加载持仓股票 {len(positions)} 只")

        watchlist = load_watchlist({})
        for code in watchlist.keys():
            if code not in stocks:
                stocks.append(code)
        logger.info(f"加载自选股 {len(watchlist)} 只")
        
        return stocks


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A 股风险监控")
    parser.add_argument("action", choices=["check", "verify", "record_buy"],
                       help="check=检查，verify=测试，record_buy=记录买入")
    parser.add_argument("--stock", type=str, help="股票代码（record_buy 时使用）")
    parser.add_argument("--price", type=float, help="买入价格")
    parser.add_argument("--shares", type=int, help="买入数量")
    
    args = parser.parse_args()
    
    monitor = AShareRiskMonitor()
    
    if args.action == "check":
        # 运行检查
        results = monitor.run_check()
        
        print("\n" + "="*60)
        print("🔍 A 股风险检查结果")
        print("="*60)
        print(f"检查股票：{results['stocks_checked']}只")
        print(f"时间：{results['timestamp']}")
        print()
        
        if results["limit_down"]:
            print(f"🔴 跌停股票 ({len(results['limit_down'])}):")
            for s in results["limit_down"]:
                print(f"   {s['name']} ({s['code']}): ¥{s['price']:.2f} ({s['change_pct']:+.1f}%)")
            print()
        
        if results["limit_up"]:
            print(f"🟢 涨停股票 ({len(results['limit_up'])}):")
            for s in results["limit_up"]:
                print(f"   {s['name']} ({s['code']}): ¥{s['price']:.2f} ({s['change_pct']:+.1f}%)")
            print()
        
        if results["suspended"]:
            print(f"⚠️  停牌股票 ({len(results['suspended'])}):")
            for s in results["suspended"]:
                print(f"   {s['name']} ({s['code']})")
            print()
        
        if results["t1_restrictions"]:
            print(f"📅 T+1 限制 ({len(results['t1_restrictions'])}):")
            for r in results["t1_restrictions"]:
                print(f"   {r['code']}: {r['reason']}")
            print()

        if results["policy_risks"]:
            print(f"📰 政策风险 ({len(results['policy_risks'])}):")
            for risk in results["policy_risks"]:
                affected = "、".join(item["name"] or item["code"] for item in risk.get("affected", [])[:3])
                print(f"   {risk['title']} -> {affected}")
            print()
        
        if not any([results["limit_down"], results["limit_up"], 
                    results["suspended"], results["t1_restrictions"], results["policy_risks"]]):
            print("✅ 无风险，一切正常")
        
        print("="*60)
    
    elif args.action == "verify":
        # 测试
        print("\n🧪 A 股风险监控测试")
        print("="*60)
        
        # 测试 1：股票信息
        print("\n1. 测试股票信息识别...")
        verify_stocks = ["sh.600459", "sh.688001", "sz.300001", "sz.000758"]
        for code in verify_stocks:
            info = monitor.get_stock_info(code)
            print(f"   {code}: {info['name']} | 板块={info['board']} | ST={info['is_st']} | 限制={info['price_limit']*100:.0f}%")
        
        # 测试 2：涨跌停检查
        print("\n2. 测试涨跌停检查...")
        verify_cases = [
            ("sh.600459", 28.0, 26.0, "涨停测试"),
            ("sh.600459", 23.0, 26.0, "跌停测试"),
            ("sh.600459", 26.0, 26.0, "正常"),
        ]
        for code, price, prev_close, desc in verify_cases:
            result = monitor.check_limit_up_down(code, price, prev_close)
            print(f"   {desc}: {code} ¥{price:.2f} → 状态={result['status']}")
        
        # 测试 3：T+1 管理
        print("\n3. 测试 T+1 管理...")
        monitor.record_buy("sh.600459", "贵研铂业", 26.27, 1000)
        can_sell, reason = monitor.can_sell("sh.600459")
        print(f"   今日买入后尝试卖出：can_sell={can_sell}, reason={reason}")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)
    
    elif args.action == "record_buy":
        if not args.stock or not args.price or not args.shares:
            print("❌ 用法：python3 a_share_risk_monitor.py record_buy --stock <代码> --price <价格> --shares <数量>")
            sys.exit(1)
        
        monitor.record_buy(args.stock, "", args.price, args.shares)
        print(f"✅ 已记录买入：{args.stock} {args.shares}股 @ ¥{args.price:.2f}")


if __name__ == "__main__":
    main()
