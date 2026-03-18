#!/usr/bin/env python3
"""
飞书通知集成
"""

import json
import urllib.request
import os
from datetime import datetime

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")

# 飞书配置（从配置文件读取）
def load_feishu_config():
    """加载飞书配置"""
    config_file = os.path.join(PROJECT_ROOT, "config", "feishu_config.json")
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def send_feishu_message(title, content, level='info', webhook_url=None):
    """发送飞书消息"""
    config = load_feishu_config()
    
    if not webhook_url:
        webhook_url = config.get('webhook_url')
    
    if not webhook_url:
        print("⚠️ 飞书 webhook 未配置")
        return False
    
    # 消息颜色
    colors = {
        'info': 'blue',
        'success': 'green',
        'warning': 'yellow',
        'high': 'orange',
        'critical': 'red',
        'medium': 'yellow',
    }
    color = colors.get(level, 'blue')
    
    # 构建消息
    message = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": color
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": content
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                }
            ]
        }
    }
    
    try:
        data = json.dumps(message).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            
        if result.get('StatusCode') == 0 or result.get('code') == 0:
            print(f"✅ 飞书消息发送成功: {title}")
            return True
        else:
            print(f"❌ 飞书消息发送失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 发送飞书消息失败: {e}")
        return False

def send_daily_report(portfolio, alerts):
    """发送每日报告"""
    config = load_feishu_config()
    
    if not config.get('daily_report_enabled', True):
        return
    
    # 构建报告内容
    lines = [
        f"📊 每日投资报告",
        f"",
        f"💰 资金状况",
        f"总资产: ¥{portfolio['total_capital']:,.0f}",
        f"持仓市值: ¥{portfolio['total_value']:,.2f}",
        f"总盈亏: ¥{portfolio['total_profit']:,.2f} ({portfolio['total_profit_pct']:+.2f}%)",
        f"",
        f"📈 持仓详情",
    ]
    
    for detail in portfolio.get('details', []):
        profit_icon = '🟢' if detail['profit'] >= 0 else '🔴'
        lines.append(f"{profit_icon} {detail['name']}: {detail['profit_pct']:+.2f}%")
    
    if alerts:
        lines.append(f"")
        lines.append(f"⚠️ 预警 ({len(alerts)}条)")
        for alert in alerts[:5]:  # 最多显示5条
            lines.append(f"• {alert['message']}")
    
    content = '\n'.join(lines)
    
    send_feishu_message(
        title="📈 每日投资报告",
        content=content,
        level='info'
    )

def send_trade_notification(action, code, name, shares, price, profit=None):
    """发送交易通知"""
    if action == 'BUY':
        content = f"买入 {name} ({code})\n数量: {shares}股\n价格: ¥{price:.2f}\n金额: ¥{shares * price:,.2f}"
        level = 'info'
    else:  # SELL
        profit_text = f"\n盈亏: ¥{profit:,.2f}" if profit is not None else ""
        content = f"卖出 {name} ({code})\n数量: {shares}股\n价格: ¥{price:.2f}{profit_text}"
        level = 'success' if profit is None or profit >= 0 else 'warning'
    
    send_feishu_message(
        title=f"{'🛒' if action == 'BUY' else '💰'} 交易通知",
        content=content,
        level=level
    )

def send_alert_notification(alert):
    """发送预警通知"""
    send_feishu_message(
        title=f"⚠️ 股票预警 - {alert['name']}",
        content=alert['message'],
        level=alert['level']
    )

