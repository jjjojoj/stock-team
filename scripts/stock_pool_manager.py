#!/usr/bin/env python3
"""
股票池管理系统

功能：
1. 股票池容量管理（最多 20 支）
2. 淘汰机制：最不看好/不符合逻辑 → 淘汰池
3. 轮转：从股票池候选中补充新股票
4. 评分排序：基于预测置信度 + 近期表现
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(PROJECT_ROOT))

from core.storage import load_watchlist, save_watchlist

# 股票池配置
MAX_POOL_SIZE = 20
MIN_POOL_SIZE = 15  # 低于此数量时补充


def load_json(file: Path) -> dict:
    """加载 JSON 文件"""
    if file.exists():
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_json(file: Path, data: dict):
    """保存 JSON 文件"""
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_stock_score(code: str, watchlist: dict, predictions: dict) -> float:
    """
    计算股票评分（用于排序淘汰）
    
    评分因素：
    1. 预测置信度（40%）
    2. 近期预测准确率（30%）
    3. 持仓表现（20%）
    4. 行业景气度（10%）
    """
    score = 50.0  # 基础分
    
    # 1. 预测置信度（40%）
    # 查找该股票最新的预测
    latest_pred = None
    for pred_id, pred in predictions.get('active', {}).items():
        if pred.get('code') == code:
            if latest_pred is None or pred.get('created_at', '') > latest_pred.get('created_at', ''):
                latest_pred = pred
    
    if latest_pred:
        confidence = latest_pred.get('confidence', 50)
        score += (confidence - 50) * 0.4  # 置信度 80 → +12 分
    
    # 2. 近期预测准确率（30%）
    # 从学习记录中查找
    learning_file = DATA_DIR / "learning" / "memory.md"
    if learning_file.exists():
        with open(learning_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # 简化：如果有成功记录，加分
            if f"成功：{code}" in content or f"成功：{code.split('.')[1]}" in content:
                score += 15
            if f"失败：{code}" in content or f"失败：{code.split('.')[1]}" in content:
                score -= 15
    
    # 3. 持仓表现（20%）
    positions = load_json(CONFIG_DIR / "positions.json")
    if code in positions:
        pos = positions[code]
        cost = pos.get('cost_price', 0)
        if cost > 0:
            # 获取当前价
            current = pos.get('current_price', cost)
            pnl_pct = (current - cost) / cost * 100
            score += pnl_pct * 0.2  # 盈利 10% → +2 分
    
    # 4. 优先级（10%）
    if code in watchlist:
        priority = watchlist[code].get('priority', 'medium')
        if priority == 'high':
            score += 10
        elif priority == 'low':
            score -= 10
    
    return score


def find_elimination_candidate(watchlist: dict, predictions: dict) -> str:
    """
    找出最应该淘汰的股票
    
    淘汰标准：
    1. 评分最低
    2. 预测置信度持续低（<50%）
    3. 不符合当前选股逻辑
    """
    if len(watchlist) <= MIN_POOL_SIZE:
        return None
    
    # 计算所有股票评分
    scores = {}
    for code in watchlist.keys():
        scores[code] = get_stock_score(code, watchlist, predictions)
    
    # 找出最低分
    if not scores:
        return None
    
    min_code = min(scores, key=scores.get)
    min_score = scores[min_code]
    
    print(f"📊 股票评分排行（最低分淘汰）:")
    for code, score in sorted(scores.items(), key=lambda x: x[1])[:5]:
        name = watchlist.get(code, {}).get('name', '?')
        print(f"   {name} ({code}): {score:.1f}分")
    
    # 如果最低分<40，建议淘汰
    if min_score < 40:
        return min_code
    
    return None


def find_replacement_candidate() -> dict:
    """
    从候选池中找替代股票
    
    候选来源：
    1. stock_pool.md 中未加入观察池的股票
    2. 每日研究新发现的股票
    """
    # 读取股票池配置
    pool_file = CONFIG_DIR / "stock_pool.md"
    watchlist = load_watchlist({})
    positions = load_json(CONFIG_DIR / "positions.json")
    
    # 已存在的股票（观察池 + 持仓）
    existing = set(watchlist.keys()) | set(positions.keys())
    
    # 候选股票（从 stock_pool.md 解析，简化版：硬编码）
    candidates = [
        {"code": "sh.601168", "name": "西部矿业", "industry": "铜", "priority": "high"},
        {"code": "sh.600362", "name": "江西铜业", "industry": "铜", "priority": "medium"},
        {"code": "sh.601600", "name": "中国铝业", "industry": "铝", "priority": "medium"},
        {"code": "sz.000807", "name": "云铝股份", "industry": "铝", "priority": "high"},
        {"code": "sh.600547", "name": "山东黄金", "industry": "黄金", "priority": "medium"},
        {"code": "sh.601899", "name": "紫金矿业", "industry": "黄金", "priority": "low"},
        {"code": "sh.688396", "name": "华润微", "industry": "芯片", "priority": "high"},
        {"code": "sh.688037", "name": "芯源微", "industry": "芯片", "priority": "medium"},
    ]
    
    # 找出未在观察池的
    available = [c for c in candidates if c['code'] not in existing]
    
    if not available:
        return None
    
    # 返回优先级最高的
    available.sort(key=lambda x: {'high': 0, 'medium': 1, 'low': 2}.get(x.get('priority', 'medium'), 1))
    return available[0]


def manage_pool(action: str = "auto"):
    """
    管理股票池
    
    action: "auto"=自动检查，"eliminate"=手动淘汰，"add"=手动添加
    """
    print("=" * 60)
    print(f"📈 股票池管理 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 加载数据
    watchlist = load_watchlist({})
    eliminated = load_json(CONFIG_DIR / "eliminated_pool.json")
    predictions = load_json(DATA_DIR / "predictions.json")
    
    print(f"\n当前观察池：{len(watchlist)}只股票")
    print(f"淘汰池：{len(eliminated)}只股票")
    print(f"容量上限：{MAX_POOL_SIZE}只")
    print()
    
    if action == "auto":
        # 自动检查是否需要淘汰
        if len(watchlist) >= MAX_POOL_SIZE:
            print("⚠️  观察池已满，检查是否需要淘汰...")
            candidate = find_elimination_candidate(watchlist, predictions)
            
            if candidate:
                name = watchlist[candidate].get('name', '?')
                print(f"\n🔴 建议淘汰：{name} ({candidate})")
                print(f"   原因：评分过低/不符合当前选股逻辑")
                
                # 移动到淘汰池
                eliminated[candidate] = watchlist[candidate]
                eliminated[candidate]['eliminated_date'] = datetime.now().isoformat()
                eliminated[candidate]['reason'] = '评分过低'
                del watchlist[candidate]
                
                # 添加新股票
                replacement = find_replacement_candidate()
                if replacement:
                    print(f"\n🟢 补充新股：{replacement['name']} ({replacement['code']})")
                    watchlist[replacement['code']] = {
                        'name': replacement['name'],
                        'industry': replacement['industry'],
                        'added_date': datetime.now().strftime('%Y-%m-%d'),
                        'priority': replacement.get('priority', 'medium'),
                        'reason': '股票池轮转补充',
                    }
            else:
                print("✅ 无需淘汰，所有股票评分合理")
        
        elif len(watchlist) < MIN_POOL_SIZE:
            print(f"⚠️  观察池股票不足（{len(watchlist)}<{MIN_POOL_SIZE}），补充新股...")
            replacement = find_replacement_candidate()
            if replacement:
                print(f"🟢 补充新股：{replacement['name']} ({replacement['code']})")
                watchlist[replacement['code']] = {
                    'name': replacement['name'],
                    'industry': replacement['industry'],
                    'added_date': datetime.now().strftime('%Y-%m-%d'),
                    'priority': replacement.get('priority', 'medium'),
                    'reason': '股票池补充',
                }
        else:
            print(f"✅ 股票池数量正常（{len(watchlist)}只，范围{MIN_POOL_SIZE}-{MAX_POOL_SIZE}）")
    
    # 保存
    save_watchlist(watchlist)
    save_json(CONFIG_DIR / "eliminated_pool.json", eliminated)
    
    print(f"\n✅ 股票池更新完成")
    print(f"   观察池：{len(watchlist)}只")
    print(f"   淘汰池：{len(eliminated)}只")
    
    # 打印淘汰池历史
    if eliminated:
        print(f"\n📋 最近淘汰记录:")
        for code, info in list(eliminated.items())[-5:]:
            date = info.get('eliminated_date', '?')[:10]
            reason = info.get('reason', '?')
            print(f"   {info.get('name', '?')} ({code}): {date} - {reason}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="股票池管理")
    parser.add_argument("action", nargs="?", default="auto", 
                       choices=["auto", "eliminate", "add", "list"],
                       help="auto=自动检查，eliminate=淘汰，add=添加，list=列表")
    args = parser.parse_args()
    
    if args.action == "list":
        watchlist = load_json(CONFIG_DIR / "watchlist.json")
        print("\n📈 观察池股票:")
        for code, info in watchlist.items():
            priority = info.get('priority', '?')
            industry = info.get('industry', '?')
            added = info.get('added_date', '?')
            print(f"   {info.get('name', '?')} ({code}) | {industry} | 优先级:{priority} | 加入:{added}")
    else:
        manage_pool(args.action)


if __name__ == "__main__":
    main()
