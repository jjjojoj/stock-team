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
import re
import sys
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error
from typing import Dict, List, Optional

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"

sys.path.insert(0, str(PROJECT_ROOT))

from core.fundamentals import get_fundamental_bundle
from core.runtime_guardrails import evaluate_runtime_mode, record_guardrail_event, record_guardrail_success, task_lock, TaskLockedError
from core.storage import load_positions, load_watchlist, save_watchlist


def _normalize_symbol(raw_code: str) -> str:
    raw = raw_code.strip()
    if raw.startswith(("sh.", "sz.")):
        return raw
    if raw.isdigit():
        return f"{'sh' if raw.startswith(('6', '9')) else 'sz'}.{raw}"
    return raw


def _parse_market_cap(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(match.group(1)) if match else 0.0


def load_stock_pool_candidates() -> List[Dict[str, object]]:
    """Parse the maintained stock pool markdown instead of hardcoding candidates."""
    stock_pool_file = CONFIG_DIR / "stock_pool.md"
    if not stock_pool_file.exists():
        return []

    rows: List[Dict[str, object]] = []
    current_industry = ""
    in_code_block = False
    for raw_line in stock_pool_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line.startswith("### "):
            current_industry = line[4:].strip()
            continue
        if not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"代码", "------"}:
            continue
        if len(cells) < 7:
            continue

        rows.append(
            {
                "code": _normalize_symbol(cells[0]),
                "name": cells[1],
                "controller": cells[2],
                "business": cells[3],
                "market_cap": _parse_market_cap(cells[4]),
                "pb_hint": cells[5],
                "reason": cells[6],
                "industry": current_industry or "未知",
            }
        )

    return rows


def load_fundamental_snapshot() -> Dict[str, Dict[str, float]]:
    """Load maintained fundamental snapshot from markdown."""
    fundamentals_file = CONFIG_DIR / "fundamental_data.md"
    if not fundamentals_file.exists():
        return {}

    snapshot: Dict[str, Dict[str, float]] = {}
    in_code_block = False
    for raw_line in fundamentals_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"代码", "------"} or len(cells) < 8:
            continue

        code = _normalize_symbol(cells[0])
        try:
            snapshot[code] = {
                "pb": float(cells[2]),
                "pe": float(cells[3]),
                "roe": float(cells[4]),
                "net_profit_growth": float(cells[5].replace("%", "").replace("+", "")),
                "dividend_yield": float(cells[6].replace("%", "")),
            }
        except ValueError:
            continue

    return snapshot

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
    watchlist = load_watchlist({})
    bundle = get_fundamental_bundle(code, watchlist_data=watchlist)
    return {
        'pb': float(bundle.get('pb', 0) or 0),
        'pe': float(bundle.get('pe', 0) or 0),
        'roe': float(bundle.get('roe', 0) or 0),
        'net_profit_growth': float(bundle.get('net_profit_growth', 0) or 0),
        'dividend_yield': float(bundle.get('dividend_yield', 0) or 0),
        'market_cap': float(bundle.get('market_cap', 0) or 0),
        'source': bundle.get('source', 'snapshot'),
        'fetched_at': bundle.get('fetched_at'),
    }


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
    
    pool_entry = next((item for item in load_stock_pool_candidates() if item["code"] == code), {})

    analysis = {
        'code': code,
        'name': stock_data['name'],
        'industry': industry,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'price': stock_data['price'],
        'change_pct': stock_data['change_pct'],
        'pe': float(fundamental.get('pe', 0) or 0),
        'pb': float(fundamental.get('pb', 0) or 0),
        'market_cap': float(fundamental.get('market_cap', 0) or pool_entry.get('market_cap', 0) or 0),
        'dividend_yield': float(fundamental.get('dividend_yield', 0) or 0),
        'roe': fundamental.get('roe', 10),
        'net_profit_growth': float(fundamental.get('net_profit_growth', 0) or 0),
        'fundamental_source': fundamental.get('source', 'snapshot'),
    }
    
    # 评分（基于投资框架）
    score = 0
    reasons = []
    
    score = 50  # 基础分
    reasons.append(f"{industry}行业")
    if pool_entry.get("reason"):
        reasons.append(str(pool_entry["reason"]))
    
    # 价格位置评分
    if stock_data['change_pct'] < -5:
        score += 15
        reasons.append(f"大跌{stock_data['change_pct']:.1f}%（关注机会）")
    elif stock_data['change_pct'] < 0:
        score += 5
        reasons.append(f"调整中（{stock_data['change_pct']:.1f}%）")
    
    # PB / ROE / 股息率评分
    if 0 < analysis['pb'] < 2.5:
        score += 10
        reasons.append(f"PB较低（{analysis['pb']:.2f}）")

    if fundamental.get('roe', 0) > 15:
        score += 20
        reasons.append(f"高 ROE（{fundamental['roe']:.1f}%）")
    elif fundamental.get('roe', 0) > 10:
        score += 10
        reasons.append(f"ROE{fundamental.get('roe', 0):.1f}%")

    if analysis['dividend_yield'] >= 2:
        score += 5
        reasons.append(f"股息率 {analysis['dividend_yield']:.1f}%")
    
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
    print(f"市值：{analysis['market_cap']:.1f}亿")
    print(f"股息率：{analysis['dividend_yield']:.1f}%")
    print(f"ROE: {fundamental.get('roe', 0):.1f}%")
    print(f"基本面来源：{analysis['fundamental_source']}")
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
    watchlist = load_watchlist({})
    
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
    
    save_watchlist(watchlist)
    
    print(f"\n✅ 已加入观察池：{analysis['name']} ({analysis['code']})")


