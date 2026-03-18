#!/usr/bin/env python3
"""
示例：使用多数据源适配器分析股票
展示新模块的完整用法
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 添加虚拟环境
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / "python3.14" / "site-packages"
sys.path.insert(0, str(VENV_PATH))

from adapters import get_data_manager, DataSource
from knowledge import get_knowledge_base


def analyze_stock(symbol: str) -> dict:
    """
    分析一只股票
    
    Args:
        symbol: 股票代码，如 sh.600519
    
    Returns:
        分析结果
    """
    print(f"\n{'='*60}")
    print(f"📊 分析股票: {symbol}")
    print(f"{'='*60}")
    
    dm = get_data_manager()
    kb = get_knowledge_base()
    
    results = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
    }
    
    # 1. 获取实时价格
    print("\n💰 获取实时价格...")
    price = dm.get_realtime_price(symbol)
    if price:
        print(f"  价格: ¥{price.price}")
        print(f"  涨跌幅: {price.change_percent}%")
        print(f"  数据源: {price.source.value}")
        results["price"] = float(price.price)
        results["change_percent"] = float(price.change_percent or 0)
    else:
        print("  ❌ 获取失败")
    
    # 2. 获取历史数据
    print("\n📈 获取历史数据（30天）...")
    end = datetime.now()
    start = end - timedelta(days=30)
    prices = dm.get_historical_prices(symbol, start, end)
    if prices:
        print(f"  获取到 {len(prices)} 条记录")
        print(f"  最新: ¥{prices[-1].close_price}")
        print(f"  最早: ¥{prices[0].close_price}")
        results["history_count"] = len(prices)
    else:
        print("  ❌ 获取失败")
    
    # 3. 计算技术指标
    print("\n📊 计算技术指标...")
    tech = dm.get_technical_indicators(symbol, lookback_days=60)
    if tech:
        print(f"  RSI(14): {tech.rsi_14:.2f}")
        print(f"  MACD: {tech.macd:.4f}")
        print(f"  布林带: [{tech.bb_lower:.2f}, {tech.bb_middle:.2f}, {tech.bb_upper:.2f}]")
        results["technical"] = {
            "rsi": tech.rsi_14,
            "macd": tech.macd,
            "bb_upper": tech.bb_upper,
            "bb_middle": tech.bb_middle,
            "bb_lower": tech.bb_lower,
        }
    else:
        print("  ❌ 计算失败")
    
    # 4. 搜索知识库中的相关教训
    print("\n📚 搜索历史教训...")
    stock_name = symbol.split(".")[1] if "." in symbol else symbol
    lessons = kb.search_lessons(stock_name, top_k=3)
    if lessons:
        print(f"  找到 {len(lessons)} 条相关教训")
        for item, score in lessons:
            print(f"  - {item.content[:50]}... (相似度: {score:.2f})")
        results["related_lessons"] = len(lessons)
    else:
        print("  ⚠️ 未找到相关教训")
    
    return results


def main():
    """主函数"""
    print("=" * 60)
    print("📊 股票分析示例 - 多数据源适配器 + 知识库")
    print("=" * 60)
    
    # 分析贵州茅台
    analyze_stock("sh.600519")
    
    # 分析贵研铂业
    analyze_stock("sh.600459")
    
    print("\n" + "=" * 60)
    print("✅ 分析完成")
    print("=" * 60)
    
    # 显示知识库统计
    kb = get_knowledge_base()
    print(f"\n📚 知识库统计:")
    print(f"  总条目: {kb.count()}")


if __name__ == "__main__":
    main()
