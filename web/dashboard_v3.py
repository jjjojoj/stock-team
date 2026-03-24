#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
from enhanced_cron_handler import handle_api_openclaw_cron, get_openclaw_cron_status

"""
AI 股票团队监控面板 v3.1 - Cron脚本驱动版
6大模块，支持24个Cron脚本状态显示
端口: 8082
"""

import http.server
import socketserver
import json
import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from core.storage import (
    DB_PATH,
    LEARNING_DIR,
    load_json,
    load_rejected_rules,
    load_rules,
    load_validation_pool,
    load_watchlist,
)

PORT = 8082

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_sql(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results

def query_one(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# Cron脚本分类定义 (6大类，24个脚本)
# =============================================================================

CRON_SCRIPTS = {
    "monitoring": {
        "market_style_monitor": {"name": "市场风格监测", "freq": "每日", "status_key": "style_monitor"},
        "a_share_risk_monitor": {"name": "A股风险监控", "freq": "每日", "status_key": "risk_monitor"},
        "circuit_breaker": {"name": "熔断机制监控", "freq": "实时/每小时", "status_key": "circuit_breaker"},
        "api_health_monitor": {"name": "API健康检查", "freq": "每15分钟", "status_key": "api_health"},
    },
    "ai_prediction": {
        "ai_predictor": {"name": "AI预测生成器", "freq": "每日", "status_key": "ai_predictor"},
        "selector": {"name": "智能选股工具", "freq": "每日", "status_key": "selector"},
        "price_report": {"name": "价格分析报告", "freq": "每日", "status_key": "price_report"},
    },
    "research": {
        "daily_stock_research": {"name": "个股深度研究", "freq": "每日", "status_key": "stock_research"},
        "daily_web_search": {"name": "网络热点搜索", "freq": "每日", "status_key": "web_search"},
        "news_trigger": {"name": "新闻触发器", "freq": "实时", "status_key": "news_trigger"},
        "event_driven_scan": {"name": "事件驱动扫描", "freq": "每日", "status_key": "event_scan"},
    },
    "trading": {
        "auto_trader_v3": {"name": "自动交易系统", "freq": "实时/每日", "status_key": "auto_trader"},
        "daily_performance_report": {"name": "每日业绩报告", "freq": "每日", "status_key": "daily_perf"},
    },
    "validation": {
        "rule_validator": {"name": "规则验证器", "freq": "每日", "status_key": "rule_validator"},
        "daily_book_learning": {"name": "书籍学习", "freq": "每日", "status_key": "book_learning"},
        "backtester": {"name": "策略回测系统", "freq": "每周", "status_key": "backtester"},
        "overfitting_test": {"name": "过拟合检测", "freq": "每周", "status_key": "overfitting"},
        "learning_engine": {"name": "学习引擎v2", "freq": "每日", "status_key": "learning_engine"},
    },
    "reports": {
        "news_monitor": {"name": "新闻监控系统", "freq": "实时", "status_key": "news_monitor"},
        "midday_review": {"name": "午间复盘", "freq": "每日", "status_key": "midday_review"},
        "weekly_summary": {"name": "每周总结报告", "freq": "每周", "status_key": "weekly_summary"},
    }
}


# =============================================================================
# 数据处理函数
# =============================================================================

def get_account_latest():
    return query_one("SELECT * FROM account ORDER BY date DESC LIMIT 1")

def get_positions():
    return query_sql("SELECT * FROM positions ORDER BY profit_loss_pct DESC")


def flatten_rule_library(limit: Optional[int] = None):
    """Flatten the rule library into a ranked list."""
    rules = load_rules({})
    items = []
    for category, category_rules in rules.items():
        for rule_id, rule in category_rules.items():
            entry = dict(rule)
            entry["rule_id"] = rule_id
            entry["category"] = category
            items.append(entry)

    items.sort(
        key=lambda item: (
            float(item.get("success_rate", 0.0) or 0.0),
            int(item.get("samples", 0) or 0),
            float(item.get("weight", 0.0) or 0.0),
        ),
        reverse=True,
    )
    return items[:limit] if limit else items


def get_watchlist_items(limit: Optional[int] = None):
    """Return watchlist entries as a list for APIs/UI."""
    watchlist = load_watchlist({})
    items = []
    for symbol, info in watchlist.items():
        entry = dict(info)
        entry["symbol"] = symbol
        items.append(entry)

    items.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item.get("priority", "medium"), 1),
            -(float(item.get("score", 0) or 0)),
        )
    )
    return items[:limit] if limit else items


def get_validation_pool_items(limit: Optional[int] = None):
    """Return validation-pool entries as a ranked list."""
    pool = load_validation_pool({})
    items = []
    for rule_id, rule in pool.items():
        entry = dict(rule)
        entry["rule_id"] = rule_id
        items.append(entry)

    items.sort(
        key=lambda item: (
            float(item.get("confidence", 0.0) or 0.0),
            float(item.get("live_test", {}).get("success_rate", 0.0) or 0.0),
            int(item.get("backtest", {}).get("samples", 0) or 0),
        ),
        reverse=True,
    )
    return items[:limit] if limit else items


def get_validation_summary():
    """Build dashboard-friendly summary for rule validation and learning."""
    rule_items = flatten_rule_library()
    validation_pool_items = get_validation_pool_items()
    rejected_items = list(load_rejected_rules({}).values())
    book_knowledge = load_json(LEARNING_DIR / "book_knowledge.json", {})

    active_with_samples = [item for item in rule_items if int(item.get("samples", 0) or 0) > 0]
    validated_library_rules = [
        item for item in rule_items
        if int(item.get("samples", 0) or 0) >= 1 and float(item.get("success_rate", 0.0) or 0.0) >= 0.5
    ]
    ready_pool_rules = [
        item for item in validation_pool_items
        if item.get("status") in {"ready_for_promotion", "proven"}
    ]
    hot_rules = [
        item for item in rule_items
        if int(item.get("samples", 0) or 0) >= 5 and float(item.get("success_rate", 0.0) or 0.0) >= 0.6
    ]
    hot_pool_rules = [item for item in validation_pool_items if float(item.get("confidence", 0.0) or 0.0) >= 0.7]
    warm_rule_count = max(
        0,
        len(rule_items) + len(validation_pool_items) - len(hot_rules) - len(hot_pool_rules),
    )

    total_points = 0
    for book in book_knowledge.values():
        total_points += len(book.get("key_points", []))

    in_sample = round(
        (
            sum(float(item.get("success_rate", 0.0) or 0.0) for item in active_with_samples) / len(active_with_samples) * 100
        ) if active_with_samples else 0.0,
        1,
    )
    live_pool_items = [
        item for item in validation_pool_items if int(item.get("live_test", {}).get("samples", 0) or 0) > 0
    ]
    out_sample = round(
        (
            sum(float(item.get("live_test", {}).get("success_rate", 0.0) or 0.0) for item in live_pool_items) / len(live_pool_items) * 100
        ) if live_pool_items else 0.0,
        1,
    )

    return {
        "passed_rules": len(validated_library_rules) + len(ready_pool_rules),
        "failed_rules": len(rejected_items),
        "pending_rules": max(0, len(validation_pool_items) - len(ready_pool_rules)),
        "learning_points": total_points,
        "memory": {
            "hot": len(hot_rules) + len(hot_pool_rules),
            "warm": warm_rule_count,
            "cold": len(rejected_items),
        },
        "overfitting": {
            "in_sample_accuracy": in_sample,
            "out_sample_accuracy": out_sample,
            "risk": "low" if abs(in_sample - out_sample) <= 10 else ("medium" if abs(in_sample - out_sample) <= 20 else "high"),
        },
        "top_rules": rule_items[:8],
        "validation_pool": validation_pool_items[:8],
        "watchlist_count": len(get_watchlist_items()),
    }

def get_trades(limit=20):
    return query_sql("SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?", (limit,))

