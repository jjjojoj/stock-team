#!/usr/bin/env python3
"""
价格汇报脚本 - 发送到飞书群
每天4次：9:30, 11:30, 14:00, 15:05
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# 配置
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSITIONS_FILE = PROJECT_ROOT / "config" / "positions.json"

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
        scripts_dir = str(PROJECT_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from feishu_notifier import get_default_webhook_url, send_feishu_message

        webhook_url = get_default_webhook_url()
        if not webhook_url:
            print("⚠️ 飞书 webhook 未配置")
            return False

        lines = text.splitlines()
        title = lines[0] if lines else "📊 持仓汇报"
        content = "\n".join(lines[1:]).strip() or "无详细内容"
        level = 'warning' if '暂无持仓配置' in text else 'info'
        return send_feishu_message(title=title, content=content, level=level, webhook_url=webhook_url)
    except Exception as e:
        print(f"发送失败: {e}")
        return False


def generate_report():
    """生成汇报内容"""
    now = datetime.now()
    time_str = now.strftime("%m-%d %H:%M")
    if now.hour < 10:
        report_type = "morning"
    elif now.hour < 12:
        report_type = "noon_close"
    elif now.hour < 15:
        report_type = "noon_open"
    else:
        report_type = "close"

    scripts_dir = str(PROJECT_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from feishu_notifier import send_portfolio_report

    success = send_portfolio_report(report_type)
    print(f"[{time_str}] {'✅ 发送成功' if success else '❌ 发送失败'}")
    return success


if __name__ == '__main__':
    generate_report()
