#!/usr/bin/env python3
"""Archive current paper ledger and reset the live account baseline."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.storage import reset_operational_ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="重置模拟交易账本")
    parser.add_argument("--capital", type=float, default=200000.0, help="新的模拟初始资金")
    parser.add_argument(
        "--reason",
        default="重置模拟账本基线，丢弃历史脏账并从新的资金基线重新开始",
        help="重置原因，会写入归档文件",
    )
    args = parser.parse_args()

    result = reset_operational_ledger(
        args.capital,
        reset_at=datetime.now(),
        reason=args.reason,
    )

    print("✅ 模拟账本已重置")
    print(f"📅 基线日期: {result['baseline_date']}")
    print(f"💰 初始资金: ¥{result['total_capital']:,.2f}")
    print(f"📦 归档文件: {result['archive_path']}")


if __name__ == "__main__":
    main()
