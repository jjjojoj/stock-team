#!/usr/bin/env python3
"""持仓同步脚本，统一通过公共同步层更新 dashboard 数据。"""

import argparse
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE_DIR))

from core.storage import DB_PATH, PORTFOLIO_FILE, POSITIONS_FILE, load_json, sync_positions_and_account_to_db


def get_db_positions():
    """获取数据库中的 holding 持仓，用于 dry-run 展示。"""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT * FROM positions WHERE status = 'holding'")
        return {row["symbol"]: dict(row) for row in cursor.fetchall()}
    finally:
        conn.close()


def sync_positions(dry_run: bool = False):
    """同步 JSON 持仓到数据库，并刷新 account 汇总。"""
    print("📊 持仓同步脚本")
    print("=" * 50)
    print(f"📁 JSON文件: {POSITIONS_FILE}")
    print(f"🗄️ 数据库: {DB_PATH}")
    print()

    json_positions = load_json(POSITIONS_FILE, {})
    portfolio = load_json(PORTFOLIO_FILE, {"total_capital": 200000, "available_cash": 0})
    db_positions = get_db_positions()

    print(f"📋 JSON持仓: {len(json_positions)} 只")
    print(f"📋 数据库持仓: {len(db_positions)} 只")
    print()

    stats = {
        "inserted": len(set(json_positions) - set(db_positions)),
        "updated": len(set(json_positions) & set(db_positions)),
        "deleted": len(set(db_positions) - set(json_positions)),
    }

    if dry_run:
        for symbol in sorted(set(json_positions) - set(db_positions)):
            print(f"📝 [DRY-RUN] 新增: {symbol}")
        for symbol in sorted(set(json_positions) & set(db_positions)):
            print(f"📝 [DRY-RUN] 更新: {symbol}")
        for symbol in sorted(set(db_positions) - set(json_positions)):
            print(f"📝 [DRY-RUN] 删除: {symbol}")
        print()
        print("📋 DRY-RUN 模式 - 未实际修改数据")
    else:
        metrics = sync_positions_and_account_to_db(
            json_positions,
            float(portfolio.get("available_cash", 0) or 0),
            portfolio,
            DB_PATH,
        )
        print("✅ 同步完成!")
        print(f"💰 总资产: ¥{metrics['total_asset']:,.2f}")
        print(f"📈 市值: ¥{metrics['market_value']:,.2f}")

    print()
    print("📊 统计:")
    print(f"   新增: {stats['inserted']} 只")
    print(f"   更新: {stats['updated']} 只")
    print(f"   删除: {stats['deleted']} 只")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="同步持仓数据")
    parser.add_argument("--dry-run", action="store_true", help="只显示操作，不实际执行")
    args = parser.parse_args()
    
    sync_positions(dry_run=args.dry_run)
