#!/usr/bin/env python3
"""
中国股市智能投资团队 - 执行器
"""

import sqlite3
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "database" / "stock_team.db"

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_pending_proposals():
    """获取待处理提案"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM proposals 
        WHERE status IN ('pending', 'quant_validated', 'risk_checked')
        ORDER BY priority DESC, created_at ASC
    """)
    
    proposals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return proposals

def get_positions():
    """获取当前持仓"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM positions WHERE status = 'holding'")
    positions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return positions

def get_account():
    """获取账户信息"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM account ORDER BY date DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def update_proposal_status(proposal_id, status, metadata=None):
    """更新提案状态"""
    conn = get_db()
    cursor = conn.cursor()
    
    if metadata:
        cursor.execute("""
            UPDATE proposals 
            SET status = ?, metadata = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, json.dumps(metadata), proposal_id))
    else:
        cursor.execute("""
            UPDATE proposals 
            SET status = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, proposal_id))
    
    conn.commit()
    conn.close()

def add_log(agent, event_type, event_data):
    """添加日志"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO agent_logs (agent, event_type, event_data)
        VALUES (?, ?, ?)
    """, (agent, event_type, json.dumps(event_data, ensure_ascii=False)))
    
    conn.commit()
    conn.close()

def create_proposal(symbol, name, direction, thesis, target_price, stop_loss, source_agent="manual"):
    """创建投资提案"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO proposals (symbol, name, direction, thesis, target_price, stop_loss, source_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (symbol, name, direction, thesis, target_price, stop_loss, source_agent))
    
    proposal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    add_log(source_agent, "proposal_created", {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "direction": direction
    })
    
    return proposal_id

def get_status():
    """获取系统状态"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 提案统计
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) as executed
        FROM proposals
    """)
    proposals = dict(cursor.fetchone())
    
    # 持仓统计
    cursor.execute("""
        SELECT 
            COUNT(*) as count,
            SUM(market_value) as total_value,
            SUM(profit_loss) as total_profit
        FROM positions WHERE status = 'holding'
    """)
    positions = dict(cursor.fetchone())
    
    # 账户信息
    cursor.execute("SELECT * FROM account ORDER BY date DESC LIMIT 1")
    account = dict(cursor.fetchone()) if cursor.fetchone() else None
    
    conn.close()
    
    return {
        "proposals": proposals,
        "positions": positions,
        "account": account
    }

def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python3 executor.py <命令> [参数]")
        print("命令:")
        print("  status               查看系统状态")
        print("  proposals            查看待处理提案")
        print("  positions            查看当前持仓")
        print("  account              查看账户信息")
        print("  create               创建提案（交互式）")
        print("  init                 初始化数据库")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "status":
        status = get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    
    elif command == "proposals":
        proposals = get_pending_proposals()
        print(json.dumps(proposals, ensure_ascii=False, indent=2))
    
    elif command == "positions":
        positions = get_positions()
        print(json.dumps(positions, ensure_ascii=False, indent=2))
    
    elif command == "account":
        account = get_account()
        print(json.dumps(account, ensure_ascii=False, indent=2))
    
    elif command == "init":
        import subprocess
        schema_path = BASE_DIR / "database" / "schema.sql"
        result = subprocess.run(
            ["sqlite3", str(DB_PATH)],
            stdin=open(schema_path),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ 数据库初始化成功")
        else:
            print(f"❌ 初始化失败: {result.stderr}")
    
    elif command == "create":
        print("创建投资提案（输入 q 退出）")
        symbol = input("股票代码: ")
        if symbol == 'q':
            return
        
        name = input("股票名称: ")
        direction = input("方向 (buy/sell): ")
        thesis = input("投资逻辑: ")
        target_price = float(input("目标价: "))
        stop_loss = float(input("止损价: "))
        
        proposal_id = create_proposal(symbol, name, direction, thesis, target_price, stop_loss)
        print(f"✅ 提案创建成功，ID: {proposal_id}")
    
    else:
        print("未知命令")
        sys.exit(1)

if __name__ == "__main__":
    main()
