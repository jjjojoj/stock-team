#!/usr/bin/env python3
"""
事件驱动交易系统
根据重大事件（战争、疫情、政策等）自动决策买入

工作流程：
1. 检测重大事件（地缘政治、政策、疫情等）
2. 映射到受益行业
3. 筛选相关股票
4. 计算仓位和买入金额
5. 输出买入建议（飞书通知）
6. [预留] 执行买入（券商API）
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"

# ============================================================
# 事件 → 行业映射
# ============================================================

EVENT_STRATEGIES = {
    "war_middle_east": {
        "name": "中东冲突",
        "severity_levels": {
            "low": {"position_pct": 0.10},     # 小冲突 → 10%仓位
            "medium": {"position_pct": 0.20},  # 升级 → 20%仓位
            "high": {"position_pct": 0.30},    # 战争 → 30%仓位
        },
        "sectors": {
            "油气": {
                "weight": 0.5,  # 50%资金
                "stocks": [
                    {"code": "sh.600028", "name": "中国石化", "reason": "国内最大炼油企业"},
                    {"code": "sh.600256", "name": "广汇能源", "reason": "LNG进口"},
                ]
            },
            "黄金": {
                "weight": 0.3,
                "stocks": [
                    {"code": "sz.002155", "name": "辰州矿业", "reason": "黄金+锑"},
                ]
            },
            "军工": {
                "weight": 0.2,
                "stocks": [
                    {"code": "sz.000768", "name": "中航飞机", "reason": "军机龙头"},
                ]
            }
        }
    },
    
    "trade_war": {
        "name": "贸易战",
        "severity_levels": {
            "low": {"position_pct": 0.05},
            "medium": {"position_pct": 0.10},
            "high": {"position_pct": 0.15},
        },
        "sectors": {
            "稀土": {
                "weight": 0.5,
                "stocks": [
                    {"code": "sh.600111", "name": "北方稀土", "reason": "稀土龙头"},
                    {"code": "sz.000831", "name": "中国稀土", "reason": "中重稀土"},
                ]
            },
            "农业": {
                "weight": 0.3,
                "stocks": [
                    {"code": "sz.000876", "name": "新希望", "reason": "饲料龙头"},
                ]
            },
            "国产替代": {
                "weight": 0.2,
                "stocks": [
                    {"code": "sz.002049", "name": "紫光国微", "reason": "芯片"},
                ]
            }
        }
    },
    
    "pandemic": {
        "name": "疫情",
        "severity_levels": {
            "low": {"position_pct": 0.03},
            "medium": {"position_pct": 0.08},
            "high": {"position_pct": 0.12},
        },
        "sectors": {
            "医药": {
                "weight": 0.5,
                "stocks": [
                    {"code": "sz.300122", "name": "智飞生物", "reason": "疫苗"},
                    {"code": "sh.603259", "name": "药明康德", "reason": "CRO龙头"},
                ]
            },
            "在线经济": {
                "weight": 0.3,
                "stocks": [
                    {"code": "sh.603444", "name": "吉比特", "reason": "游戏"},
                ]
            },
            "生鲜": {
                "weight": 0.2,
                "stocks": [
                    {"code": "sz.002124", "name": "天邦食品", "reason": "猪肉"},
                ]
            }
        }
    },
    
    "rate_cut": {
        "name": "降息",
        "severity_levels": {
            "low": {"position_pct": 0.05},
            "medium": {"position_pct": 0.10},
            "high": {"position_pct": 0.15},
        },
        "sectors": {
            "房地产": {
                "weight": 0.4,
                "stocks": [
                    {"code": "sz.000002", "name": "万科A", "reason": "地产龙头"},
                ]
            },
            "高股息": {
                "weight": 0.6,
                "stocks": [
                    {"code": "sh.601318", "name": "中国平安", "reason": "保险龙头"},
                    {"code": "sh.601288", "name": "农业银行", "reason": "银行股息"},
                ]
            }
        }
    }
}

# ============================================================
# 风险控制
# ============================================================

RISK_RULES = {
    "max_single_stock_pct": 0.15,     # 单只股票最大15%
    "max_industry_pct": 0.30,         # 单行业最大30%
    "max_total_position_pct": 0.80,   # 总仓位最大80%
    "min_cash_reserve_pct": 0.20,     # 保留20%现金
}

# ============================================================
# 核心类
# ============================================================

class EventTrader:
    """事件驱动交易系统"""
    
    def __init__(self):
        self.events_file = DATA_DIR / "events" / "detected_events.json"
        self.trades_file = DATA_DIR / "event_trades.json"
        self.positions_file = CONFIG_DIR / "positions.json"
        self.portfolio_file = CONFIG_DIR / "portfolio.json"
        
        self._ensure_dirs()
        self._load_portfolio()
    
    def _ensure_dirs(self):
        """确保目录存在"""
        (DATA_DIR / "events").mkdir(parents=True, exist_ok=True)
    
    def _load_portfolio(self):
        """加载账户信息"""
        # 尝试加载账户配置
        if self.portfolio_file.exists():
            with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                self.portfolio = json.load(f)
        else:
            # 默认配置
            self.portfolio = {
                "total_capital": 100000,  # 总资金 10万
                "available_cash": 100000,  # 可用现金
                "positions": {}  # 当前持仓
            }
            self._save_portfolio()
    
    def _save_portfolio(self):
        """保存账户信息"""
        with open(self.portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(self.portfolio, f, ensure_ascii=False, indent=2)
    
    def detect_event(self, event_type: str, severity: str = "medium", 
                     source: str = "", details: str = "") -> Dict:
        """
        检测到重大事件
        
        Args:
            event_type: 事件类型（war_middle_east, trade_war, pandemic, rate_cut）
            severity: 严重程度（low, medium, high）
            source: 消息来源
            details: 事件详情
        
        Returns:
            事件记录
        """
        if event_type not in EVENT_STRATEGIES:
            print(f"未知事件类型: {event_type}")
            return None
        
        event = {
            "id": f"{event_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "type": event_type,
            "name": EVENT_STRATEGIES[event_type]["name"],
            "severity": severity,
            "source": source,
            "details": details,
            "detected_at": datetime.now().isoformat(),
            "processed": False
        }
        
        # 保存事件
        self._save_event(event)
        
        print(f"\n🚨 检测到重大事件: {event['name']} (严重程度: {severity})")
        print(f"   来源: {source}")
        print(f"   详情: {details}")
        
        return event
    
    def _save_event(self, event: Dict):
        """保存事件记录"""
        events = []
        if self.events_file.exists():
            with open(self.events_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
        
        events.append(event)
        
        with open(self.events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    
    def analyze_and_decide(self, event_id: str) -> Dict:
        """
        分析事件并生成买入决策
        
        Args:
            event_id: 事件ID
        
        Returns:
            买入决策
        """
        # 加载事件
        events = []
        if self.events_file.exists():
            with open(self.events_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
        
        event = next((e for e in events if e["id"] == event_id), None)
        if not event:
            print(f"未找到事件: {event_id}")
            return None
        
        if event["processed"]:
            print(f"事件已处理: {event_id}")
            return None
        
        strategy = EVENT_STRATEGIES[event["type"]]
        severity_config = strategy["severity_levels"][event["severity"]]
        
        # 计算可用资金
        total_capital = self.portfolio["total_capital"]
        available_cash = self.portfolio["available_cash"]
        event_position = total_capital * severity_config["position_pct"]
        
        # 检查是否有足够现金
        if available_cash < event_position:
            print(f"⚠️ 可用现金不足: {available_cash:.0f} < {event_position:.0f}")
            event_position = available_cash * 0.9  # 使用90%可用现金
        
        print(f"\n💰 资金分配:")
        print(f"   总资金: ¥{total_capital:,.0f}")
        print(f"   可用现金: ¥{available_cash:,.0f}")
        print(f"   事件仓位: ¥{event_position:,.0f} ({severity_config['position_pct']*100:.0f}%)")
        
        # 生成买入建议
        buy_orders = []
        
        for sector_name, sector_config in strategy["sectors"].items():
            sector_amount = event_position * sector_config["weight"]
            
            print(f"\n📊 行业: {sector_name}")
            print(f"   分配资金: ¥{sector_amount:,.0f} ({sector_config['weight']*100:.0f}%)")
            
            # 平均分配给该行业的股票
            stocks = sector_config["stocks"]
            amount_per_stock = sector_amount / len(stocks)
            
            for stock in stocks:
                # 风险检查：单只股票仓位
                current_position = self.portfolio["positions"].get(stock["code"], {}).get("value", 0)
                max_position = total_capital * RISK_RULES["max_single_stock_pct"]
                
                if current_position + amount_per_stock > max_position:
                    amount_per_stock = max_position - current_position
                    if amount_per_stock <= 0:
                        print(f"   ⚠️ {stock['name']}: 已达仓位上限，跳过")
                        continue
                
                buy_orders.append({
                    "code": stock["code"],
                    "name": stock["name"],
                    "sector": sector_name,
                    "amount": amount_per_stock,
                    "reason": stock["reason"],
                    "event": event["name"],
                    "event_id": event_id
                })
                
                print(f"   ✅ {stock['name']}: ¥{amount_per_stock:,.0f} - {stock['reason']}")
        
        # 汇总
        decision = {
            "event_id": event_id,
            "event_name": event["name"],
            "event_severity": event["severity"],
            "total_capital": total_capital,
            "available_cash": available_cash,
            "event_position": event_position,
            "buy_orders": buy_orders,
            "total_buy_amount": sum(o["amount"] for o in buy_orders),
            "created_at": datetime.now().isoformat(),
            "executed": False
        }
        
        # 保存决策
        self._save_decision(decision)
        
        # 标记事件已处理
        event["processed"] = True
        with open(self.events_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        
        print(f"\n📝 买入建议已生成，共 {len(buy_orders)} 只股票")
        print(f"   总买入金额: ¥{decision['total_buy_amount']:,.0f}")
        
        return decision
    
    def _save_decision(self, decision: Dict):
        """保存交易决策"""
        decisions = []
        if self.trades_file.exists():
            with open(self.trades_file, 'r', encoding='utf-8') as f:
                decisions = json.load(f)
        
        decisions.append(decision)
        
        with open(self.trades_file, 'w', encoding='utf-8') as f:
            json.dump(decisions, f, ensure_ascii=False, indent=2)
    
    def generate_report(self, decision_id: str = None) -> str:
        """
        生成买入建议报告（详细版）
        
        Args:
            decision_id: 决策ID，None则取最新
        
        Returns:
            报告文本
        """
        if not self.trades_file.exists():
            return "暂无买入建议"
        
        with open(self.trades_file, 'r', encoding='utf-8') as f:
            decisions = json.load(f)
        
        if decision_id:
            decision = next((d for d in decisions if d["event_id"] == decision_id), None)
        else:
            decision = decisions[-1] if decisions else None
        
        if not decision:
            return "未找到买入建议"
        
        lines = [
            f"🚨 **事件驱动买入建议**",
            f"",
            f"**事件**: {decision['event_name']} ({decision['event_severity']})",
            f"**时间**: {decision['created_at'][:19]}",
            f"",
            f"💰 **资金分配**:",
            f"- 总资金: ¥{decision['total_capital']:,.0f}",
            f"- 可用现金: ¥{decision['available_cash']:,.0f}",
            f"- 本次买入: ¥{decision['total_buy_amount']:,.0f}",
            f"",
            f"📈 **买入清单** ({len(decision['buy_orders'])}只):",
        ]
        
        # 按行业分组
        sectors = {}
        for order in decision['buy_orders']:
            if order['sector'] not in sectors:
                sectors[order['sector']] = []
            sectors[order['sector']].append(order)
        
        for sector, orders in sectors.items():
            lines.append(f"\n**{sector}**:")
            for order in orders:
                lines.append(f"- {order['name']} ({order['code']}): ¥{order['amount']:,.0f}")
                lines.append(f"  理由: {order['reason']}")
        
        lines.append("")
        lines.append("⚠️ **风险提示**:")
        lines.append("- 以上建议基于事件驱动策略，不保证收益")
        lines.append("- 请根据实际情况决定是否执行")
        lines.append("- 建议分批买入，控制仓位")
        
        return "\n".join(lines)
    
    def generate_feishu_report(self) -> str:
        """
        生成飞书简报（简化版）
        只包含：持股、买卖、理由、收益
        """
        # 获取当前持仓
        positions = self._get_current_positions()
        
        # 获取今日交易
        trades = self._get_today_trades()
        
        # 计算总收益
        total_cost = 0
        total_value = 0
        positions_detail = []
        
        for code, pos in positions.items():
            cost = pos['shares'] * pos['cost_price']
            value = pos['shares'] * pos.get('current_price', pos['cost_price'])
            pnl = value - cost
            pnl_pct = (value / cost - 1) * 100 if cost > 0 else 0
            
            total_cost += cost
            total_value += value
            
            positions_detail.append({
                "name": pos['name'],
                "shares": pos['shares'],
                "cost": pos['cost_price'],
                "current": pos.get('current_price', pos['cost_price']),
                "pnl": pnl,
                "pnl_pct": pnl_pct
            })
        
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0
        
        # 生成报告
        lines = [
            "📊 **持仓简报**",
            "",
            f"**当前持股** ({len(positions)}只):",
        ]
        
        for pos in positions_detail:
            emoji = "🟢" if pos['pnl'] >= 0 else "🔴"
            lines.append(
                f"{emoji} {pos['name']}: {pos['shares']}股 "
                f"@¥{pos['cost']:.2f} → ¥{pos['current']:.2f} "
                f"({pos['pnl_pct']:+.1f}%)"
            )
        
        lines.append("")
        lines.append(f"💰 **总收益**: ¥{total_pnl:,.0f} ({total_pnl_pct:+.1f}%)")
        
        # 今日交易
        if trades:
            lines.append("")
            lines.append(f"📝 **今日交易**:")
            for trade in trades:
                action_emoji = "🟢" if trade['action'] == 'BUY' else "🔴"
                lines.append(
                    f"{action_emoji} {trade['action']}: {trade['name']} "
                    f"{trade['shares']}股 @¥{trade['price']:.2f}"
                )
                if trade.get('reason'):
                    lines.append(f"   理由: {trade['reason']}")
        
        return "\n".join(lines)
    
    def _get_current_positions(self) -> Dict:
        """从 Dashboard API 获取当前持仓"""
        import urllib.request
        
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:5000/api/positions",
                headers={'User-Agent': 'EventTrader/1.0'}
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except:
            # 从本地文件读取
            if self.positions_file.exists():
                with open(self.positions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
    
    def _get_today_trades(self) -> List[Dict]:
        """获取今日交易记录"""
        history_file = DATA_DIR / "trade_history.json"
        
        if not history_file.exists():
            return []
        
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # 筛选今日交易
        today = datetime.now().strftime('%Y-%m-%d')
        today_trades = [t for t in history if t['time'].startswith(today)]
        
        return today_trades
    
    def execute_buy(self, decision_id: str, dry_run: bool = False) -> Dict:
        """
        执行买入（调用本地 Dashboard API）
        
        Args:
            decision_id: 决策ID
            dry_run: 是否实战运行（不实际下单）
        
        Returns:
            执行结果
        """
        with open(self.trades_file, 'r', encoding='utf-8') as f:
            decisions = json.load(f)
        
        decision = next((d for d in decisions if d["event_id"] == decision_id), None)
        if not decision:
            return {"success": False, "error": "未找到决策"}
        
        if decision["executed"]:
            return {"success": False, "error": "决策已执行"}
        
        results = []
        
        # 获取实时价格
        prices = self._get_realtime_prices([o["code"] for o in decision["buy_orders"]])
        
        for order in decision["buy_orders"]:
            code = order["code"]
            name = order["name"]
            amount = order["amount"]
            
            # 获取当前价格
            current_price = prices.get(code, 0)
            if current_price <= 0:
                results.append({
                    "code": code,
                    "name": name,
                    "status": "failed",
                    "error": "无法获取价格"
                })
                continue
            
            # 计算买入股数（100股为一手）
            shares = int(amount / current_price / 100) * 100
            
            if shares < 100:
                results.append({
                    "code": code,
                    "name": name,
                    "status": "skipped",
                    "error": f"资金不足（需要 ¥{current_price * 100:.0f}）"
                })
                continue
            
            if dry_run:
                # 实战买入
                results.append({
                    "code": code,
                    "name": name,
                    "status": "simulated",
                    "shares": shares,
                    "price": current_price,
                    "amount": shares * current_price,
                    "message": "实战买入成功"
                })
            else:
                # 调用 Dashboard API 买入
                result = self._call_dashboard_api("buy", {
                    "code": code,
                    "name": name,
                    "shares": shares,
                    "price": current_price,
                    "target_price": round(current_price * 1.3, 2),
                    "stop_loss": round(current_price * 0.92, 2),
                    "industry": order["sector"]
                })
                
                if result and result.get("success"):
                    results.append({
                        "code": code,
                        "name": name,
                        "status": "success",
                        "shares": shares,
                        "price": current_price,
                        "amount": shares * current_price,
                        "message": "买入成功"
                    })
                else:
                    results.append({
                        "code": code,
                        "name": name,
                        "status": "failed",
                        "error": result.get("error", "API调用失败") if result else "API调用失败"
                    })
        
        # 更新决策状态
        decision["executed"] = True
        decision["execution_time"] = datetime.now().isoformat()
        decision["execution_results"] = results
        decision["dry_run"] = dry_run
        with open(self.trades_file, 'w', encoding='utf-8') as f:
            json.dump(decisions, f, ensure_ascii=False, indent=2)
        
        # 更新账户资金
        if not dry_run:
            total_cost = sum(r.get("amount", 0) for r in results if r.get("status") == "success")
            self.portfolio["available_cash"] -= total_cost
            self._save_portfolio()
            
            # 记录交易到学习系统（2026-03-07 新增）
            self._record_trade_learning(decision, results)
        
        return {
            "success": True,
            "dry_run": dry_run,
            "results": results,
            "total_cost": sum(r.get("amount", 0) for r in results if r.get("status") == "success")
        }
    
    def _record_trade_learning(self, decision: Dict, results: List[Dict]):
        """
        记录交易到学习系统（2026-03-07 新增）
        
        功能：
        1. 记录交易详情到 daily_learning_log.json
        2. 如交易成功，提取模式 → memory.md
        3. 如交易失败，提取教训 → memory.md
        """
        import json
        from datetime import datetime
        
        learning_dir = PROJECT_ROOT / "learning"
        learning_log = learning_dir / "daily_learning_log.json"
        
        # 准备交易记录
        trade_record = {
            "date": datetime.now().isoformat(),
            "type": "event_trade",
            "event_id": decision.get("id"),
            "event_type": decision.get("event_type"),
            "event_name": decision.get("event", {}).get("name"),
            "severity": decision.get("event", {}).get("severity"),
            "trades": [],
            "total_cost": sum(r.get("amount", 0) for r in results if r.get("status") == "success"),
            "success_count": sum(1 for r in results if r.get("status") == "success"),
            "failed_count": sum(1 for r in results if r.get("status") == "failed")
        }
        
        # 记录每笔交易
        for result in results:
            if result.get("status") == "success":
                trade_record["trades"].append({
                    "code": result.get("code"),
                    "name": result.get("name"),
                    "action": "buy",
                    "price": result.get("price"),
                    "shares": result.get("shares"),
                    "amount": result.get("amount"),
                    "reason": decision.get("event", {}).get("name"),
                    "status": "opened"
                })
        
        # 读取现有日志
        logs = []
        if learning_log.exists():
            with open(learning_log, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(trade_record)
        
        # 只保留最近 50 条
        if len(logs) > 50:
            logs = logs[-50:]
        
        with open(learning_log, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 交易学习记录已保存：{trade_record['success_count']} 笔成功，{trade_record['failed_count']} 笔失败")
    
    def _get_realtime_prices(self, codes: List[str]) -> Dict[str, float]:
        """获取实时价格"""
        import urllib.request
        
        prices = {}
        
        # 转换代码格式
        url_codes = []
        for code in codes:
            market = 'sh' if code.startswith('sh') else 'sz'
            stock_code = code.split('.')[1]
            url_codes.append(f"{market}{stock_code}")
        
        # 批量获取
        url = f"http://qt.gtimg.cn/q={','.join(url_codes)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                text = response.read().decode("gbk")
                
            for line in text.strip().split('\n'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                stock_code = parts[2]
                price = float(parts[3])
                
                # 匹配回原始代码
                for code in codes:
                    if code.endswith(stock_code):
                        prices[code] = price
                        break
        except Exception as e:
            print(f"获取价格失败: {e}")
        
        return prices
    
    def _call_dashboard_api(self, action: str, data: Dict) -> Optional[Dict]:
        """调用 Dashboard API"""
        import urllib.request
        
        api_urls = {
            "buy": "http://127.0.0.1:5000/api/trade/buy",
            "sell": "http://127.0.0.1:5000/api/trade/sell",
            "positions": "http://127.0.0.1:5000/api/positions"
        }
        
        url = api_urls.get(action)
        if not url:
            return None
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'EventTrader/1.0'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"API 调用失败: {e}")
            return None


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python event_trader.py detect <event_type> <severity> [source] [details]")
        print("    - 检测事件")
        print("    - event_type: war_middle_east, trade_war, pandemic, rate_cut")
        print("    - severity: low, medium, high")
        print("")
        print("  python event_trader.py analyze <event_id>")
        print("    - 分析事件并生成买入建议")
        print("")
        print("  python event_trader.py report [event_id]")
        print("    - 生成买入建议报告")
        print("")
        print("  python event_trader.py execute <event_id> [--dry-run]")
        print("    - 执行买入（默认实战运行）")
        print("")
        print("  python event_trader.py verify")
        print("    - 测试：实战中东冲突事件")
        sys.exit(1)
    
    command = sys.argv[1]
    trader = EventTrader()
    
    if command == "detect":
        if len(sys.argv) < 4:
            print("错误: 需要参数 <event_type> <severity>")
            sys.exit(1)
        
        event_type = sys.argv[2]
        severity = sys.argv[3]
        source = sys.argv[4] if len(sys.argv) > 4 else "手动输入"
        details = sys.argv[5] if len(sys.argv) > 5 else ""
        
        event = trader.detect_event(event_type, severity, source, details)
        if event:
            print(f"\n事件ID: {event['id']}")
            print(f"运行以下命令生成买入建议:")
            print(f"  python event_trader.py analyze {event['id']}")
    
    elif command == "analyze":
        if len(sys.argv) < 3:
            print("错误: 需要参数 <event_id>")
            sys.exit(1)
        
        event_id = sys.argv[2]
        decision = trader.analyze_and_decide(event_id)
        if decision:
            print(f"\n运行以下命令查看买入建议:")
            print(f"  python event_trader.py report {event_id}")
    
    elif command == "report":
        event_id = sys.argv[2] if len(sys.argv) > 2 else None
        report = trader.generate_report(event_id)
        print(report)
    
    elif command == "execute":
        if len(sys.argv) < 3:
            print("错误: 需要参数 <event_id>")
            sys.exit(1)
        
        event_id = sys.argv[2]
        dry_run = "--dry-run" in sys.argv or "--no-dry-run" not in sys.argv
        
        result = trader.execute_buy(event_id, dry_run=dry_run)
        print(f"\n执行结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    elif command == "verify":
        # 测试：实战中东冲突
        print("="*70)
        print("测试：实战中东冲突事件")
        print("="*70)
        
        event = trader.detect_event(
            "war_middle_east",
            "high",
            "测试实战",
            "美国轰炸胡塞武装，中东冲突升级"
        )
        
        if event:
            decision = trader.analyze_and_decide(event["id"])
            if decision:
                print("\n" + "="*70)
                print(trader.generate_report(event["id"]))
    
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