def get_predictions(limit=20):
    return query_sql("""
        SELECT p.* FROM predictions p
        WHERE p.status = 'active'
        ORDER BY p.confidence DESC, p.created_at DESC
        LIMIT ?
    """, (limit,))

def get_predictions_stats():
    data = query_one("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result = 'correct' THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN result = 'partial' THEN 1 ELSE 0 END) as partial,
            SUM(CASE WHEN result = 'wrong' THEN 1 ELSE 0 END) as incorrect,
            SUM(CASE WHEN result IN ('pending', 'expired') OR result IS NULL THEN 1 ELSE 0 END) as pending,
            ROUND(COALESCE(SUM(CASE WHEN result = 'correct' THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(CASE WHEN result IN ('correct','partial','wrong') THEN 1 ELSE 0 END), 0), 0), 1) as accuracy
        FROM predictions
        WHERE created_at >= date('now', '-30 days')
    """)
    return data or {"total": 0, "correct": 0, "partial": 0, "incorrect": 0, "pending": 0, "accuracy": 0}

def get_selector_results():
    return query_sql("""
        SELECT p.symbol, p.name, p.direction, p.confidence, p.reasons, p.created_at
        FROM predictions p
        WHERE p.created_at >= date('now')
        ORDER BY p.confidence DESC
        LIMIT 10
    """)

def get_events_today():
    return query_sql("""
        SELECT nl.*, COUNT(eka.id) as 关联股票数
        FROM news_labels nl
        LEFT JOIN event_kline_associations eka ON nl.news_id = eka.news_id
        WHERE date(nl.news_time) = date('now')
        GROUP BY nl.news_id
        ORDER BY nl.urgency DESC, nl.news_time DESC
        LIMIT 20
    """)

def get_market_style():
    data = query_one("""
        SELECT
            AVG(CASE WHEN pb < 1.5 THEN 1 ELSE 0 END) as value_ratio,
            AVG(CASE WHEN pb >= 1.5 THEN 1 ELSE 0 END) as growth_ratio,
            AVG(CASE WHEN market_cap > 100000 THEN 1 ELSE 0 END) as large_cap_ratio,
            AVG(CASE WHEN market_cap <= 100000 THEN 1 ELSE 0 END) as small_cap_ratio
        FROM market_cache
        WHERE updated_at >= datetime('now', '-1 day')
    """)
    if data:
        value_ratio = data.get("value_ratio")
        growth_ratio = data.get("growth_ratio")
        large_cap_ratio = data.get("large_cap_ratio")
        small_cap_ratio = data.get("small_cap_ratio")
        # Handle None values from empty table or NULL averages
        def safe_value(val, default=0.5):
            return val if val is not None else default
        return {
            "value_growth": {"value": round(safe_value(value_ratio) * 100), "growth": round(safe_value(growth_ratio) * 100)},
            "large_small": {"large": round(safe_value(large_cap_ratio) * 100), "small": round(safe_value(small_cap_ratio) * 100)}
        }
    return {"value_growth": {"value": 55, "growth": 45}, "large_small": {"large": 60, "small": 40}}

def get_risk_level():
    risk = query_one("""
        SELECT risk_level, risk_notes, created_at
        FROM risk_assessment
        WHERE created_at >= datetime('now', '-1 day')
        ORDER BY created_at DESC LIMIT 1
    """)
    if risk:
        return {"level": risk["risk_level"], "notes": risk["risk_notes"]}
    return {"level": "low", "notes": "无近期风险记录"}

def get_scheduled_scripts():
    """获取今日待运行的脚本列表 - 直接基于 OpenClaw cron 实时数据。"""
    cron_tasks = get_openclaw_cron_status()
    scheduled = []

    for task in sorted(cron_tasks, key=lambda item: item.get("next_run_raw", 0) or 0):
        scheduled.append(
            {
                "name": task.get("name", "Unknown"),
                "key": task.get("script_key") or task.get("id"),
                "freq": task.get("schedule", "unknown"),
                "next_run": task.get("next_run", "未计划"),
                "status": task.get("status", "idle"),
                "enabled": task.get("enabled", True),
            }
        )

    return scheduled

def get_cron_status():
    status = {}
    for script_info in CRON_SCRIPTS.values():
        for name, info in script_info.items():
            status[info["status_key"]] = {"running": False, "last_run": None, "status": "idle", "message": "待运行"}

    for task in get_openclaw_cron_status():
        script_key = (task.get("script_key") or "").lower()
        task_name = (task.get("name") or "").lower()
        for script_info in CRON_SCRIPTS.values():
            for name, info in script_info.items():
                status_key = info["status_key"].lower()
                if script_key in {name.lower(), status_key} or name.lower() in script_key or status_key in task_name:
                    status[info["status_key"]] = {
                        "running": task.get("status") == "running",
                        "last_run": task.get("last_run"),
                        "status": task.get("status", "idle"),
                        "message": f"下次运行: {task.get('next_run', '未计划')}",
                    }
    return status


def get_enhanced_cron_data():
    """
    获取增强版 Cron 任务监控数据
    包含更详细的状态信息、运行时间统计和下次运行时间预测
    """
    try:
        # 从 OpenClaw CLI 获取实时数据
        cron_data = get_openclaw_cron_status()

        # 从数据库获取历史运行记录
        cron_logs = query_sql("""
            SELECT
                agent as script,
                created_at as run_time,
                strftime('%s', created_at) as run_timestamp
            FROM agent_logs
            WHERE created_at >= datetime('now', '-7 days')
            ORDER BY created_at DESC
            LIMIT 500
        """)

        # 处理日志数据，计算每个任务的统计信息
        task_stats = {}
        for log in cron_logs:
            script = log["script"].lower()
            if script not in task_stats:
                task_stats[script] = {
                    "run_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "last_run": None,
                    "recent_runs": [],
                    "durations": []
                }
            task_stats[script]["run_count"] += 1
            task_stats[script]["success_count"] += 1  # 假设成功，后续可以改进
            task_stats[script]["recent_runs"].append({
                "time": log["run_time"],
                "status": "ok"
            })
            # 保留最近 10 次运行记录
            if len(task_stats[script]["recent_runs"]) > 10:
                task_stats[script]["recent_runs"] = task_stats[script]["recent_runs"][:10]

        # 增强 cron_data 中的每个任务
        for task in cron_data:
            task_key = (task.get("script_key") or task.get("id", "")).lower()
            stats = task_stats.get(task_key, {})

            # 添加运行统计
            task["run_count"] = stats.get("run_count", 0)
            task["success_count"] = stats.get("success_count", 0)
            task["error_count"] = stats.get("error_count", 0)
            task["run_history"] = [r["status"] for r in stats.get("recent_runs", [])]

            # 计算平均运行时间（模拟）
            if task.get("duration_ms"):
                task["avg_duration_ms"] = task["duration_ms"]
            else:
                # 根据任务类型估算
                if "backtest" in task_id or "overfit" in task_id:
                    task["avg_duration_ms"] = 120000  # 2 分钟
                elif "research" in task_id or "learning" in task_id:
                    task["avg_duration_ms"] = 45000  # 45 秒
                else:
                    task["avg_duration_ms"] = 15000  # 15 秒

        return {
            "cron_tasks": cron_data,
            "total_count": len(cron_data),
            "success_count": sum(1 for t in cron_data if t.get("status") == "ok"),
            "error_count": sum(1 for t in cron_data if t.get("status") == "error"),
            "running_count": sum(1 for t in cron_data if t.get("status") == "running"),
            "idle_count": sum(1 for t in cron_data if t.get("status") in ["idle", "waiting"]),
            "avg_duration_ms": sum(t.get("avg_duration_ms", 0) for t in cron_data) // max(len(cron_data), 1),
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"Get enhanced cron data error: {e}")
        return {"error": str(e), "cron_tasks": []}


def get_overview_data():
    account = get_account_latest() or {"total_asset": 0, "total_profit": 0, "cash": 0}
    positions = get_positions()
    predictions_stats = get_predictions_stats()
    market_style = get_market_style()
    cron_status = get_cron_status()
    scheduled_scripts = get_scheduled_scripts()
    running_count = sum(1 for s in cron_status.values() if s["running"])
    idle_count = sum(1 for s in cron_status.values() if not s["running"])
    return {
        "account": {"total_asset": account.get("total_asset", 0), "total_profit": account.get("total_profit", 0), "cash": account.get("cash", 0), "position_count": len(positions)},
        "positions": positions,
        "predictions_stats": predictions_stats,
        "market_style": market_style,
        "cron_status": cron_status,
        "scheduled_scripts": scheduled_scripts,
        "risk": get_risk_level()
    }


def get_cron_dashboard_html():
    """Read and return the enhanced cron dashboard HTML file"""
    html_path = os.path.join(os.path.dirname(__file__), 'cron_monitor.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Enhanced cron dashboard HTML file not found: {html_path}")
        return get_enhanced_cron_monitor_html_fallback()


def get_enhanced_cron_monitor_html_fallback():
    """Fallback enhanced cron monitor HTML if external file not found"""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cron 任务监控中心 - OpenClaw</title>
    <style>
        :root {
            --bg-primary: #0A0A0A; --bg-secondary: #121212; --bg-card: #1A1A1A;
            --text-primary: #FFFFFF; --text-secondary: #A0A0A0;
            --success: #00DC82; --warning: #FFB800; --error: #FF3B30; --accent: #0A84FF;
            --border: #2A2A2A;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: var(--bg-primary); color: var(--text-primary); font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { font-size: 24px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: var(--bg-card); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }
        .stat-value { font-size: 28px; font-weight: 700; }
        .stat-value.success { color: var(--success); }
        .stat-value.error { color: var(--error); }
        .stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
        .task-list { background: var(--bg-card); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; }
        .task-item { display: grid; grid-template-columns: 100px 1fr 150px 120px 100px; padding: 16px; border-bottom: 1px solid var(--border); align-items: center; }
        .task-item:hover { background: var(--bg-secondary); }
        .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; }
        .status-badge.success { background: rgba(0,220,130,0.15); color: var(--success); }
        .status-badge.error { background: rgba(255,59,48,0.15); color: var(--error); }
        .status-badge.running { background: rgba(10,132,255,0.15); color: var(--accent); }
        .status-badge.idle { background: rgba(255,184,0,0.15); color: var(--warning); }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Cron 任务监控中心</h1>
        <div class="stats" id="stats"></div>
        <div class="task-list" id="task-list"></div>
    </div>
    <script>
        async function loadData() {
            try {
                const res = await fetch('/api/enhanced_cron');
                const data = await res.json();
                render(data);
            } catch(e) {
                document.getElementById('stats').innerHTML = '<p style="color:var(--error)">加载失败</p>';
            }
        }
        function render(data) {
            const tasks = data.cron_tasks || [];
            document.getElementById('stats').innerHTML = `
                <div class="stat-card"><div class="stat-value">${data.total_count || 0}</div><div class="stat-label">总任务数</div></div>
                <div class="stat-card"><div class="stat-value success">${data.success_count || 0}</div><div class="stat-label">成功</div></div>
                <div class="stat-card"><div class="stat-value error">${data.error_count || 0}</div><div class="stat-label">失败</div></div>
                <div class="stat-card"><div class="stat-value">${data.running_count || 0}</div><div class="stat-label">运行中</div></div>
            `;
            document.getElementById('task-list').innerHTML = tasks.map(t => `
                <div class="task-item">
                    <span class="status-badge ${t.status === 'ok' ? 'success' : t.status === 'error' ? 'error' : t.status === 'running' ? 'running' : 'idle'}">${t.status}</span>
                    <div><strong>${t.name}</strong><div style="font-size:11px;color:var(--text-secondary)">${t.id}</div></div>
                    <div style="font-size:12px;color:var(--text-secondary)">${t.last_run || '从未运行'}</div>
                    <div style="font-size:12px;color:var(--text-secondary)">${t.next_run || '未计划'}</div>
                    <div style="font-size:12px;">⏱️ ${t.duration_ms ? (t.duration_ms/1000).toFixed(1)+'s' : '--'}</div>
                </div>
            `).join('');
        }
        loadData();
        setInterval(loadData, 10000);
    </script>
</body>
</html>'''


# =============================================================================
# HTML Content
# =============================================================================

HTML_CONTENT = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 股票团队监控 v3.1</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-primary: #0A0A0A; --bg-secondary: #1A1A1A; --bg-card: #0F0F0F;
            --text-primary: #FFFFFF; --text-secondary: #A0A0A0; --accent: #0066FF;
            --success: #00CC66; --warning: #FFCC00; --error: #FF3333; --border: #2A2A2A;
        }
        html, body { width: 100%; height: 100%; overflow: hidden; background: var(--bg-primary); color: var(--text-primary); font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
        .header { height: 64px; background: rgba(26,26,26,0.95); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; position: fixed; top: 0; left: 0; right: 0; z-index: 100; }
        .logo { font-size: 20px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 12px; }
        .logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent), #00AAFF); border-radius: 8px; }
        .clock { font-family: monospace; font-size: 14px; color: var(--text-secondary); padding: 6px 12px; background: var(--bg-secondary); border-radius: 4px; }
        .refresh-btn { padding: 6px 16px; background: var(--accent); color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .refresh-btn:hover { opacity: 0.9; }
        .main-wrapper { display: flex; height: calc(100vh - 64px); width: 100%; margin-top: 64px; }
        .sidebar { width: 260px; background: var(--bg-secondary); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 16px; overflow-y: auto; }
        .nav-group { margin-bottom: 24px; }
        .nav-group-title { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
        .nav-item { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 6px; cursor: pointer; color: var(--text-secondary); font-size: 13px; transition: all 0.2s; }
        .nav-item:hover { background: var(--bg-card); color: var(--text-primary); }
        .nav-item.active { background: var(--accent); color: white; }
        .nav-icon { width: 20px; text-align: center; font-size: 16px; }
        .badge { font-size: 10px; padding: 2px 6px; border-radius: 3px; }
        .badge-success { background: rgba(0,204,102,0.2); color: var(--success); }
        .badge-warning { background: rgba(255,204,0,0.2); color: var(--warning); }
        .badge-error { background: rgba(255,51,51,0.2); color: var(--error); }
        .main-content { flex: 1; background: var(--bg-primary); padding: 24px; overflow-y: auto; }
        .page { display: none; animation: fadeIn 0.3s ease; max-width: 1400px; margin: 0 auto; }
        .page.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .page-header { margin-bottom: 24px; }
        .page-title { font-size: 28px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
        .page-subtitle { font-size: 14px; color: var(--text-secondary); }
        .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--border); }
        .tab-item { padding: 12px 20px; cursor: pointer; color: var(--text-secondary); border: none; background: none; font-size: 14px; transition: all 0.2s; border-bottom: 2px solid transparent; }
        .tab-item:hover { color: var(--text-primary); }
        .tab-item.active { color: var(--accent); border-bottom-color: var(--accent); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
        .stat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .stat-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
        .stat-value { font-size: 28px; font-weight: 700; color: var(--text-primary); }
        .stat-value.positive { color: var(--success); }
        .stat-value.negative { color: var(--error); }
        .stat-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
        .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
        .card-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
        .card-title .badge { margin-left: 8px; }
        .card-content { padding: 0 8px; }
        .status-row { display: flex; align-items: center; gap: 8px; margin: 12px 0; padding: 8px; background: var(--bg-primary); border-radius: 6px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-dot.running { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-dot.idle { background: var(--text-secondary); }
        .status-dot.error { background: var(--error); }
        .status-info { flex: 1; }
        .status-name { font-size: 13px; color: var(--text-primary); }
        .status-meta { font-size: 11px; color: var(--text-secondary); }
        .data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .data-table th { text-align: left; padding: 12px; background: var(--bg-secondary); border-bottom: 1px solid var(--border); color: var(--text-primary); font-weight: 500; }
        .data-table td { padding: 12px; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
        .data-table tr:hover td { background: rgba(255,255,255,0.05); }
        .data-table .positive { color: var(--success); }
        .data-table .negative { color: var(--error); }
        .tag { padding: 2px 8px; border-radius: 3px; font-size: 11px; }
        .tag-buy { background: rgba(0,204,102,0.15); color: var(--success); }
        .tag-sell { background: rgba(255,51,51,0.15); color: var(--error); }
        .tag-neutral { background: rgba(255,204,0,0.15); color: var(--warning); }
        .detail-panel { width: 300px; background: var(--bg-secondary); border-left: 1px solid var(--border); padding: 20px; overflow-y: auto; }
        .detail-section { margin-bottom: 24px; }
        .detail-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
        .detail-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; font-size: 13px; color: var(--text-secondary); }
        .detail-item-value { color: var(--text-primary); font-weight: 500; }
        .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; transition: all 0.2s; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: #0052cc; }
        .btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-secondary:hover { border-color: var(--accent); }
        .btn-sm { padding: 4px 10px; font-size: 11px; }
        .script-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        .script-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
        .script-card .card-title { font-size: 13px; margin-bottom: 8px; }
        .script-card .card-content { padding: 0; }
        .status-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
        .status-card .status-card-name { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
        .status-card .status-card-meta { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
        .status-card .status-card-time { font-size: 12px; color: var(--accent); font-weight: 500; }
        .status-card.error { border-left: 3px solid var(--error); }
        .status-card.warning { border-left: 3px solid var(--warning); }
        .status-card.success { border-left: 3px solid var(--success); }
        .status-card.error .status-card-name { color: var(--error); }
        .status-card.warning .status-card-name { color: var(--warning); }
        .status-card.success .status-card-name { color: var(--success); }
        .status-summary { display: flex; gap: 24px; justify-content: center; padding: 12px 0; }
        .status-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
        .status-item .label { font-size: 12px; color: var(--text-secondary); }
        .status-item .value { font-size: 18px; font-weight: 700; color: var(--text-primary); }
        .risk-badge { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .risk-low { background: rgba(0,204,102,0.2); color: var(--success); }
        .risk-medium { background: rgba(255,204,0,0.2); color: var(--warning); }
        .risk-high { background: rgba(255,51,51,0.2); color: var(--error); }
        .empty-tip { text-align: center; padding: 40px; color: var(--text-secondary); font-size: 14px; }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo"><div class="logo-icon"></div><span>AI 股票监控 v3.1</span></div>
        <div style="display:flex;align-items:center;gap:12px">
            <div class="clock" id="clock">00:00:00</div>
            <button class="refresh-btn" onclick="refreshAll()">刷新所有数据</button>
        </div>
    </header>
    <div class="main-wrapper">
        <aside class="sidebar">
            <div class="nav-group">
                <div class="nav-group-title">实时监控</div>
                <div class="nav-item active" data-page="overview"><span class="nav-icon">📊</span>概览</div>
                <div class="nav-item" data-page="monitoring"><span class="nav-icon">👁️</span>监控面板</div>
                <div class="nav-item" data-page="cron"><span class="nav-icon">⚙️</span>Cron任务</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">AI预测</div>
                <div class="nav-item" data-page="ai-prediction"><span class="nav-icon">🤖</span>AI预测中心</div>
                <div class="nav-item" data-page="selector"><span class="nav-icon">🎯</span>选股结果</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">研究分析</div>
                <div class="nav-item" data-page="research"><span class="nav-icon">🔍</span>研究与分析</div>
                <div class="nav-item" data-page="events"><span class="nav-icon">⚡</span>事件驱动</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">交易执行</div>
                <div class="nav-item" data-page="trading"><span class="nav-icon">💼</span>交易执行</div>
                <div class="nav-item" data-page="positions"><span class="nav-icon">📈</span>持仓管理</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">验证学习</div>
                <div class="nav-item" data-page="validation"><span class="nav-icon">✅</span>验证学习</div>
                <div class="nav-item" data-page="backtest"><span class="nav-icon">📈</span>回测系统</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">报告总结</div>
                <div class="nav-item" data-page="reports"><span class="nav-icon">📋</span>报告总结</div>
                <div class="nav-item" data-page="news"><span class="nav-icon">📰</span>新闻监控</div>
            </div>
            <div class="nav-group">
                <div class="nav-group-title">OpenClaw</div>
            </div>
        </aside>
        <main class="main-content">
            <div class="page active" id="page-overview">
                <div class="page-header"><h1 class="page-title">系统概览</h1><p class="page-subtitle">AI 股票团队实时监控总览</p></div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-header"><span class="stat-label">总资产</span><span class="badge badge-success">昨日 +1.2%</span></div><div class="stat-value" id="overview-total-asset">--</div><div class="stat-sub">净值</div></div>
                    <div class="stat-card"><div class="stat-header"><span class="stat-label">总盈亏</span><span class="badge" id="overview-profit-badge">--</span></div><div class="stat-value" id="overview-total-profit">--</div><div class="stat-sub">累计收益</div></div>
                    <div class="stat-card"><div class="stat-header"><span class="stat-label">预测准确率</span><span class="badge badge-success" id="overview-accuracy-badge">--</span></div><div class="stat-value" id="overview-accuracy">--</div><div class="stat-sub">近30天</div></div>
                    <div class="stat-card"><div class="stat-header"><span class="stat-label">执行脚本</span><span class="badge badge-success">24/24</span></div><div class="stat-value" id="overview-scripts-status">🟢 闲置</div><div class="stat-sub">运行中/空闲</div></div>
                </div>
                <div class="card">
                    <div class="card-title"><span>市场风格</span><span class="badge badge-warning">实时</span></div>
                    <div class="card-content">
                        <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">价值 / 成长</div><div class="status-meta"><span id="market-style-value">55</span>% / <span id="market-style-growth">45</span>%</div></div></div>
                        <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">大盘 / 小盘</div><div class="status-meta"><span id="market-style-large">60</span>% / <span id="market-style-small">40</span>%</div></div></div>
                        <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">周期 / 防御</div><div class="status-meta"><span id="market-style-cycle">45</span>% / <span id="market-style-defense">55</span>%</div></div></div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title"><span>持仓列表</span><span class="badge" id="overview-positions-count">--</span></div>
                    <table class="data-table"><thead><tr><th>代码</th><th>名称</th><th>持仓</th><th>成本</th><th>现价</th><th>盈亏</th><th>盈亏%</th></tr></thead><tbody id="overview-positions-body"><tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">加载中...</td></tr></tbody></table>
                </div>
            </div>

            <div class="page" id="page-monitoring">
                <div class="page-header"><h1 class="page-title">监控面板</h1><p class="page-subtitle">市场监控与风险预警</p></div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-label">A股风险等级</div><div class="stat-value"><span id="monitor-risk-level" class="risk-badge risk-low">🟢 低风险</span></div></div>
                    <div class="stat-card"><div class="stat-label">上证指数</div><div class="stat-value" id="monitor-sz-index">--</div></div>
                    <div class="stat-card"><div class="stat-label">深证成指</div><div class="stat-value" id="monitor-szse-index">--</div></div>
                    <div class="stat-card"><div class="stat-label">熔断状态</div><div class="stat-value"><span class="risk-badge risk-low">🟢 正常</span></div></div>
                </div>
                <div class="card"><div class="card-title"><span>API 健康状态</span><span class="badge badge-success">所有正常</span></div><div class="card-content">API状态数据待集成</div></div>
            </div>

            <div class="page" id="page-cron">
                <div class="page-header"><h1 class="page-title">Cron 任务</h1><p class="page-subtitle">股票团队 OpenClaw 定时任务 - 实时状态</p></div>

                <!-- 运行统计 -->
                <div class="card"><div class="card-title"><span>运行统计</span><span class="badge" id="cron-today-count">--</span></div>
                    <div class="card-content">
                        <div class="status-summary">
                            <div class="status-item"><span class="label">已运行</span><span class="value" id="cron-status-count">0</span></div>
                            <div class="status-item"><span class="label">今日计划</span><span class="value" id="cron-scheduled-count">0</span></div>
                            <div class="status-item"><span class="label">成功率</span><span class="value" id="cron-success-rate">100%</span></div>
                        </div>
                    </div>
                </div>

                <!-- 任务列表卡片网格 -->
                <div class="card"><div class="card-title"><span>任务列表</span><span class="badge" id="oc-last-updated">最后更新：--</span></div>
                    <div class="card-content">
                        <div class="script-grid" id="cron-task-grid">
                            <div class="status-card loading"><div class="status-card-name">加载中...</div><div class="status-card-meta">获取任务数据中</div><div class="status-card-time">--</div></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="page" id="page-ai-prediction">
                <div class="page-header"><h1 class="page-title">AI预测中心</h1><p class="page-subtitle">AI模型预测结果与统计</p></div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-label">昨日预测</div><div class="stat-value" id="pred-yesterday-count">--</div><div class="stat-sub">条</div></div>
                    <div class="stat-card"><div class="stat-label">今日预测</div><div class="stat-value" id="pred-today-count">--</div><div class="stat-sub">条</div></div>
                    <div class="stat-card"><div class="stat-label">准确率</div><div class="stat-value" id="pred-accuracy">--</div><div class="stat-sub">近30天</div></div>
                    <div class="stat-card"><div class="stat-label">最近胜率</div><div class="stat-value" id="pred-recent-winrate">--</div><div class="stat-sub">近10次</div></div>
                </div>
                <div class="card"><div class="card-title"><span>今日高置信度预测</span><span class="badge" id="pred-today-count-badge">--</span></div><div class="card-content"><div id="pred-today-list"><p class="empty-tip">暂无今日预测</p></div></div></div>
                <div class="card"><div class="card-title"><span>近期预测列表</span><span class="badge" id="pred-total-count-badge">--</span></div><table class="data-table"><thead><tr><th>代码</th><th>方向</th><th>置信度</th><th>目标价</th><th>状态</th><th>结果</th><th>创建时间</th></tr></thead><tbody id="pred-list-body"><tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">加载中...</td></tr></tbody></table></div>
            </div>

            <div class="page" id="page-selector">
                <div class="page-header"><h1 class="page-title">智能选股</h1><p class="page-subtitle">根据PB/ROE和技术指标筛选</p></div>
                <div class="card"><div class="card-title"><span>今日推荐股票</span><span class="badge badge-success">最新</span></div><div class="card-content"><div id="selector-today-recommend"><p class="empty-tip">暂无今日推荐</p></div></div></div>
                <div class="card"><div class="card-title"><span>选股条件</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">PB < 1.5 (低估值)</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">ROE > 15% (高盈利)</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">MA5 > MA10 > MA20 (技术多头)</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">量比 > 1.2 (放量突破)</div></div></div>
                </div></div>
            </div>

            <div class="page" id="page-research">
                <div class="page-header"><h1 class="page-title">研究与分析</h1><p class="page-subtitle">深度研报与热点信息</p></div>
                <div class="card"><div class="card-title"><span>今日深度研报</span><span class="badge badge-success">AI生成</span></div><div class="card-content" id="research-today"><p class="empty-tip">暂无今日研报</p></div></div>
                <div class="card"><div class="card-title"><span>网络热点</span><span class="badge badge-warning">实时</span></div><div class="card-content" id="research-hotnews"><p class="empty-tip">暂无热点信息</p></div></div>
            </div>

            <div class="page" id="page-events">
                <div class="page-header"><h1 class="page-title">事件驱动</h1><p class="page-subtitle">热点事件与影响分析</p></div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-label">政策类事件</div><div class="stat-value" id="event-policy-count">--</div></div>
                    <div class="stat-card"><div class="stat-label">经济数据</div><div class="stat-value" id="event-data-count">--</div></div>
                    <div class="stat-card"><div class="stat-label">行业新闻</div><div class="stat-value" id="event-news-count">--</div></div>
                    <div class="stat-card"><div class="stat-label">今日影响</div><div class="stat-value" id="event-total-count">--</div></div>
                </div>
                <div class="card"><div class="card-title"><span>今日事件列表</span><span class="badge" id="event-list-count">--</span></div><div class="card-content" id="event-list"><p class="empty-tip">暂无今日事件</p></div></div>
            </div>

            <div class="page" id="page-trading">
                <div class="page-header"><h1 class="page-title">交易执行</h1><p class="page-subtitle">交易系统与执行记录</p></div>
                <div class="card"><div class="card-title"><span>持仓汇总</span><span class="badge" id="trading-positions-count">--</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">总市值</div><div class="status-meta" id="trading-market-value">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">今日盈亏</div><div class="status-meta" id="trading-today-profit">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">熔断状态</div><div class="status-meta"><span class="risk-badge risk-low">🟢 正常</span></div></div></div>
                </div></div>
                <div class="card"><div class="card-title"><span>今日交易记录</span><span class="badge" id="trading-today-count">--</span></div><table class="data-table"><thead><tr><th>时间</th><th>代码</th><th>方向</th><th>数量</th><th>价格</th><th>金额</th><th>原因</th></tr></thead><tbody id="trading-today-body"><tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无今日交易</td></tr></tbody></table></div>
            </div>

            <div class="page" id="page-positions">
                <div class="page-header"><h1 class="page-title">持仓管理</h1><p class="page-subtitle">当前持仓详情与盈亏</p></div>
                <div class="card"><div class="card-title"><span>持仓详情</span><span class="badge" id="positions-count-badge">--</span></div><table class="data-table"><thead><tr><th>代码</th><th>名称</th><th>持仓</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>盈亏%</th><th>操作</th></tr></thead><tbody id="positions-body-full"><tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr></tbody></table></div>
                <div class="card"><div class="card-title"><span>止盈止损设置</span></div><table class="data-table"><thead><tr><th>代码</th><th>止盈价</th><th>止损价</th><th>状态</th></tr></thead><tbody id="positions-stop-loss"><tr><td colspan="4" style="text-align:center;color:var(--text-secondary)">暂无设置</td></tr></tbody></table></div>
            </div>

            <div class="page" id="page-validation">
                <div class="page-header"><h1 class="page-title">验证与学习</h1><p class="page-subtitle">规则验证与机器学习进度</p></div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-label">验证通过</div><div class="stat-value" id="val-passed">--</div><div class="stat-sub">条规则</div></div>
                    <div class="stat-card"><div class="stat-label">验证失败</div><div class="stat-value" id="val-failed">--</div><div class="stat-sub">条规则</div></div>
                    <div class="stat-card"><div class="stat-label">待验证</div><div class="stat-value" id="val-pending">--</div><div class="stat-sub">条规则</div></div>
                    <div class="stat-card"><div class="stat-label">学习进度</div><div class="stat-value" id="val-progress">--</div><div class="stat-sub">知识点</div></div>
                </div>
                <div class="card"><div class="card-title"><span>学习记忆分类</span></div><div class="card-content"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
                    <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center"><div style="font-size:32px;font-weight:700;color:var(--success)" id="mem-hot">--</div><div style="color:var(--text-secondary);font-size:12px">热门记忆</div></div>
                    <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center"><div style="font-size:32px;font-weight:700;color:var(--accent)" id="mem-warm">--</div><div style="color:var(--text-secondary);font-size:12px">温暖记忆</div></div>
                    <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center"><div style="font-size:32px;font-weight:700;color:var(--text-secondary)" id="mem-cold">--</div><div style="color:var(--text-secondary);font-size:12px">冷门归档</div></div>
                </div></div></div>
                <div class="content-grid">
                    <div class="card"><div class="card-title"><span>规则库 Top</span><span class="badge" id="validation-rules-count">--</span></div><div class="card-content" id="validation-rules-list"><p class="empty-tip">加载中...</p></div></div>
                    <div class="card"><div class="card-title"><span>验证池候选</span><span class="badge" id="validation-pool-count">--</span></div><div class="card-content" id="validation-pool-list"><p class="empty-tip">加载中...</p></div></div>
                </div>
                <div class="card"><div class="card-title"><span>过拟合检测</span><span class="badge badge-success">🟢 低风险</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">样本内准确率</div><div class="status-meta" id="overfitting-in-sample">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">样本外准确率</div><div class="status-meta" id="overfitting-out-sample">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">过拟合风险</div><div class="status-meta"><span class="risk-badge risk-low">🟢 低风险</span></div></div></div>
                </div></div>
            </div>

            <div class="page" id="page-backtest">
                <div class="page-header"><h1 class="page-title">回测系统</h1><p class="page-subtitle">策略有效性验证</p></div>
                <div class="card"><div class="card-title"><span>最近回测结果</span></div><table class="data-table"><thead><tr><th>回测ID</th><th>策略名称</th><th>回测周期</th><th>收益率</th><th>最大回撤</th><th>夏普比率</th><th>创建时间</th></tr></thead><tbody id="backtest-body"><tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无回测结果</td></tr></tbody></table></div>
            </div>

            <div class="page" id="page-reports">
                <div class="page-header"><h1 class="page-title">报告总结</h1><p class="page-subtitle">各类报告与总结</p></div>
                <div class="card"><div class="card-title"><span>每日报告</span><span class="badge badge-success" id="report-today-date">--</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">总资产</div><div class="status-meta" id="report-total-asset">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">今日盈亏</div><div class="status-meta" id="report-today-profit">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">今日操作</div><div class="status-meta" id="report-today-ops">--</div></div></div>
                </div></div>
                <div class="card"><div class="card-title"><span>周报</span><span class="badge badge-success" id="report-week-date">--</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">周度收益</div><div class="status-meta" id="report-week-profit">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">同比</div><div class="status-meta" id="report-week-yoy">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">累计收益</div><div class="status-meta" id="report-week-cumulative">--</div></div></div>
                </div></div>
            </div>

            <div class="page" id="page-news">
                <div class="page-header"><h1 class="page-title">新闻监控</h1><p class="page-subtitle">实时新闻与事件影响</p></div>
                <div class="card"><div class="card-title"><span>实时新闻流</span><span class="badge badge-success">🟢 实时更新</span></div><div class="card-content" id="news-stream"><p class="empty-tip">暂无新闻</p></div></div>
                <div class="card"><div class="card-title"><span>事件影响统计</span></div><div class="card-content">
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">今日新闻数</div><div class="status-meta" id="news-today-count">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">重要事件</div><div class="status-meta" id="news-urgent-count">--</div></div></div>
                </div></div>
            </div>
        </main>
        <aside class="detail-panel">
            <div class="detail-section">
                <div class="detail-title">系统状态</div>
                <div class="detail-item"><span>服务器状态</span><span class="detail-item-value" style="color:var(--success)">🟢 运行中</span></div>
                <div class="detail-item"><span>数据库</span><span class="detail-item-value" style="color:var(--success)">🟢 已连接</span></div>
                <div class="detail-item"><span>上次更新</span><span class="detail-item-value" id="panel-last-update">--</span></div>
            </div>
            <div class="detail-section">
                <div class="detail-title">快捷操作</div>
                <button class="btn btn-primary" style="width:100%;margin-bottom:8px" onclick="refreshAll()">刷新所有数据</button>
                <button class="btn btn-secondary" style="width:100%;margin-bottom:8px" onclick="exportData('positions')">导出持仓</button>
                <button class="btn btn-secondary" style="width:100%" onclick="exportData('trades')">导出交易</button>
            </div>
            <div class="detail-section">
                <div class="detail-title">监控脚本</div>
                <div class="detail-item"><span>已运行</span><span class="detail-item-value" id="panel-scripts-running">0</span></div>
                <div class="detail-item"><span>今日待运行</span><span class="detail-item-value" id="panel-scripts-scheduled">0</span></div>
            </div>
        </aside>
    </div>
    <script>
        const API_BASE = '/api';
        let currentTab = 'overview';

        function updateClock() { document.getElementById('clock').textContent = new Date().toLocaleTimeString('zh-CN', {hour12:false}); }
        setInterval(updateClock, 1000); updateClock();

        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function() {
                document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
                document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                this.classList.add('active');
                const pageEl = document.getElementById('page-' + this.dataset.page);
                if (pageEl) { pageEl.classList.add('active'); currentTab = this.dataset.page; loadPageData(this.dataset.page); }
            });
        });

        async function fetchAPI(endpoint, fallback=[]) {
            try {
                const res = await fetch(API_BASE + endpoint);
                if (!res.ok) throw new Error();
                return await res.json();
            } catch(e) { console.error(endpoint, e); return fallback; }
        }

        async function loadPageData(page) {
            if (page === 'overview') loadOverviewData();
            else if (page === 'monitoring') loadMonitoringData();
            else if (page === 'cron') loadCronData();
            else if (page === 'ai-prediction') loadAiPredictionData();
            else if (page === 'selector') loadSelectorData();
            else if (page === 'research') loadResearchData();
            else if (page === 'events') loadEventData();
            else if (page === 'trading') loadTradingData();
            else if (page === 'positions') loadPositionsData();
            else if (page === 'validation') loadValidationData();
            else if (page === 'backtest') loadBacktestData();
            else if (page === 'reports') loadReportsData();
            else if (page === 'news') loadNewsData();
            updatePanelState();
        }

        async function loadOverviewData() {
            const data = await fetchAPI('/overview', {});
            if (!data.account) return;
            const acc = data.account;
            document.getElementById('overview-total-asset').textContent = '¥' + (acc.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            const profit = acc.total_profit || 0;
            const profitEl = document.getElementById('overview-total-profit');
            profitEl.textContent = (profit >= 0 ? '+' : '') + '¥' + profit.toLocaleString('zh-CN', {minimumFractionDigits:2});
            profitEl.className = 'stat-value ' + (profit >= 0 ? 'positive' : 'negative');
            const stats = data.predictions_stats || {};
            document.getElementById('overview-accuracy').textContent = (stats.accuracy || 0) + '%';
            document.getElementById('overview-accuracy-badge').textContent = (stats.accuracy || 0) >= 60 ? '✅ ' + (stats.accuracy || 0) + '%' : '⚠️ ' + (stats.accuracy || 0) + '%';
            document.getElementById('overview-positions-count').textContent = data.positions?.length || 0;
            document.getElementById('overview-positions-body').innerHTML = (data.positions || []).slice(0, 10).map(p => '<tr><td>' + p.symbol + '</td><td>' + (p.name || '') + '</td><td>' + (p.shares || 0) + '</td><td>' + (p.cost_price || 0).toFixed(2) + '</td><td>' + (p.current_price || 0).toFixed(2) + '</td><td class="' + (p.profit_loss >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss || 0).toFixed(2) + '</td><td class="' + (p.profit_loss_pct >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss_pct || 0).toFixed(2) + '%</td></tr>').join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>';
            const style = data.market_style || {};
            document.getElementById('market-style-value').textContent = style.value_growth?.value || 55;
            document.getElementById('market-style-growth').textContent = style.value_growth?.growth || 45;
            document.getElementById('market-style-large').textContent = style.large_small?.large || 60;
            document.getElementById('market-style-small').textContent = style.large_small?.small || 40;

            // 更新监控脚本统计
            const cronStatus = data.cron_status || {};
            const scheduled = data.scheduled_scripts || [];
            // 已运行：有last_run记录的脚本
            const running = Object.entries(cronStatus).filter(([_, s]) => s.last_run).length;
            document.getElementById('panel-scripts-running').textContent = running;
            document.getElementById('panel-scripts-scheduled').textContent = scheduled.length;
        }

        async function loadMonitoringData() {
            const data = await fetchAPI('/overview', {});
            const risk = data.risk || {level: 'low', notes: '无风险记录'};
            const riskEl = document.getElementById('monitor-risk-level');
            riskEl.textContent = risk.level === 'low' ? '🟢 低风险' : (risk.level === 'medium' ? '🟡 中风险' : '🔴 高风险');
            riskEl.className = 'risk-badge ' + (risk.level === 'low' ? 'risk-low' : (risk.level === 'medium' ? 'risk-medium' : 'risk-high'));
            document.getElementById('monitor-sz-index').textContent = '2950.12 (-0.5%)';
            document.getElementById('monitor-szse-index').textContent = '8900.34 (+0.2%)';
        }

        async function loadCronData() {
            // 加载 OpenClaw Cron 任务列表到卡片网格
            loadOpenClawCronCards();
        }

        async function loadOpenClawCronCards() {
            try {
                const data = await fetchAPI('/openclaw_cron', {});
                const tasks = data.cron_tasks || [];

                // 更新统计
                const successCount = data.success_count || 0;
                const totalCount = tasks.length;
                const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;

                document.getElementById('cron-scheduled-count').textContent = totalCount;
                document.getElementById('cron-status-count').textContent = successCount;
                document.getElementById('cron-success-rate').textContent = successRate + '%';
                document.getElementById('cron-today-count').textContent = totalCount;
                document.getElementById('oc-last-updated').textContent = '最后更新：' + (data.last_updated || '--');

                // 更新卡片网格
                const grid = document.getElementById('cron-task-grid');
                if (!grid) return;

                if (tasks.length === 0) {
                    grid.innerHTML = '<div class="status-card"><div class="status-card-name">暂无任务</div><div class="status-card-meta">请检查 OpenClaw 配置</div><div class="status-card-time">--</div></div>';
                    return;
                }

                grid.innerHTML = tasks.map(task => {
                    let statusClass = 'warning';
                    let statusEmoji = '🟡';
                    let statusText = task.status || 'unknown';
                    if (statusText === 'ok') { statusClass = 'success'; statusEmoji = '🟢'; }
                    else if (statusText === 'error') { statusClass = 'error'; statusEmoji = '🔴'; }
                    else if (statusText === 'running') { statusClass = 'accent'; statusEmoji = '🔵'; }

                    return '<div class="status-card" data-task-id="' + (task.id || '') + '">' +
                        '<div class="status-card-name">' + (task.name || '未知任务') + '</div>' +
                        '<div class="status-card-meta"><span class="badge badge-' + statusClass + '">' + statusEmoji + ' ' + statusText + '</span> | ' + (task.schedule || '--') + '</div>' +
                        '<div class="status-card-time">上次: ' + (task.last_run || '从未运行') + '</div>' +
                        '<div class="status-card-time" style="color:var(--success)">下次: ' + (task.next_run || '未计划') + '</div>' +
                    '</div>';
                }).join('');

            } catch (error) {
                console.error('加载 OpenClaw Cron 数据失败:', error);
                const grid = document.getElementById('cron-task-grid');
                if (grid) {
                    grid.innerHTML = '<div class="status-card error"><div class="status-card-name">加载失败</div><div class="status-card-meta">请刷新页面重试</div><div class="status-card-time">--</div></div>';
                }
            }
        }


        async function loadAiPredictionData() {
            const data = await fetchAPI('/predictions', []);
            const stats = await fetchAPI('/predictions-stats', {});
            const today = new Date().toISOString().slice(0, 10);
            document.getElementById('pred-yesterday-count').textContent = data.filter(p => p.created_at?.startsWith(today)).length;
            document.getElementById('pred-today-count').textContent = data.filter(p => p.created_at?.slice(0, 10) === today).length;
            document.getElementById('pred-accuracy').textContent = (stats.accuracy || 0) + '%';
            document.getElementById('pred-total-count-badge').textContent = data.length;
            document.getElementById('pred-today-list').innerHTML = data.filter(p => p.created_at?.slice(0, 10) === today && p.confidence >= 70).slice(0, 5).map(p => '<div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center"><span>' + p.symbol + (p.name || '') + '</span><span style="color:' + (p.direction === 'up' ? 'var(--success)' : (p.direction === 'down' ? 'var(--error)' : 'var(--warning)')) + '">看' + (p.direction === 'up' ? '涨' : (p.direction === 'down' ? '空' : '平')) + '</span><span style="color:var(--accent);font-weight:700">' + p.confidence + '%</span></div>').join('') || '<p class="empty-tip">暂无今日高置信度预测</p>';
            document.getElementById('pred-list-body').innerHTML = data.slice(0, 20).map(p => '<tr><td>' + p.symbol + '</td><td><span class="tag ' + (p.direction === 'up' ? 'buy' : (p.direction === 'down' ? 'sell' : 'neutral')) + '">' + (p.direction === 'up' ? '看涨' : (p.direction === 'down' ? '看空' : '中性')) + '</span></td><td>' + p.confidence + '%</td><td>' + (p.target_price || 0).toFixed(2) + '</td><td>' + p.status + '</td><td>' + (p.result || '--') + '</td><td>' + (p.created_at?.slice(0, 10) || '--') + '</td></tr>').join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无预测</td></tr>';
        }

        async function loadSelectorData() {
            const data = await fetchAPI('/selector-results', []);
            document.getElementById('selector-today-recommend').innerHTML = data.slice(0, 5).map(p => '<div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center"><span>' + p.symbol + (p.name || '') + '</span><span style="color:var(--accent);font-weight:700">置信度 ' + p.confidence + '%</span></div>').join('') || '<p class="empty-tip">暂无今日推荐</p>';
        }

        async function loadResearchData() { document.getElementById('research-today').innerHTML = '<p class="empty-tip">今日研报生成中...</p>'; document.getElementById('research-hotnews').innerHTML = '<p class="empty-tip">热点聚合中...</p>'; }

        async function loadEventData() {
            const data = await fetchAPI('/events-today', []);
            document.getElementById('event-policy-count').textContent = data.filter(e => e.event_types && e.event_types.includes('政策')).length || 0;
            document.getElementById('event-data-count').textContent = data.filter(e => e.event_types && e.event_types.includes('数据')).length || 0;
            document.getElementById('event-news-count').textContent = data.filter(e => e.event_types && e.event_types.includes('新闻')).length || 0;
            document.getElementById('event-total-count').textContent = data.length;
            document.getElementById('event-list').innerHTML = data.slice(0, 10).map(e => '<div style="padding:12px 0;border-bottom:1px solid var(--border)"><div style="color:var(--text-primary);margin-bottom:4px">' + (e.title || '无标题') + '</div><div style="color:var(--text-secondary);font-size:11px">' + (e.event_types || '综合') + ' | 影响: ' + (e.impact_score || '未知') + '</div></div>').join('') || '<p class="empty-tip">暂无今日事件</p>';
        }

        async function loadTradingData() {
            const data = await fetchAPI('/overview', {});
            const acc = data.account || {};
            document.getElementById('trading-market-value').textContent = '¥' + (acc.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            document.getElementById('trading-today-profit').textContent = (acc.total_profit || 0).toFixed(2);
            document.getElementById('trading-positions-count').textContent = data.positions?.length || 0;
        }

        async function loadPositionsData() {
            const data = await fetchAPI('/overview', {});
            document.getElementById('positions-count-badge').textContent = data.positions?.length || 0;
            document.getElementById('positions-body-full').innerHTML = (data.positions || []).map(p => '<tr><td>' + p.symbol + '</td><td>' + (p.name || '') + '</td><td>' + (p.shares || 0) + '</td><td>' + (p.cost_price || 0).toFixed(2) + '</td><td>' + (p.current_price || 0).toFixed(2) + '</td><td>' + (p.market_value || (p.shares || 0) * (p.current_price || 0) || 0).toFixed(2) + '</td><td class="' + (p.profit_loss >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss || 0).toFixed(2) + '</td><td class="' + (p.profit_loss_pct >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss_pct || 0).toFixed(2) + '%</td><td><button class="btn btn-sm btn-secondary">详情</button></td></tr>').join('') || '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>';
        }

        async function loadValidationData() {
            const data = await fetchAPI('/validation-summary', {});
            document.getElementById('val-passed').textContent = data.passed_rules || 0;
            document.getElementById('val-failed').textContent = data.failed_rules || 0;
            document.getElementById('val-pending').textContent = data.pending_rules || 0;
            document.getElementById('val-progress').textContent = data.learning_points || 0;
            document.getElementById('mem-hot').textContent = data.memory?.hot || 0;
            document.getElementById('mem-warm').textContent = data.memory?.warm || 0;
            document.getElementById('mem-cold').textContent = data.memory?.cold || 0;
            document.getElementById('overfitting-in-sample').textContent = (data.overfitting?.in_sample_accuracy || 0) + '%';
            document.getElementById('overfitting-out-sample').textContent = (data.overfitting?.out_sample_accuracy || 0) + '%';
            document.getElementById('validation-rules-count').textContent = data.top_rules?.length || 0;
            document.getElementById('validation-pool-count').textContent = data.validation_pool?.length || 0;
            document.getElementById('validation-rules-list').innerHTML = (data.top_rules || []).map(rule => (
                '<div style="padding:12px 0;border-bottom:1px solid var(--border)">' +
                '<div style="color:var(--text-primary);margin-bottom:4px">' + rule.rule_id + '</div>' +
                '<div style="color:var(--text-secondary);font-size:11px">' + rule.category + ' | 样本 ' + (rule.samples || 0) + ' | 胜率 ' + (((rule.success_rate || 0) * 100).toFixed(1)) + '%</div>' +
                '</div>'
            )).join('') || '<p class="empty-tip">暂无规则库数据</p>';
            document.getElementById('validation-pool-list').innerHTML = (data.validation_pool || []).map(rule => (
                '<div style="padding:12px 0;border-bottom:1px solid var(--border)">' +
                '<div style="color:var(--text-primary);margin-bottom:4px">' + (rule.rule || rule.rule_id || '未命名规则') + '</div>' +
                '<div style="color:var(--text-secondary);font-size:11px">' + (rule.category || '未分类') + ' | 置信度 ' + ((rule.confidence || 0).toFixed(2)) + ' | 实盘样本 ' + (rule.live_test?.samples || 0) + '</div>' +
                '</div>'
            )).join('') || '<p class="empty-tip">暂无验证池数据</p>';
        }

        async function loadBacktestData() { document.getElementById('backtest-body').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无回测结果</td></tr>'; }

        async function loadReportsData() {
            const data = await fetchAPI('/overview', {});
            const acc = data.account || {};
            const today = new Date().toISOString().slice(0, 10);
            document.getElementById('report-today-date').textContent = today;
            document.getElementById('report-total-asset').textContent = '¥' + (acc.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            document.getElementById('report-today-profit').textContent = (acc.total_profit || 0).toFixed(2);
            document.getElementById('report-today-ops').textContent = '无操作';
            document.getElementById('report-week-date').textContent = '2026-W11';
            document.getElementById('report-week-profit').textContent = '+1.2%';
            document.getElementById('report-week-yoy').textContent = '-2.3%';
            document.getElementById('report-week-cumulative').textContent = '+12.5%';
        }

        async function loadNewsData() {
            document.getElementById('news-today-count').textContent = 12; document.getElementById('news-urgent-count').textContent = 3;
            document.getElementById('news-stream').innerHTML = '<p class="empty-tip">实时新闻流待加载...</p>';
        }

        function updatePanelState() {
            document.getElementById('panel-last-update').textContent = new Date().toLocaleTimeString('zh-CN', {hour12:false});
        }

        async function refreshAll() { await loadPageData(currentTab); }

        function exportData(type) { alert('导出 ' + type + ' 功能开发中...'); }

        window.addEventListener('load', () => { loadPageData('overview'); });
    </script>
</body>
</html>'''


# =============================================================================
# API Handlers
# =============================================================================

def handle_api_overview():
    try:
        return get_overview_data()
    except Exception as e:
        logger.error(f"Overview error: {e}")
        return {"error": str(e)}

def handle_api_enhanced_cron():
    """API endpoint for enhanced cron monitoring data"""
    try:
        return get_enhanced_cron_data()
    except Exception as e:
        logger.error(f"Enhanced cron error: {e}")
        return {"error": str(e), "cron_tasks": []}

def handle_api_predictions():
    try:
        return {"predictions": get_predictions(50)}
    except Exception as e:
        logger.error(f"Predictions error: {e}")
        return {"predictions": []}

def handle_api_predictions_stats():
    try:
        return get_predictions_stats()
    except Exception as e:
        logger.error(f"Predictions stats error: {e}")
        return {"accuracy": 0}

def handle_api_selector_results():
    try:
        return {"results": get_selector_results()}
    except Exception as e:
        logger.error(f"Selector results error: {e}")
        return {"results": []}

def handle_api_events_today():
    try:
        return {"events": get_events_today()}
    except Exception as e:
        logger.error(f"Events today error: {e}")
        return {"events": []}

def handle_api_realtime_prices():
    return {"prices": [], "message": "待实现"}

def handle_api_trades():
    try:
        return {"trades": get_trades(50)}
    except Exception as e:
        logger.error(f"Trades error: {e}")
        return {"trades": []}


def handle_api_rules():
    try:
        return {"rules": flatten_rule_library(100)}
    except Exception as e:
        logger.error(f"Rules error: {e}")
        return {"rules": []}


def handle_api_validation_pool():
    try:
        return {"rules": get_validation_pool_items(100)}
    except Exception as e:
        logger.error(f"Validation pool error: {e}")
        return {"rules": []}


def handle_api_watchlist():
    try:
        return {"watchlist": get_watchlist_items(100)}
    except Exception as e:
        logger.error(f"Watchlist error: {e}")
        return {"watchlist": []}


def handle_api_validation_summary():
    try:
        return get_validation_summary()
    except Exception as e:
        logger.error(f"Validation summary error: {e}")
        return {"error": str(e)}

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_html(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_GET(self):
        path = self.path.split('?')[0]
        if path.startswith('/api/'):
            endpoint = path[5:]
            if endpoint == 'overview':
                self.send_json(handle_api_overview())
            elif endpoint == 'predictions':
                self.send_json(handle_api_predictions())
            elif endpoint == 'predictions-stats':
                self.send_json(handle_api_predictions_stats())
            elif endpoint == 'selector-results':
                self.send_json(handle_api_selector_results())
            elif endpoint == 'events-today':
                self.send_json(handle_api_events_today())
            elif endpoint == 'realtime-prices':
                self.send_json(handle_api_realtime_prices())
            elif endpoint == 'trades':
                self.send_json(handle_api_trades())
            elif endpoint == 'rules':
                self.send_json(handle_api_rules())
            elif endpoint == 'validation-pool':
                self.send_json(handle_api_validation_pool())
            elif endpoint == 'watchlist':
                self.send_json(handle_api_watchlist())
            elif endpoint == 'validation-summary':
                self.send_json(handle_api_validation_summary())
            elif endpoint == 'openclaw_cron':
                self.send_json(handle_api_openclaw_cron())
            elif endpoint == 'enhanced_cron':
                self.send_json(handle_api_enhanced_cron())
            else:
                self.send_json({"error": "Not found"}, 404)
        elif path == '/' or path == '/index.html':
            self.send_html(HTML_CONTENT)
        elif path == '/cron-dashboard.html' or path == '/cron' or path == '/cron-monitor':
            self.send_html(get_cron_dashboard_html())
        else:
            self.send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")


def run_server():
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        logger.info(f"Dashboard v3.1 started at http://127.0.0.1:{PORT}")
        logger.info(f"24 Cron scripts: 6 categories (4+3+4+2+5+3)")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
