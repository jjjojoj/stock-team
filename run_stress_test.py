#!/usr/bin/env python3
"""临时脚本 - 运行压力测试"""

import sys
import os

# 设置路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

print("开始执行压力测试...")
print(f"工作目录: {PROJECT_ROOT}")
sys.stdout.flush()

# 导入backtester模块
try:
    from scripts.backtester import Backverifyer, main
    print("成功导入 backtester 模块")
    sys.stdout.flush()
except Exception as e:
    print(f"导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 手动设置 sys.argv
sys.argv = ['backtester.py', 'stress_test']

# 执行 main 函数
try:
    print("\n执行 main()...")
    sys.stdout.flush()
    main()
    print("\nmain() 执行完成")
    sys.stdout.flush()
except Exception as e:
    print(f"执行失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n压力测试脚本结束")
sys.stdout.flush()
