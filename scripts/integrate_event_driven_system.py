#!/usr/bin/env python3
"""
事件驱动股票团队 - 主集成脚本
一键部署所有功能
"""

import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "web" / "dashboard_claude.py"


def start_dashboard():
    """启动仪表盘"""
    print("🚀 启动事件驱动仪表盘...")
    try:
        subprocess.Popen([sys.executable, str(DASHBOARD_PATH)], 
                        cwd=str(PROJECT_ROOT))
        print("✅ 仪表盘已启动: http://localhost:8082")
    except Exception as e:
        print(f"❌ 仪表盘启动失败: {e}")


def run_health_check():
    """运行健康检查"""
    print("\n🔍 运行系统健康检查...")
    health_script = PROJECT_ROOT / "scripts" / "system_health_check.py"
    try:
        result = subprocess.run([sys.executable, str(health_script)], 
                              cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 健康检查通过")
        else:
            print(f"⚠️ 健康检查警告:\n{result.stdout}")
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")


def test_event_api():
    """测试事件API"""
    print("\n🧪 测试事件API端点...")
    import requests
    
    try:
        # 测试概览API
        response = requests.get("http://localhost:8082/api/overview", timeout=5)
        if response.status_code == 200:
            print("✅ /api/overview 工作正常")
        else:
            print(f"❌ /api/overview 返回状态码: {response.status_code}")
            
        # 测试事件分析API
        response = requests.get("http://localhost:8082/api/event-analysis", timeout=5)
        if response.status_code == 200:
            print("✅ /api/event-analysis 工作正常")
        else:
            print(f"❌ /api/event-analysis 返回状态码: {response.status_code}")
            
        # 测试K线API
        response = requests.get("http://localhost:8082/api/stocks/sz.000792/kline-with-events", timeout=5)
        if response.status_code == 200:
            print("✅ /api/stocks/*/kline-with-events 工作正常")
        else:
            print(f"❌ /api/stocks/*/kline-with-events 返回状态码: {response.status_code}")
            
    except Exception as e:
        print(f"⚠️ API测试异常: {e}")


def main():
    """主函数"""
    print("=" * 50)
    print("📊 事件驱动股票团队 - 集成部署")
    print("=" * 50)
    
    # 1. 启动仪表盘
    start_dashboard()
    
    # 2. 运行健康检查
    run_health_check()
    
    # 3. 测试API
    test_event_api()
    
    print("\n" + "=" * 50)
    print("🎯 部署完成！")
    print("📋 访问地址: http://localhost:8082")
    print("📈 功能亮点:")
    print("   • 事件时间线显示")
    print("   • K线图事件标记")
    print("   • 事件驱动的Agent协作")
    print("   • 自动模式识别和规则生成")
    print("   • 实时健康监控")
    print("=" * 50)


if __name__ == "__main__":
    main()