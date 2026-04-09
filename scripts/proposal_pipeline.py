#!/usr/bin/env python3
"""Proposal pipeline helper for the multi-agent stock workflow."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from core.proposals import get_pipeline_snapshot
from scripts.auto_trader_v3 import AutoTraderV3


def show_status() -> int:
    snapshot = get_pipeline_snapshot()
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


def advance_pipeline() -> int:
    trader = AutoTraderV3()
    approved = trader.build_pipeline_buy_signals()
    payload = {
        "approved_candidates": approved,
        "snapshot": get_pipeline_snapshot(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"status", "advance"}:
        print("用法: python3 proposal_pipeline.py <status|advance>")
        return 1
    if sys.argv[1] == "status":
        return show_status()
    return advance_pipeline()


if __name__ == "__main__":
    raise SystemExit(main())
