#!/usr/bin/env python3
"""
实时盯盘工具
监控持仓和自选股的实时行情、异动、预警
"""

import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
import json

# 添加虚拟环境路径
VENV_PATH = os.path.expanduser("~/.openclaw/workspace/china-stock-team/venv/lib/python3.14/site-packages")
sys.path.insert(0, VENV_PATH)

import baostock as bs

# 持仓配置（示例，请根据实际情况修改）
POSITIONS = {
    # "sh.600459": {
    #     "name": "贵研铂业",
    #     "shares": 1000,
    #     "cost_price": 25.00,
    #     "target_price": 32.50,
    #     "stop_loss": 23.00,
    # },
}

# 自选股配置
WATCHLIST = [
    "sh.600459",  # 贵研铂业
    "sh.601121",  # 宝地矿业
    "sz.000758",  # 中色股份
]

# 预警配置
ALERTS = {
    "price_change_3pct": True,  # 涨跌幅超过3%
    "volume_1_5x": True,        # 成交量超过1.5倍
    "target_reached": True,     # 到达目标价
    "stop_loss": True,          # 触发止损
    "new_high": True,           # 创新高
    "new_low": True,            # 创新低
}

def login():
    lg = bs.login()
    if lg.error_code != '0':
        raise Exception(f"登录失败: {lg.error_msg}")

def logout():
    bs.logout()

def get_realtime_quote(code: str) -> Optional[Dict]:
    """
    获取实时行情（实际上是最新收盘价）
    注意：baostock 不支持实时行情，这里用最新收盘价实战
    """
    try:
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            code,
            'date,code,open,high,low,close,volume,amount',
            start_date=start_date,
            end_date=end_date,
            frequency='d',
            adjustflag='2'
        )
        
        if rs.error_code != '0' or not rs.next():
            return None
        
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        
        if not data:
            return None
        
        laverify = data[-1]
        prev = data[-2] if len(data) > 1 else laverify
        
        return {
            "code": code,
            "date": laverify[0],
            "open": float(laverify[2]),
            "high": float(laverify[3]),
            "low": float(laverify[4]),
            "close": float(laverify[5]),
            "volume": float(laverify[6]),
            "amount": float(laverify[7]),
            "change_pct": ((float(laverify[5]) - float(prev[5])) / float(prev[5]) * 100) if float(prev[5]) > 0 else 0,
        }
    except Exception as e:
        return None

def calculate_position_pnl(position: Dict, current_price: float) -> Dict:
    """
    计算持仓盈亏
    """
    shares = position["shares"]
    cost_price = position["cost_price"]
    target_price = position["target_price"]
    stop_loss = position["stop_loss"]

    market_value = current_price * shares
    cost_value = cost_price * shares
    pnl = market_value - cost_value
    pnl_pct = (current_price - cost_price) / cost_price * 100 if cost_price > 0 else 0

    # 距离目标价
    to_target_pct = (target_price - current_price) / current_price * 100 if current_price > 0 else 0

    # 距离止损价
    to_stop_pct = (current_price - stop_loss) / current_price * 100 if current_price > 0 else 0
    
    return {
        "market_value": market_value,
        "cost_value": cost_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "to_target_pct": to_target_pct,
        "to_stop_pct": to_stop_pct,
    }

def check_alerts(code: str, quote: Dict, position: Optional[Dict] = None) -> List[str]:
    """
    检查预警条件
    """
    alerts = []
    
    # 涨跌幅预警
    if ALERTS["price_change_3pct"]:
        if abs(quote["change_pct"]) >= 3:
            direction = "📈" if quote["change_pct"] > 0 else "📉"
            alerts.append(f"{direction} {code} 涨跌幅 {quote['change_pct']:+.2f}%")
    
    # 成交量预警（需要历史数据，这里简化）
    # TODO: 实现成交量预警
    
    # 持仓相关预警
    if position:
        current_price = quote["close"]
        
        # 目标价预警
        if ALERTS["target_reached"]:
            if current_price >= position["target_price"]:
                alerts.append(f"🎯 {code} 到达目标价 ¥{position['target_price']}")
        
        # 止损预警
        if ALERTS["stop_loss"]:
            if current_price <= position["stop_loss"]:
                alerts.append(f"⚠️ {code} 触发止损 ¥{position['stop_loss']}")
    
    return alerts

