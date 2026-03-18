#!/usr/bin/env python3
"""测试 API 连接"""
import os
import json
import sys
from datetime import datetime

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
os.chdir(PROJECT_ROOT)

def test_imports():
    """测试依赖包导入"""
    print("🧪 测试依赖包导入...")
    try:
        import bs4
        print("  ✅ beautifulsoup4")
    except ImportError as e:
        print(f"  ❌ beautifulsoup4: {e}")
        return False

    try:
        import baostock
        print("  ✅ baostock")
    except ImportError as e:
        print(f"  ❌ baostock: {e}")
        return False

    try:
        import akshare as ak
        print("  ✅ akshare")
    except ImportError as e:
        print(f"  ❌ akshare: {e}")
        return False

    return True

def test_database():
    """测试数据库连接"""
    print("\n🧪 测试数据库连接...")
    try:
        import sqlite3

        # 测试 stock_team.db
        conn = sqlite3.connect("database/stock_team.db")
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"  ✅ stock_team.db 表数量: {len(tables)}")

        required_tables = ['agents', 'predictions', 'proposals', 'trades', 'agent_logs', 'positions']
        missing = [t for t in required_tables if t not in tables]
        if missing:
            print(f"  ❌ stock_team.db 缺失的表: {missing}")
            conn.close()
            return False
        else:
            print(f"  ✅ stock_team.db 所有关键表都存在")

        # 检查数据
        cursor.execute("SELECT COUNT(*) FROM agents")
        agents_count = cursor.fetchone()[0]
        print(f"  ✅ agents 表记录数: {agents_count}")

        cursor.execute("SELECT COUNT(*) FROM proposals")
        proposals_count = cursor.fetchone()[0]
        print(f"  ✅ proposals 表记录数: {proposals_count}")

        cursor.execute("SELECT COUNT(*) FROM trades")
        trades_count = cursor.fetchone()[0]
        print(f"  ✅ trades 表记录数: {trades_count}")

        cursor.execute("SELECT COUNT(*) FROM predictions")
        predictions_count = cursor.fetchone()[0]
        print(f"  ✅ predictions 表记录数: {predictions_count}")

        conn.close()

        # 测试 performance.db
        perf_conn = sqlite3.connect("database/performance.db")
        perf_cursor = perf_conn.cursor()

        perf_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        perf_tables = [row[0] for row in perf_cursor.fetchall()]
        print(f"  ✅ performance.db 表数量: {len(perf_tables)}")

        perf_required = ['member_performance', 'warnings', 'eliminations']
        perf_missing = [t for t in perf_required if t not in perf_tables]
        if perf_missing:
            print(f"  ❌ performance.db 缺失的表: {perf_missing}")
            perf_conn.close()
            return False
        else:
            print(f"  ✅ performance.db 所有关键表都存在")

        perf_cursor.execute("SELECT COUNT(*) FROM member_performance")
        perf_count = perf_cursor.fetchone()[0]
        print(f"  ✅ member_performance 表记录数: {perf_count}")

        perf_conn.close()

        return True

    except Exception as e:
        print(f"  ❌ 数据库测试失败: {e}")
        return False

def test_api_configs():
    """测试 API 配置"""
    print("\n🧪 测试 API 配置...")
    try:
        with open("config/api_config.json", 'r') as f:
            api_config = json.load(f)
        print("  ✅ api_config.json 存在")

        # 检查关键配置
        if "zhipu" in api_config and api_config["zhipu"].get("enabled"):
            api_key = api_config["zhipu"].get("api_key")
            if api_key and api_key.startswith(""):
                print(f"  ✅ 智谱 API 已配置 (密钥: {api_key[:10]}...)")
            else:
                print("  ⚠️ 智谱 API 密钥格式异常")

        if "mcp_services" in api_config:
            print(f"  ✅ MCP 服务配置存在")

        return True

    except Exception as e:
        print(f"  ❌ API 配置测试失败: {e}")
        return False

def test_baostock_connection():
    """测试 baostock 连接"""
    print("\n🧪 测试 baostock 连接...")
    try:
        import baostock as bs
        lg = bs.login()

        if lg.error_code == '0':
            print("  ✅ baostock 登录成功")

            # 测试获取数据
            rs = bs.query_history_k_data_plus("sz.000792",
                "date,code,open,high,low,close,volume",
                start_date='2026-03-10', end_date='2026-03-15',
                frequency="d", adjustflag="3")

            if rs.error_code == '0':
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                print(f"  ✅ 获取到 {len(data_list)} 条数据")

                if data_list:
                    latest = data_list[0]
                    print(f"  ✅ 最新数据: {latest[0]} 收盘价 {latest[5]}")

            bs.logout()
            return True
        else:
            print(f"  ❌ baostock 登录失败: {lg.error_msg}")
            return False

    except Exception as e:
        print(f"  ❌ baostock 测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 中国股市智能投资团队 - 系统测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = {
        "依赖包导入": test_imports(),
        "数据库": test_database(),
        "API 配置": test_api_configs(),
        "baostock 连接": test_baostock_connection(),
    }

    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查上述错误")
    print("=" * 60)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