def send_feishu_notification(analysis: dict):
    """发送飞书通知"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from feishu_notifier import send_feishu_message

        title = f"📊 每日深度研究 - {analysis['name']}"
        content = f"""股票：{analysis['name']} ({analysis['code']})
行业：{analysis['industry']}
日期：{analysis['date']}

💰 估值数据
当前价：¥{analysis['price']:.2f}
PE: {analysis['pe']:.1f} | PB: {analysis['pb']:.2f}
市值：{analysis['market_cap']:.1f}亿
股息率：{analysis['dividend_yield']:.1f}%
ROE: {analysis['roe']:.1f}%
基本面来源：{analysis.get('fundamental_source', 'snapshot')}

📈 评级
综合评分：{analysis['score']}分
评级：{analysis['recommendation']}
目标价：¥{analysis['target_price']:.2f} (+{((analysis['target_price']/analysis['price']-1)*100):.0f}%)
止损价：¥{analysis['stop_loss']:.2f} (-{((1-analysis['stop_loss']/analysis['price'])*100):.0f}%)

🎯 推荐理由
{chr(10).join('• ' + r for r in analysis['reasons'])}

已加入观察池，持续跟踪。"""

        send_feishu_message(title=title, content=content, level='info')
    except Exception as e:
        print(f"发送飞书通知失败：{e}")


def select_stock_to_research():
    """从股票池选择 1 只未研究的股票"""
    positions = set(load_positions({}).keys())
    watchlist = set(load_watchlist({}).keys())
    candidates = load_stock_pool_candidates()

    for candidate in candidates:
        code = str(candidate["code"])
        if code not in positions and code not in watchlist:
            return code, str(candidate["name"]), str(candidate["industry"])

    if candidates:
        fallback = candidates[0]
        return str(fallback["code"]), str(fallback["name"]), str(fallback["industry"])

    raise RuntimeError("stock_pool.md 中未解析到可研究股票")


def main():
    """主函数"""
    try:
        with task_lock("daily_stock_research"):
            positions = load_positions({})
            watchlist = load_watchlist({})
            guard = evaluate_runtime_mode(
                "research",
                universe_count=len(load_stock_pool_candidates()) or len(watchlist) or len(positions),
            )
            for warning in guard.warnings:
                print(f"⚠️ {warning}")
                record_guardrail_event("daily_stock_research", "warning", warning)
            if not guard.ok:
                for reason in guard.reasons:
                    print(f"⛔ {reason}")
                    record_guardrail_event("daily_stock_research", "error", reason)
                return

            print("=" * 60)
            print(f"📚 每日深度研究 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print("=" * 60)

            code, name, industry = select_stock_to_research()
            print(f"\n🎯 今日研究：{name} ({code}) - {industry}")

            analysis = analyze_stock(code, name, industry)
            if not analysis:
                print("❌ 分析失败")
                return

            add_to_watchlist(analysis)
            send_feishu_notification(analysis)

            report_file = DATA_DIR / f"research_{code}_{analysis['date']}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
            print(f"\n📄 报告已保存：{report_file}")
            record_guardrail_success("daily_stock_research", f"研究完成: {code}")
    except TaskLockedError as exc:
        print(f"⚠️ {exc}")
        record_guardrail_event("daily_stock_research", "warning", str(exc))


if __name__ == "__main__":
    main()
