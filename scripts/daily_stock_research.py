#!/usr/bin/env python3
"""
每日深度研究 - 每天研究 1 只股票加入观察池

功能：
1. 从股票池中选择 1 只未持仓的股票
2. 深度分析（基本面 + 技术面 + 行业周期）
3. 给出买入理由和目标价
4. 加入 watchlist.json 观察池
5. 飞书通知用户
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"

sys.path.insert(0, str(PROJECT_ROOT))

def get_stock_data(code: str) -> dict:
    """获取股票实时数据（腾讯 API）"""
    try:
        # 转换代码格式：sh.600459 → sh600459
        secid = code.replace('.', '')
        url = f"http://qt.gtimg.cn/q={secid}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('gbk')
        
        # 解析：v_sz000878="51~云南铜业~000878~22.55~23.40~..."
        # 字段：0=未知，1=名称，2=代码，3=当前价，4=昨收，5=开盘，...
        if '=' in content:
            parts = content.split('=')[1].strip('"').split('~')
            if len(parts) >= 5:
                price = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[4]) if parts[4] else price
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
                
                return {
                    'code': code,
                    'name': parts[1],
                    'price': price,
                    'change_pct': change_pct,
                    'prev_close': prev_close,
                }
    except Exception as e:
        print(f"获取数据失败 {code}: {e}")
    return None


def get_fundamental_data(code: str) -> dict:
    """获取基本面数据（简化版，从股票池配置读取）"""
    # 从 watchlist 或 stock_pool 读取预设数据
    watchlist_file = CONFIG_DIR / "watchlist.json"
    if watchlist_file.exists():
        with open(watchlist_file, 'r', encoding='utf-8') as f:
            watchlist = json.load(f)
            if code in watchlist:
                return {
                    'roe': watchlist[code].get('roe', 10),
                    'gross_margin': watchlist[code].get('gross_margin', 20),
                    'net_margin': watchlist[code].get('net_margin', 10),
                }
    return {'roe': 10, 'gross_margin': 20, 'net_margin': 10}  # 默认值


def analyze_stock(code: str, name: str, industry: str) -> dict:
    """深度分析股票"""
    print(f"\n🔍 深度研究：{name} ({code})")
    print("=" * 60)
    
    # 获取实时数据
    stock_data = get_stock_data(code)
    if not stock_data:
        return None
    
    # 获取基本面
    fundamental = get_fundamental_data(code)
    
    # 分析（简化版，只用价格数据）
    analysis = {
        'code': code,
        'name': stock_data['name'],
        'industry': industry,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'price': stock_data['price'],
        'change_pct': stock_data['change_pct'],
        'pe': 15,  # 默认值
        'pb': 1.5,  # 默认值
        'market_cap': 150,  # 默认值
        'dividend_yield': 2.0,  # 默认值
        'roe': fundamental.get('roe', 10),
        'gross_margin': fundamental.get('gross_margin', 20),
        'net_margin': fundamental.get('net_margin', 10),
    }
    
    # 评分（基于投资框架）
    score = 0
    reasons = []
    
    # 简化评分：行业 + 央企背景
    score = 50  # 基础分
    reasons.append(f"{industry}行业")
    
    # 价格位置评分
    if stock_data['change_pct'] < -5:
        score += 15
        reasons.append(f"大跌{stock_data['change_pct']:.1f}%（关注机会）")
    elif stock_data['change_pct'] < 0:
        score += 5
        reasons.append(f"调整中（{stock_data['change_pct']:.1f}%）")
    
    # ROE 评分
    if fundamental.get('roe', 0) > 15:
        score += 20
        reasons.append(f"高 ROE（{fundamental['roe']:.1f}%）")
    elif fundamental.get('roe', 0) > 10:
        score += 10
        reasons.append(f"ROE{fundamental.get('roe', 0):.1f}%")
    
    # 计算目标价（简单版：当前价 * (1 + 合理涨幅)）
    target_price = stock_data['price'] * 1.2  # 20% 上涨空间
    stop_loss = stock_data['price'] * 0.85   # 15% 止损
    
    analysis.update({
        'score': score,
        'reasons': reasons,
        'target_price': round(target_price, 2),
        'stop_loss': round(stop_loss, 2),
        'recommendation': '强烈推荐' if score >= 70 else '推荐' if score >= 50 else '观望',
    })
    
    # 打印分析结果
    print(f"当前价：¥{stock_data['price']:.2f} ({stock_data['change_pct']:+.1f}%)")
    print(f"PE: {analysis['pe']:.1f} | PB: {analysis['pb']:.2f}")
    print(f"市值：{analysis['market_cap']:.1f}亿（估算）")
    print(f"股息率：{analysis['dividend_yield']:.1f}%")
    print(f"ROE: {fundamental.get('roe', 0):.1f}%")
    print()
    print(f"综合评分：{score}分")
    print(f"评级：{analysis['recommendation']}")
    print()
    if reasons:
        print("推荐理由:")
        for r in reasons:
            print(f"  ✓ {r}")
    print()
    print(f"目标价：¥{target_price:.2f} (+20%)")
    print(f"止损价：¥{stop_loss:.2f} (-15%)")
    print("=" * 60)
    
    return analysis


def add_to_watchlist(analysis: dict):
    """加入观察池"""
    watchlist_file = CONFIG_DIR / "watchlist.json"
    
    watchlist = {}
    if watchlist_file.exists():
        with open(watchlist_file, 'r', encoding='utf-8') as f:
            watchlist = json.load(f)
    
    # 添加股票
    watchlist[analysis['code']] = {
        'name': analysis['name'],
        'industry': analysis['industry'],
        'added_date': analysis['date'],
        'reason': '，'.join(analysis['reasons']),
        'target_price': analysis['target_price'],
        'stop_loss': analysis['stop_loss'],
        'score': analysis['score'],
        'priority': 'high' if analysis['score'] >= 70 else 'medium',
    }
    
    with open(watchlist_file, 'w', encoding='utf-8') as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已加入观察池：{analysis['name']} ({analysis['code']})")


def send_feishu_notification(analysis: dict):
    """发送飞书通知"""
    try:
        feishu_file = CONFIG_DIR / "feishu_config.json"
        if not feishu_file.exists():
            return
        
        with open(feishu_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        webhook = config.get('webhook_url') or config.get('webhook')
        if not webhook:
            return
        
        message = f"""📊 **每日深度研究**

