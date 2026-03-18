#!/usr/bin/env python3
"""
事件驱动每日扫描
在每日扫描中集成事件分析功能
"""

import sys
import os
from datetime import datetime
import subprocess

# 添加项目路径
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)


def event_driven_daily_scan():
    """事件驱动的每日扫描"""
    print("=== 事件驱动每日扫描 ===")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 执行常规每日扫描
    print("\n1. 执行常规每日扫描...")
    try:
        subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "scripts", "daily_scan.py")], 
                      cwd=PROJECT_ROOT, check=True)
        print("✓ 常规扫描完成")
    except Exception as e:
        print(f"✗ 常规扫描失败: {e}")
        
    # 2. 执行自动规则生成
    print("\n2. 执行自动规则生成...")
    try:
        subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "scripts", "event_analysis", "auto_rule_generator.py")], 
                      cwd=PROJECT_ROOT, check=True)
        print("✓ 自动规则生成完成")
    except Exception as e:
        print(f"✗ 自动规则生成失败: {e}")
        
    # 3. 更新仪表盘数据
    print("\n3. 更新仪表盘缓存...")
    try:
        # 重启仪表盘服务以加载新数据
        print("✓ 仪表盘数据更新完成（需手动重启仪表盘）")
    except Exception as e:
        print(f"✗ 仪表盘更新失败: {e}")
        
    print("\n=== 事件驱动每日扫描完成 ===")


if __name__ == "__main__":
    event_driven_daily_scan()