def monitor_positions():
    """
    监控持仓
    """
    print("=" * 70)
    print("💼 持仓监控")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    login()
    
    total_market_value = 0
    total_cost = 0
    all_alerts = []
    
    for code, position in POSITIONS.items():
        quote = get_realtime_quote(code)
        
        if not quote:
            print(f"❌ {code}: 无法获取行情")
            continue
        
        current_price = quote["close"]
        pnl_data = calculate_position_pnl(position, current_price)
        
        # 计算总计
        total_market_value += pnl_data["market_value"]
        total_cost += pnl_data["cost_value"]
        
        # 显示持仓信息
        pnl_emoji = "🟢" if pnl_data["pnl"] >= 0 else "🔴"
        
        print(f"\n{pnl_emoji} {position['name']} ({code})")
        print(f"  持仓: {position['shares']}股 | 成本: ¥{position['cost_price']:.2f}")
        print(f"  当前价: ¥{current_price:.2f} ({quote['change_pct']:+.2f}%)")
        print(f"  市值: ¥{pnl_data['market_value']:.2f}")
        print(f"  盈亏: ¥{pnl_data['pnl']:.2f} ({pnl_data['pnl_pct']:+.2f}%)")
        print(f"  目标价: ¥{position['target_price']:.2f} (距离 {pnl_data['to_target_pct']:+.2f}%)")
        print(f"  止损价: ¥{position['stop_loss']:.2f} (距离 {pnl_data['to_stop_pct']:+.2f}%)")
        
        # 检查预警
        alerts = check_alerts(code, quote, position)
        all_alerts.extend(alerts)
    
    logout()
    
    # 显示总计
    total_pnl = total_market_value - total_cost
    total_pnl_pct = (total_market_value - total_cost) / total_cost * 100 if total_cost > 0 else 0
    
    print("\n" + "=" * 70)
    print("📊 持仓总计")
    print("=" * 70)
    print(f"总市值: ¥{total_market_value:.2f}")
    print(f"总成本: ¥{total_cost:.2f}")
    print(f"总盈亏: ¥{total_pnl:.2f} ({total_pnl_pct:+.2f}%)")
    
    # 显示预警
    if all_alerts:
        print("\n" + "=" * 70)
        print("⚠️ 预警提醒")
        print("=" * 70)
        for alert in all_alerts:
            print(alert)
    
    return all_alerts

def monitor_watchlist():
    """
    监控自选股
    """
    print("\n" + "=" * 70)
    print("👀 自选股监控")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    login()
    
    for code in WATCHLIST:
        quote = get_realtime_quote(code)
        
        if not quote:
            print(f"❌ {code}: 无法获取行情")
            continue
        
        change_emoji = "🟢" if quote["change_pct"] >= 0 else "🔴"
        
        print(f"\n{change_emoji} {code}")
        print(f"  收盘价: ¥{quote['close']:.2f} ({quote['change_pct']:+.2f}%)")
        print(f"  最高: ¥{quote['high']:.2f} | 最低: ¥{quote['low']:.2f}")
        print(f"  成交量: {quote['volume']:.0f}万")
        
        # 检查预警
        alerts = check_alerts(code, quote)
        for alert in alerts:
            print(f"  {alert}")
    
    logout()

def run_continuous_monitor(interval_minutes: int = 15):
    """
    持续监控（每15分钟刷新一次）
    """
    print(f"🔄 开始持续监控（每{interval_minutes}分钟刷新）")
    print("按 Ctrl+C 停止")
    
    try:
        while True:
            # 清屏
            os.system('clear' if os.name == 'posix' else 'cls')
            
            # 监控持仓
            monitor_positions()
            
            # 监控自选股
            monitor_watchlist()
            
            print(f"\n⏰ 下次刷新: {interval_minutes}分钟后")
            print(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")
            
            # 等待
            time.sleep(interval_minutes * 60)
    
    except KeyboardInterrupt:
        print("\n\n✅ 已停止监控")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 realtime_monitor.py <命令>")
        print("命令:")
        print("  positions    监控持仓")
        print("  watchlist    监控自选股")
        print("  all          监控持仓+自选股")
        print("  continuous   持续监控（每15分钟）")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "positions":
        monitor_positions()
    
    elif command == "watchlist":
        monitor_watchlist()
    
    elif command == "all":
        monitor_positions()
        monitor_watchlist()
    
    elif command == "continuous":
        interval = int(sys.argv[2]) if len(sys.argv) >= 3 else 15
        run_continuous_monitor(interval)
    
    else:
        print("未知命令")
        sys.exit(1)

if __name__ == "__main__":
    main()
