#!/usr/bin/env python3
"""
增强版实时监控系统
- 每15分钟自动刷新
- 止盈止损提醒
- 飞书通知
"""

import json
import time
import urllib.request
from datetime import datetime
import os
import sys

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

# 导入飞书通知（如果可用）
try:
    from feishu_notifier import send_feishu_message
    FEISHU_ENABLED = True
except:
    FEISHU_ENABLED = False
    print("⚠️ 飞书通知未启用")

def get_realtime_prices(codes):
    """批量获取实时股价"""
    results = {}
    
    try:
        code_list = [code.replace(".", "") for code in codes]
        url = f"http://qt.gtimg.cn/q={','.join(code_list)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode("gbk")
            
        for line in text.strip().split('\n'):
            if '~' not in line:
                continue
            
            parts = line.split('~')
            if len(parts) >= 32:
                code = parts[2]
                results[code] = {
                    'name': parts[1],
                    'price': float(parts[3]),
                    'change_pct': float(parts[31]) if parts[31] and parts[31] != '-' else 0,
                    'high': float(parts[33]) if len(parts) > 33 else float(parts[3]),
                    'low': float(parts[34]) if len(parts) > 34 else float(parts[3]),
                    'volume': int(parts[6]) if parts[6].isdigit() else 0,
                }
    
    except Exception as e:
        print(f"❌ 获取价格失败: {e}")
    
    return results

