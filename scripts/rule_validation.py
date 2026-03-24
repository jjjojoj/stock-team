#!/usr/bin/env python3
"""
兼容入口：规则验证已合并到 rule_validator.py。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rule_validator import main


if __name__ == "__main__":
    main()