def load_positions():
    """加载持仓数据"""
    positions_file = os.path.join(PROJECT_ROOT, "config", "positions.json")
    if os.path.exists(positions_file):
        with open(positions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_portfolio():
    """加载资金数据"""
    portfolio_file = os.path.join(PROJECT_ROOT, "config", "portfolio.json")
    if os.path.exists(portfolio_file):
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_realtime_price(code: str) -> float:
    """获取实时价格（简化版）"""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from adapters import get_data_manager
        dm = get_data_manager()
        price = dm.get_realtime_price(code)
        if price:
            return float(price.price)
    except:
        pass
    return None

def generate_portfolio_report(report_type: str) -> dict:
    """生成持仓汇报"""
    positions = load_positions()
    portfolio = load_portfolio()

    total_capital = portfolio.get("total_capital", 200000)
    available_cash = portfolio.get("available_cash", total_capital)

    # 计算持仓市值和盈亏
    position_details = []
    total_value = 0
    total_profit = 0

    for code, pos in positions.items():
        current_price = get_realtime_price(code)
        cost_price = pos.get("cost_price", 0)
        shares = pos.get("shares", 0)

        if current_price:
            market_value = shares * current_price
            profit = shares * (current_price - cost_price)
            profit_pct = (current_price / cost_price - 1) * 100 if cost_price > 0 else 0
        else:
            market_value = shares * cost_price
            profit = 0
            profit_pct = 0

        total_value += market_value
        total_profit += profit

        position_details.append({
            "name": pos.get("name", code),
            "code": code,
            "shares": shares,
            "cost_price": cost_price,
            "current_price": current_price,
            "market_value": market_value,
            "profit": profit,
            "profit_pct": profit_pct,
        })

    total_assets = available_cash + total_value
    total_profit_pct = (total_profit / total_value * 100) if total_value > 0 else 0

    return {
        "total_capital": total_capital,
        "available_cash": available_cash,
        "total_value": total_value,
        "total_profit": total_profit,
        "total_profit_pct": total_profit_pct,
        "total_assets": total_assets,
        "positions": position_details,
    }

def format_report(report_type: str, portfolio: dict) -> tuple:
    """格式化报告"""
    time_str = datetime.now().strftime('%H:%M')

    # 根据报告类型选择标题和emoji
    type_config = {
        "morning": ("🌅 早盘持仓汇报", "早盘"),
        "noon_close": ("🕛 午盘收盘汇报", "午盘收盘"),
        "noon_open": ("🕐 午盘开盘汇报", "午盘开盘"),
        "close": ("🌙 收盘汇总汇报", "收盘汇总"),
    }

    title, time_label = type_config.get(report_type, ("📊 持仓汇报", "持仓"))

    lines = [
        f"{title}",
        f"",
        f"📅 时间: {datetime.now().strftime('%Y-%m-%d')} {time_str}",
        f"",
        f"💰 资金状况",
        f"总资产: ¥{portfolio['total_assets']:,.2f}",
        f"可用现金: ¥{portfolio['available_cash']:,.2f}",
        f"持仓市值: ¥{portfolio['total_value']:,.2f}",
        f"总盈亏: ¥{portfolio['total_profit']:,.2f} ({portfolio['total_profit_pct']:+.2f}%)",
        f"",
        f"📈 持仓详情 ({len(portfolio['positions'])}只)",
    ]

    for pos in portfolio['positions']:
        emoji = '🟢' if pos['profit'] >= 0 else '🔴'
        lines.append(f"{emoji} {pos['name']} ({pos['code']})")
        lines.append(f"   持仓: {pos['shares']}股 | 成本: ¥{pos['cost_price']:.2f} → 现价: ¥{pos['current_price']:.2f}")
        lines.append(f"   市值: ¥{pos['market_value']:,.2f} | 盈亏: ¥{pos['profit']:,.2f} ({pos['profit_pct']:+.2f}%)")

    content = '\n'.join(lines)
    level = 'success' if portfolio['total_profit'] >= 0 else 'warning'

    return title, content, level

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="飞书通知集成")
    parser.add_argument("--report", choices=["morning", "noon_close", "noon_open", "close"], help="生成持仓汇报")
    parser.add_argument("--test", action="store_true", help="发送测试消息")

    args = parser.parse_args()

    if args.report:
        # 生成并发送持仓汇报
        portfolio_data = generate_portfolio_report(args.report)
        title, content, level = format_report(args.report, portfolio_data)
        send_feishu_message(title=title, content=content, level=level)
    elif args.test:
        # 测试
        send_feishu_message(
            title="🧪 测试消息",
            content="这是一条测试消息，用于验证飞书通知功能。",
            level='info'
        )
    else:
        print("用法:")
        print("  python feishu_notifier.py --report morning      早盘持仓汇报")
        print("  python feishu_notifier.py --report noon_close    午盘收盘汇报")
        print("  python feishu_notifier.py --report noon_open     午盘开盘汇报")
        print("  python feishu_notifier.py --report close         收盘汇总汇报")
        print("  python feishu_notifier.py --test               发送测试消息")