def load_positions():
    """加载持仓数据"""
    positions_file = os.path.join(PROJECT_ROOT, "config", "positions.json")
    if os.path.exists(positions_file):
        with open(positions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_capital():
    """加载资金配置"""
    capital_file = os.path.join(PROJECT_ROOT, "config", "capital_allocation.json")
    if os.path.exists(capital_file):
        with open(capital_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def check_stop_loss_take_profit(positions, prices):
    """检查止盈止损"""
    alerts = []
    
    for code, pos in positions.items():
        code_clean = code.split(".")[1]
        
        if code_clean not in prices:
            continue
        
        current_price = prices[code_clean]['price']
        cost_price = pos['cost_price']
        target_price = pos.get('target_price', cost_price * 1.3)
        stop_loss = pos.get('stop_loss', cost_price * 0.92)
        
        profit_pct = (current_price / cost_price - 1) * 100
        
        # 止盈检查
        if current_price >= target_price:
            alert = {
                'type': 'take_profit',
                'level': 'high',
                'code': code,
                'name': pos['name'],
                'current_price': current_price,
                'target_price': target_price,
                'profit_pct': round(profit_pct, 2),
                'message': f"🎯 {pos['name']} 到达止盈线！当前价 ¥{current_price}，盈利 {profit_pct:.2f}%"
            }
            alerts.append(alert)
        
        # 止损检查
        elif current_price <= stop_loss:
            alert = {
                'type': 'stop_loss',
                'level': 'critical',
                'code': code,
                'name': pos['name'],
                'current_price': current_price,
                'stop_loss': stop_loss,
                'profit_pct': round(profit_pct, 2),
                'message': f"⚠️ {pos['name']} 触发止损！当前价 ¥{current_price}，亏损 {profit_pct:.2f}%"
            }
            alerts.append(alert)
        
        # 预警（接近止损线）
        elif profit_pct <= -5:
            alert = {
                'type': 'warning',
                'level': 'medium',
                'code': code,
                'name': pos['name'],
                'current_price': current_price,
                'profit_pct': round(profit_pct, 2),
                'message': f"⚠️ {pos['name']} 接近止损线！当前亏损 {profit_pct:.2f}%"
            }
            alerts.append(alert)
    
    return alerts

def calculate_portfolio_status(positions, prices, capital_config):
    """计算组合状态"""
    total_cost = 0
    total_value = 0
    total_profit = 0
    
    details = []
    
    for code, pos in positions.items():
        code_clean = code.split(".")[1]
        current_price = prices.get(code_clean, {}).get('price', pos['cost_price'])
        
        cost = pos['shares'] * pos['cost_price']
        value = pos['shares'] * current_price
        profit = value - cost
        profit_pct = (current_price / pos['cost_price'] - 1) * 100
        
        total_cost += cost
        total_value += value
        total_profit += profit
        
        details.append({
            'code': code,
            'name': pos['name'],
            'shares': pos['shares'],
            'cost_price': pos['cost_price'],
            'current_price': current_price,
            'profit': round(profit, 2),
            'profit_pct': round(profit_pct, 2),
            'weight': 0,  # 稍后计算
        })
    
    # 计算权重
    for detail in details:
        detail['weight'] = round((detail['shares'] * detail['current_price']) / total_value * 100, 2) if total_value > 0 else 0
    
    # 总体统计
    total_profit_pct = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0
    
    # 资金使用情况
    total_capital = capital_config.get('total_capital', 200000)
    used_capital = total_cost
    available_capital = total_capital - used_capital
    usage_pct = (used_capital / total_capital * 100) if total_capital > 0 else 0
    
    return {
        'total_capital': total_capital,
        'used_capital': round(used_capital, 2),
        'available_capital': round(available_capital, 2),
        'usage_pct': round(usage_pct, 2),
        'total_cost': round(total_cost, 2),
        'total_value': round(total_value, 2),
        'total_profit': round(total_profit, 2),
        'total_profit_pct': round(total_profit_pct, 2),
        'details': details,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

def save_monitor_data(data):
    """保存监控数据"""
    output_path = os.path.join(PROJECT_ROOT, "data", "monitor_status.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_alerts_to_feishu(alerts):
    """发送预警到飞书"""
    if not FEISHU_ENABLED or not alerts:
        return
    
    for alert in alerts:
        try:
            send_feishu_message(
                title=f"股票预警 - {alert['name']}",
                content=alert['message'],
                level=alert['level']
            )
        except Exception as e:
            print(f"❌ 发送飞书通知失败: {e}")

def monitor_once():
    """单次监控"""
    print(f"\n{'='*70}")
    print(f"📊 实时监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    
    # 加载数据
    positions = load_positions()
    capital_config = load_capital()
    
    if not positions:
        print("❌ 无持仓数据")
        return
    
    # 获取实时价格
    codes = list(positions.keys())
    prices = get_realtime_prices(codes)
    
    if not prices:
        print("❌ 无法获取价格")
        return
    
    # 计算组合状态
    portfolio = calculate_portfolio_status(positions, prices, capital_config)
    
    # 检查止盈止损
    alerts = check_stop_loss_take_profit(positions, prices)
    
    # 保存数据
    monitor_data = {
        'portfolio': portfolio,
        'alerts': alerts,
        'prices': {code: prices.get(code.split('.')[1], {}) for code in positions},
    }
    save_monitor_data(monitor_data)
    
    # 打印状态
    print(f"\n💰 组合状态")
    print(f"  总资产: ¥{portfolio['total_capital']:,.0f}")
    print(f"  已用资金: ¥{portfolio['used_capital']:,.2f} ({portfolio['usage_pct']:.1f}%)")
    print(f"  可用资金: ¥{portfolio['available_capital']:,.2f}")
    print(f"  持仓市值: ¥{portfolio['total_value']:,.2f}")
    print(f"  总盈亏: ¥{portfolio['total_profit']:,.2f} ({portfolio['total_profit_pct']:+.2f}%)")
    
    print(f"\n📈 持仓详情")
    for detail in portfolio['details']:
        profit_color = '🟢' if detail['profit'] >= 0 else '🔴'
        print(f"  {profit_color} {detail['name']} ({detail['code']})")
        print(f"     持仓: {detail['shares']}股 · 成本: ¥{detail['cost_price']:.2f} · 现价: ¥{detail['current_price']:.2f}")
        print(f"     盈亏: ¥{detail['profit']:,.2f} ({detail['profit_pct']:+.2f}%) · 权重: {detail['weight']:.1f}%")
    
    # 打印预警
    if alerts:
        print(f"\n⚠️ 预警 ({len(alerts)}条)")
        for alert in alerts:
            level_icon = '🔴' if alert['level'] == 'critical' else ('🟡' if alert['level'] == 'high' else '🟢')
            print(f"  {level_icon} {alert['message']}")
        
        # 发送飞书通知
        send_alerts_to_feishu(alerts)
    else:
        print(f"\n✅ 无预警")
    
    return monitor_data

def monitor_continuous(interval_minutes=15):
    """持续监控"""
    print(f"🔄 启动持续监控 (每{interval_minutes}分钟)")
    print(f"按 Ctrl+C 停止")
    
    interval_seconds = interval_minutes * 60
    
    while True:
        try:
            monitor_once()
            print(f"\n⏰ 下次刷新: {interval_minutes}分钟后")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            break
        except Exception as e:
            print(f"\n❌ 监控出错: {e}")
            time.sleep(60)  # 出错后等待1分钟

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='实时监控系统')
    parser.add_argument('--continuous', action='store_true', help='持续监控')
    parser.add_argument('--interval', type=int, default=15, help='监控间隔(分钟)')
    
    args = parser.parse_args()
    
    if args.continuous:
        monitor_continuous(args.interval)
    else:
        monitor_once()
