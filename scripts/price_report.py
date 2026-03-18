#!/usr/bin/env python3
"""
价格汇报脚本 - 发送到飞书群
每天4次：9:30, 11:30, 14:00, 15:05
"""

import json
import urllib.request
import os
from datetime import datetime

# 配置
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
POSITIONS_FILE = os.path.join(PROJECT_ROOT, "config", "positions.json")
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/11736928-0e52-4e41-b5c6-2c050bff11e6"

# 月度目标
TARGET_PROFIT = 40000  # +20%


def get_realtime_prices(codes):
    """获取实时价格（腾讯API）"""
    try:
        stock_codes = [code.replace(".", "") for code in codes]
        url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode('gbk')
        
        prices = {}
        for line in text.strip().split('\n'):
            if '~' not in line:
                continue
            parts = line.split('~')
            if len(parts) >= 33:
                code = parts[2]
                prices[code] = {
                    'price': float(parts[3]),
                    'change_pct': float(parts[32])
                }
        return prices
    except Exception as e:
        print(f"获取价格失败: {e}")
        return {}


def send_to_feishu(text):
    """发送到飞书群"""
    try:
        data = {
            "msg_type": "text",
            "content": {"text": text}
        }
        
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('StatusCode') == 0
    except Exception as e:
        print(f"发送失败: {e}")
        return False


def generate_report():
    """生成汇报内容"""
    with open(POSITIONS_FILE, 'r') as f:
        positions = json.load(f)
    
    prices = get_realtime_prices(positions.keys())
    
    now = datetime.now()
    time_str = now.strftime("%m-%d %H:%M")
    hour = now.hour
    
    # 判断时段
    if hour < 10:
        period = "🌅 早盘开盘"
    elif hour < 12:
        period = "☀️ 午盘收盘"
    elif hour < 15:
        period = "🌤️ 午盘进行"
    else:
        period = "🌆 收盘汇总"
    
    # 计算盈亏
    total_cost = 0
    total_value = 0
    lines = []
    
    lines.append(f"【持仓汇报】{period} {time_str}")
    lines.append("=" * 30)
    
    for code, pos in positions.items():
        stock_code = code.split('.')[1]
        shares = pos['shares']
        cost = pos['cost_price']
        
        current_price = prices.get(stock_code, {}).get('price', cost)
        change_pct = prices.get(stock_code, {}).get('change_pct', 0)
        
        cost_amount = shares * cost
        value = shares * current_price
        profit = value - cost_amount
        profit_pct = (current_price / cost - 1) * 100
        
        total_cost += cost_amount
        total_value += value
        
        # 格式化
        profit_sign = "+" if profit >= 0 else ""
        today_sign = "+" if change_pct >= 0 else ""
        
        lines.append(f"\n【{pos['name']}】{stock_code}")
        lines.append(f"  现价: ¥{current_price:.2f} ({today_sign}{change_pct:.2f}%)")
        lines.append(f"  盈亏: {profit_sign}¥{profit:,.0f} ({profit_sign}{profit_pct:.2f}%)")
    
    lines.append("\n" + "=" * 30)
    
    # 总盈亏
    total_profit = total_value - total_cost
    total_pct = (total_value / total_cost - 1) * 100
    progress_pct = (total_profit / TARGET_PROFIT) * 100
    
    profit_sign = "+" if total_profit >= 0 else ""
    
    lines.append(f"\n📊 总盈亏: {profit_sign}¥{total_profit:,.0f} ({profit_sign}{total_pct:.2f}%)")
    lines.append(f"🎯 月目标: {progress_pct:.1f}% (目标+¥{TARGET_PROFIT:,})")
    
    # 发送
    text = "\n".join(lines)
    success = send_to_feishu(text)
    
    print(f"[{time_str}] {'✅ 发送成功' if success else '❌ 发送失败'}")
    return success


if __name__ == '__main__':
    generate_report()
