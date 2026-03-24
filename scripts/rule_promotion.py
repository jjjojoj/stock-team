#!/usr/bin/env python3
"""
兼容入口：规则晋升已并入统一规则验证器。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rule_validator import RuleValidator


def main() -> None:
    validator = RuleValidator()
    validator.validate_validation_pool()
    validator._save_data()


if __name__ == "__main__":
    main()