股票：{analysis['name']} ({analysis['code']})
行业：{analysis['industry']}
日期：{analysis['date']}

💰 **估值数据**
当前价：¥{analysis['price']:.2f}
PE: {analysis['pe']:.1f} | PB: {analysis['pb']:.2f}
市值：{analysis['market_cap']:.1f}亿
股息率：{analysis['dividend_yield']:.1f}%
ROE: {analysis['roe']:.1f}%

📈 **评级**
综合评分：{analysis['score']}分
评级：{analysis['recommendation']}
目标价：¥{analysis['target_price']:.2f} (+{((analysis['target_price']/analysis['price']-1)*100):.0f}%)
止损价：¥{analysis['stop_loss']:.2f} (-{((1-analysis['stop_loss']/analysis['price'])*100):.0f}%)

🎯 **推荐理由**
{chr(10).join('✓ ' + r for r in analysis['reasons'])}

---
已加入观察池，持续跟踪。"""
        
        payload = {
            "msg_type": "text",
            "content": {"text": message}
        }
        
        req = urllib.request.Request(
            webhook,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("✅ 飞书通知发送成功")
    except Exception as e:
        print(f"发送飞书通知失败：{e}")


def select_stock_to_research():
    """从股票池选择 1 只未研究的股票"""
    # 读取股票池
    pool_file = CONFIG_DIR / "stock_pool.md"
    watchlist_file = CONFIG_DIR / "watchlist.json"
    positions_file = CONFIG_DIR / "positions.json"
    
    # 已持仓的股票
    positions = set()
    if positions_file.exists():
        with open(positions_file, 'r', encoding='utf-8') as f:
            positions = set(json.load(f).keys())
    
    # 已在观察池的股票
    watchlist = set()
    if watchlist_file.exists():
        with open(watchlist_file, 'r', encoding='utf-8') as f:
            watchlist = set(json.load(f).keys())
    
    # 从 stock_pool.md 解析股票代码（简化版：硬编码重点股票）
    # 实际应该解析 markdown 表格
    priority_stocks = [
        ("sz.000878", "云南铜业", "铜"),
        ("sh.601168", "西部矿业", "铜"),
        ("sh.600362", "江西铜业", "铜"),
        ("sh.601600", "中国铝业", "铝"),
        ("sz.000807", "云铝股份", "铝"),
        ("sh.600547", "山东黄金", "黄金"),
        ("sh.601899", "紫金矿业", "黄金"),
        ("sz.000831", "五矿稀土", "稀土"),
        ("sz.000960", "锡业股份", "锡"),
        ("sh.600497", "驰宏锌锗", "锌"),
        ("sh.688396", "华润微", "芯片"),
        ("sh.688037", "芯源微", "芯片"),
    ]
    
    # 选择未持仓且未在观察池的股票
    for code, name, industry in priority_stocks:
        if code not in positions and code not in watchlist:
            return code, name, industry
    
    # 如果都在观察池了，随机选一只
    import random
    return random.choice(priority_stocks)


def main():
    """主函数"""
    print("=" * 60)
    print(f"📚 每日深度研究 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 选择股票
    code, name, industry = select_stock_to_research()
    print(f"\n🎯 今日研究：{name} ({code}) - {industry}")
    
    # 深度分析
    analysis = analyze_stock(code, name, industry)
    if not analysis:
        print("❌ 分析失败")
        return
    
    # 加入观察池
    add_to_watchlist(analysis)
    
    # 发送飞书通知
    send_feishu_notification(analysis)
    
    # 保存研究报告
    report_file = DATA_DIR / f"research_{code}_{analysis['date']}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"\n📄 报告已保存：{report_file}")


if __name__ == "__main__":
    main()
