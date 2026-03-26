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
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import logging

from core.storage import (
    DB_PATH,
    LEARNING_DIR,
    get_simulated_order_metrics,
    load_json,
    load_recent_simulated_orders,
    load_rule_state,
    load_watchlist,
)
from core.runtime_guardrails import (
    evaluate_runtime_mode,
    get_guardrail_control_state,
    get_runtime_snapshot,
    get_self_healing_snapshot,
    load_guardrail_config,
    load_guardrail_state,
)

PORT = 8082

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CRITICAL_AUTOPILOT_TASKS = {
    "daily_web_search",
    "ai_predictor",
    "news_trigger",
    "midday_review",
    "selector",
    "auto_trader_v3",
    "daily_review_closed_loop",
    "rule_validator",
}

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
    rules, _, _, _ = load_rule_state({}, {}, {})
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
    _, pool, _, _ = load_rule_state({}, {}, {})
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
    rules, validation_pool, rejected_rules, _ = load_rule_state({}, {}, {})
    rule_items = []
    for category, category_rules in rules.items():
        for rule_id, rule in category_rules.items():
            entry = dict(rule)
            entry["rule_id"] = rule_id
            entry["category"] = category
            rule_items.append(entry)
    rule_items.sort(
        key=lambda item: (
            float(item.get("success_rate", 0.0) or 0.0),
            int(item.get("samples", 0) or 0),
            float(item.get("weight", 0.0) or 0.0),
        ),
        reverse=True,
    )
    validation_pool_items = []
    for rule_id, rule in validation_pool.items():
        entry = dict(rule)
        entry["rule_id"] = rule_id
        validation_pool_items.append(entry)
    validation_pool_items.sort(
        key=lambda item: (
            float(item.get("confidence", 0.0) or 0.0),
            float(item.get("live_test", {}).get("success_rate", 0.0) or 0.0),
            int(item.get("backtest", {}).get("samples", 0) or 0),
        ),
        reverse=True,
    )
    rejected_items = list(rejected_rules.values())
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
        ORDER BY p.created_at DESC, p.confidence DESC
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
        WHERE p.created_at >= date('now', '-7 days')
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
        ORDER BY
            CASE nl.urgency
                WHEN '紧急' THEN 4
                WHEN '高' THEN 3
                WHEN '中' THEN 2
                WHEN '低' THEN 1
                ELSE 0
            END DESC,
            COALESCE(nl.impact_score, 0) DESC,
            nl.news_time DESC
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
        style = {
            "value_growth": {"value": round(safe_value(value_ratio) * 100), "growth": round(safe_value(growth_ratio) * 100)},
            "large_small": {"large": round(safe_value(large_cap_ratio) * 100), "small": round(safe_value(small_cap_ratio) * 100)}
        }
    else:
        style = {"value_growth": {"value": 55, "growth": 45}, "large_small": {"large": 60, "small": 40}}

    # 当 market_cache 缺失时，使用观察池行业做一个轻量风格估算。
    cyclical_industries = {"铜", "铝", "锂", "锡", "黄金", "稀土", "有色", "油气", "钢铁", "煤炭"}
    watchlist = load_watchlist({})
    total_watchlist = max(len(watchlist), 1)
    cyclical_count = sum(
        1 for info in watchlist.values()
        if any(keyword in str(info.get("industry", "")) for keyword in cyclical_industries)
    )
    cycle_ratio = round(cyclical_count / total_watchlist * 100)
    style["cycle_defense"] = {"cycle": cycle_ratio, "defense": 100 - cycle_ratio}
    return style

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


def _read_latest_files(pattern: str, limit: int = 5) -> List[Path]:
    """Return most-recent files matching a glob pattern."""
    files = list(PROJECT_ROOT.glob(pattern))
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return files[:limit]


def _extract_markdown_metric(text: str, label: str) -> Optional[str]:
    """Extract a markdown table metric by label."""
    match = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([^\|]+)\|", text)
    if match:
        return match.group(1).strip()
    return None


def _strip_markdown_emphasis(value: Optional[str]) -> str:
    """Remove simple markdown emphasis markers from a metric value."""
    if not value:
        return "--"
    return re.sub(r"[*_`]+", "", str(value)).strip() or "--"


def _parse_json_array(value) -> List[str]:
    """Parse a JSON list string into a Python list."""
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
    except Exception:
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _urgency_rank(urgency: Optional[str]) -> int:
    return {"紧急": 4, "高": 3, "中": 2, "低": 1}.get(str(urgency or "").strip(), 0)


def _impact_strength_label(impact_score: float, urgency: Optional[str]) -> str:
    if _urgency_rank(urgency) >= 4 or impact_score >= 85:
        return "极强"
    if _urgency_rank(urgency) >= 3 or impact_score >= 70:
        return "强"
    if impact_score >= 50:
        return "中"
    return "弱"


def _is_low_quality_news_item(item: Dict[str, Any]) -> bool:
    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").strip()
    news_time = str(item.get("news_time") or "").strip()
    confidence = float(item.get("sentiment_confidence") or 0.0)
    event_types = _parse_json_array(item.get("event_types"))
    generic_title = title.startswith("公司")
    generic_types = len(event_types) >= 5
    return (not news_time and not source and confidence <= 0.4 and generic_title) or (
        generic_types and confidence <= 0.4 and not source
    )


def _derive_source_from_url(url: Optional[str]) -> str:
    if not url:
        return "联网搜索"
    try:
        domain = urlparse(url).netloc.lower()
        return domain.replace("www.", "") or "联网搜索"
    except Exception:
        return "联网搜索"


def _estimate_search_signal(title: str, content: str) -> Dict[str, Any]:
    text = f"{title} {content}"
    positive_keywords = {
        "利好": 4,
        "增长": 3,
        "活跃": 2,
        "机会": 2,
        "机遇": 2,
        "领涨": 3,
        "回升": 3,
        "企稳": 2,
        "推进": 2,
        "火爆": 3,
        "改革": 1,
    }
    negative_keywords = {
        "监管": 3,
        "下跌": 3,
        "回调": 2,
        "调查": 4,
        "处罚": 4,
        "减持": 3,
        "违约": 4,
        "风险": 2,
        "暴跌": 5,
    }

    score = 0
    for keyword, weight in positive_keywords.items():
        if keyword in text:
            score += weight
    for keyword, weight in negative_keywords.items():
        if keyword in text:
            score -= weight

    if score >= 2:
        sentiment = "positive"
    elif score <= -2:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    impact_score = min(85.0, 35.0 + abs(score) * 10.0)
    urgency = "高" if impact_score >= 70 else ("中" if impact_score >= 50 else "低")
    confidence = min(0.85, 0.45 + abs(score) * 0.08)
    return {
        "sentiment": sentiment,
        "impact_score": impact_score,
        "urgency": urgency,
        "sentiment_confidence": confidence,
    }


def _get_recent_search_news(limit: int = 10) -> List[Dict[str, Any]]:
    """Build a fallback news feed from recent daily_search outputs."""
    direction_map = {
        "positive": ("利多", "📈"),
        "negative": ("利空", "📉"),
        "neutral": ("中性", "➡️"),
    }
    recent_items: List[Dict[str, Any]] = []
    seen_titles = set()

    for path in _read_latest_files("data/daily_search/*.json", limit=2):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(f"Failed to parse daily search file {path}: {exc}")
            continue

        search_date = str(payload.get("date") or path.stem)
        sections = {
            "市场热点": payload.get("market_overview", {}),
            "持仓跟踪": payload.get("holdings", {}),
            "观察池": payload.get("watchlist", {}),
        }

        for section_name, section in sections.items():
            if not isinstance(section, dict):
                continue
            for topic, items in section.items():
                if not isinstance(items, list):
                    continue
                for item in items[:2]:
                    title = str(item.get("title") or "").strip()
                    if not title or title in seen_titles:
                        continue
                    signal = _estimate_search_signal(title, str(item.get("content") or ""))
                    direction_label, direction_icon = direction_map.get(signal["sentiment"], ("中性", "➡️"))
                    recent_items.append(
                        {
                            "title": title,
                            "sentiment": signal["sentiment"],
                            "direction_label": direction_label,
                            "direction_icon": direction_icon,
                            "urgency": signal["urgency"],
                            "impact_score": signal["impact_score"],
                            "strength_label": _impact_strength_label(signal["impact_score"], signal["urgency"]),
                            "news_time": search_date,
                            "display_time": search_date,
                            "source": _derive_source_from_url(item.get("url")),
                            "event_types": [section_name, topic],
                            "event_types_display": topic,
                            "sentiment_confidence": signal["sentiment_confidence"],
                        }
                    )
                    seen_titles.add(title)
                    if len(recent_items) >= limit:
                        return recent_items

    return recent_items


def get_research_snapshot() -> Dict[str, Any]:
    """Return latest research reports and search headlines."""
    reports = []
    for path in _read_latest_files("data/research_*.json", limit=5):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            reports.append(
                {
                    "file": path.name,
                    "code": data.get("code"),
                    "name": data.get("name"),
                    "industry": data.get("industry"),
                    "date": data.get("date"),
                    "score": data.get("score"),
                    "recommendation": data.get("recommendation"),
                    "target_price": data.get("target_price"),
                    "price": data.get("price"),
                    "reasons": data.get("reasons", []),
                }
            )
        except Exception as exc:
            logger.error(f"Failed to parse research report {path}: {exc}")

    hot_items = []
    summary_path = PROJECT_ROOT / "data" / "daily_search" / "laverify_summary.txt"
    if summary_path.exists():
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip()
            if cleaned.startswith("- "):
                hot_items.append(cleaned[2:])
            elif cleaned.startswith("• "):
                hot_items.append(cleaned[2:])
        hot_items = hot_items[:10]

    return {"reports": reports, "hot_topics": hot_items}


def get_api_health_snapshot() -> Dict[str, Any]:
    """Load API health data from the existing status file."""
    status = load_json(PROJECT_ROOT / "config" / "api_status.json", {})
    services = []
    for domain, checks in status.items():
        if not isinstance(checks, dict):
            continue
        for channel, detail in checks.items():
            if not isinstance(detail, dict):
                continue
            services.append(
                {
                    "domain": domain,
                    "channel": channel,
                    "healthy": bool(detail.get("healthy", False)),
                    "response_time_ms": detail.get("response_time_ms"),
                    "last_check": detail.get("last_check"),
                    "last_error": detail.get("last_error"),
                    "consecutive_failures": detail.get("consecutive_failures", 0),
                }
            )

    healthy_count = sum(1 for item in services if item["healthy"])
    return {
        "services": services,
        "healthy_count": healthy_count,
        "total_count": len(services),
    }


def get_monitoring_snapshot() -> Dict[str, Any]:
    """Aggregate risk, API health, and critical monitoring task states."""
    health = get_api_health_snapshot()
    cron_tasks = get_openclaw_cron_status()
    market_api = next(
        (item for item in health["services"] if item["domain"] == "market" and item["channel"] == "api"),
        None,
    )
    search_api = next(
        (item for item in health["services"] if item["domain"] == "search" and item["channel"] == "api"),
        None,
    )
    circuit_breaker = next(
        (task for task in cron_tasks if task.get("script_key") == "circuit_breaker"),
        None,
    )
    return {
        "risk": get_risk_level(),
        "market_api": market_api,
        "search_api": search_api,
        "circuit_breaker": circuit_breaker,
        "api_health": health,
        "autopilot": get_autopilot_snapshot(cron_tasks=cron_tasks),
    }


def _format_age(age_hours: Optional[float]) -> str:
    if age_hours is None:
        return "缺失"
    if age_hours < 24:
        return f"{age_hours:.1f}h"
    return f"{age_hours / 24:.1f}d"


def _freshness_item(label: str, age_hours: Optional[float], limit_hours: float, *, critical: bool = True) -> Dict[str, Any]:
    if age_hours is None:
        status = "error"
        summary = "缺失"
    elif age_hours > limit_hours:
        status = "error" if critical else "warning"
        summary = "已过期"
    elif age_hours > limit_hours * 0.7:
        status = "warning"
        summary = "接近过期"
    else:
        status = "success"
        summary = "新鲜"

    return {
        "label": label,
        "age_hours": age_hours,
        "age_display": _format_age(age_hours),
        "limit_hours": limit_hours,
        "status": status,
        "summary": summary,
    }


def _get_execution_mode_snapshot() -> Dict[str, Any]:
    broker_config = PROJECT_ROOT / "config" / "broker_config.json"
    broker_enabled = broker_config.exists() or str(os.environ.get("BROKER_ENABLED", "")).lower() in {"1", "true", "yes"}
    if broker_enabled:
        return {
            "mode": "live_ready",
            "label": "实盘接口已配置",
            "detail": "检测到 broker 配置，接入前仍建议保留人工复核。",
            "status": "warning",
        }
    return {
        "mode": "simulation",
        "label": "模拟托管",
        "detail": "未检测到实盘 broker 配置，交易执行仅记录到账本、报告和看板。",
        "status": "success",
    }


def _get_active_prediction_count() -> int:
    row = query_one("SELECT COUNT(*) AS count FROM predictions WHERE status = 'active'")
    return int((row or {}).get("count", 0) or 0)


def _recent_guardrail_events(limit: int = 8) -> List[Dict[str, Any]]:
    state = load_guardrail_state()
    events = list(state.get("events", []))
    events.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return events[:limit]


def get_autopilot_snapshot(cron_tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    cron_tasks = cron_tasks if cron_tasks is not None else get_openclaw_cron_status()
    config = load_guardrail_config()
    state = load_guardrail_state()
    control = get_guardrail_control_state(config=config, state=state, persist=False)
    runtime = get_runtime_snapshot()
    prediction_config = load_json(PROJECT_ROOT / "config" / "prediction_config.json", {})
    execution_mode = _get_execution_mode_snapshot()
    account = get_account_latest() or {}
    watchlist_count = len(load_watchlist({}))
    active_prediction_count = _get_active_prediction_count()
    available_cash = account.get("cash", account.get("available_cash", 0))

    checks = [
        ("selection", "动态选股", evaluate_runtime_mode("selection", universe_count=max(watchlist_count, 1))),
        ("research", "深度研究", evaluate_runtime_mode("research", universe_count=max(watchlist_count, 1))),
        (
            "prediction_generate",
            "预测生成",
            evaluate_runtime_mode("prediction_generate", universe_count=watchlist_count + len(get_positions())),
        ),
        (
            "trade_buy",
            "自动买入",
            evaluate_runtime_mode(
                "trade_buy",
                universe_count=watchlist_count,
                active_prediction_count=active_prediction_count,
                available_cash=available_cash,
            ),
        ),
        ("trade_sell", "自动卖出", evaluate_runtime_mode("trade_sell")),
    ]

    freshness = [
        _freshness_item("daily_search", runtime.get("daily_search_age_hours"), config["freshness"]["daily_search_hours"]),
        _freshness_item("predictions", runtime.get("predictions_age_hours"), config["freshness"]["predictions_hours"]),
        _freshness_item(
            "fundamental_snapshot",
            runtime.get("fundamental_snapshot_age_hours"),
            config["freshness"]["fundamental_snapshot_hours"],
            critical=False,
        ),
        _freshness_item("stock_pool", runtime.get("stock_pool_age_hours"), config["freshness"]["stock_pool_hours"], critical=False),
    ]

    critical_errors = [
        task for task in cron_tasks
        if task.get("script_key") in CRITICAL_AUTOPILOT_TASKS and task.get("status") == "error"
    ]
    critical_warnings = [
        task for task in cron_tasks
        if task.get("script_key") in CRITICAL_AUTOPILOT_TASKS and task.get("status") == "warning"
    ]

    blocking_items: List[str] = []
    warning_items: List[str] = []
    mode_checks: List[Dict[str, Any]] = []
    for mode, label, result in checks:
        mode_checks.append(
            {
                "mode": mode,
                "label": label,
                "ok": result.ok,
                "warnings": result.warnings,
                "reasons": result.reasons,
                "status": "error" if result.reasons else ("warning" if result.warnings else "success"),
            }
        )
        blocking_items.extend(f"{label}: {reason}" for reason in result.reasons)
        warning_items.extend(f"{label}: {warning}" for warning in result.warnings)

    blocking_items.extend(f"Cron异常: {task.get('name', task.get('script_key', '未知任务'))}" for task in critical_errors)
    warning_items.extend(f"Cron告警: {task.get('name', task.get('script_key', '未知任务'))}" for task in critical_warnings)

    recent_events = _recent_guardrail_events()
    recent_error_count = sum(1 for item in recent_events if item.get("level") == "error")
    recent_warning_count = sum(1 for item in recent_events if item.get("level") == "warning")
    self_healing = get_self_healing_snapshot(config=config, state=state)

    learning_state = state.get("midday_learning", {})
    adjustments = list(learning_state.get("adjustments", []))
    active_adjustments = [item for item in adjustments if item.get("status") == "active"]
    rolled_back = [item for item in adjustments if item.get("status") == "rolled_back"]
    latest_rollback = None
    if rolled_back:
        rolled_back.sort(key=lambda item: str(item.get("rolled_back_at") or item.get("applied_at") or ""), reverse=True)
        latest_rollback = rolled_back[0]

    freshness_errors = sum(1 for item in freshness if item["status"] == "error")
    freshness_warnings = sum(1 for item in freshness if item["status"] == "warning")

    if control.get("active"):
        readiness_status = "warning"
        readiness_label = "只读托管"
        readiness_detail = (
            "已开启只读模式，自动买入和预测生成将被主动收敛。"
            if control.get("source") == "manual"
            else f"自动保护已接管：{control.get('reason') or '关键任务连续异常'}"
        )
    elif blocking_items or freshness_errors > 0 or recent_error_count > 0:
        readiness_status = "error"
        readiness_label = "需人工介入"
        readiness_detail = "当前存在阻断项或关键输入过期，不建议完全放手自动运行。"
    elif warning_items or freshness_warnings > 0 or active_adjustments:
        readiness_status = "warning"
        readiness_label = "受控自动"
        readiness_detail = "主链可以继续自动运行，但建议关注 warnings、学习调参和输入新鲜度。"
    else:
        readiness_status = "success"
        readiness_label = "全自动模拟"
        readiness_detail = "当前更适合以模拟交易模式全托管运行。"

    return {
        "execution_mode": execution_mode,
        "readiness": {
            "status": readiness_status,
            "label": readiness_label,
            "detail": readiness_detail,
        },
        "force_read_only": bool(control.get("active")),
        "read_only_source": control.get("source"),
        "read_only_reason": control.get("reason"),
        "read_only_expires_at": control.get("expires_at"),
        "confidence_threshold": float(prediction_config.get("confidence_threshold", 0.8) or 0.8),
        "freshness": freshness,
        "mode_checks": mode_checks,
        "blocking_items": blocking_items[:8],
        "warning_items": warning_items[:8],
        "recent_events": recent_events,
        "event_counts": {
            "errors": recent_error_count,
            "warnings": recent_warning_count,
        },
        "active_adjustments": len(active_adjustments),
        "latest_rollback": latest_rollback,
        "simulation_ready": execution_mode["mode"] == "simulation" and readiness_status == "success",
        "self_healing": self_healing,
    }


def get_trading_snapshot() -> Dict[str, Any]:
    """Return current trading summary plus recent trades."""
    account = get_account_latest() or {}
    positions = get_positions()
    trades = get_trades(20)
    order_metrics = get_simulated_order_metrics()
    today = datetime.now().strftime("%Y-%m-%d")
    today_trades = [trade for trade in trades if str(trade.get("executed_at", "")).startswith(today)]
    today_orders = [
        order for order in order_metrics.get("recent_orders", [])
        if str(order.get("created_at", "")).startswith(today)
    ]
    proposals = query_sql(
        """
        SELECT id, symbol, name, direction, status, created_at
        FROM proposals
        ORDER BY created_at DESC
        LIMIT 5
        """
    )

    return {
        "account": account,
        "positions": positions,
        "today_trades": today_trades,
        "recent_trades": trades,
        "today_orders": today_orders,
        "recent_orders": load_recent_simulated_orders(20),
        "order_metrics": order_metrics,
        "proposals": proposals,
    }


def get_backtest_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Parse existing markdown backtest reports into table rows."""
    results = []
    patterns = ["outputs/backverify_*.md", "outputs/weekly_backtest_*.md"]
    files: List[Path] = []
    for pattern in patterns:
        files.extend(_read_latest_files(pattern, limit=limit))
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)

    for path in files[:limit]:
        try:
            text = path.read_text(encoding="utf-8")
            results.append(
                {
                    "id": path.stem,
                    "strategy_name": "回测策略",
                    "period": re.search(r"\*\*回测期间\*\*[:：]\s*([^\n]+)", text).group(1).strip() if re.search(r"\*\*回测期间\*\*[:：]\s*([^\n]+)", text) else "--",
                    "return_pct": _extract_markdown_metric(text, "总收益率") or "--",
                    "max_drawdown": _extract_markdown_metric(text, "最大回撤") or "--",
                    "sharpe_ratio": _extract_markdown_metric(text, "夏普比率") or "--",
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
            )
        except Exception as exc:
            logger.error(f"Failed to parse backtest report {path}: {exc}")

    return results


def get_reports_snapshot() -> Dict[str, Any]:
    """Return daily and weekly report summary from existing outputs."""
    account = get_account_latest() or {}
    trades = get_trades(10)
    latest_trade = trades[0] if trades else None

    latest_weekly_path = next(iter(_read_latest_files("data/weekly_reports/*.md", limit=1)), None)
    weekly = {
        "period": "--",
        "accuracy": "--",
        "score": "--",
        "summary": "暂无周报",
    }
    if latest_weekly_path:
        text = latest_weekly_path.read_text(encoding="utf-8")
        period_match = re.search(r"\*\*时间范围\*\*[:：]\s*([^\n]+)", text)
        accuracy = _extract_markdown_metric(text, "**准确率**") or _extract_markdown_metric(text, "准确率")
        score = _extract_markdown_metric(text, "**综合得分**") or _extract_markdown_metric(text, "综合得分")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        weekly = {
            "period": period_match.group(1).strip() if period_match else latest_weekly_path.stem,
            "accuracy": _strip_markdown_emphasis(accuracy),
            "score": _strip_markdown_emphasis(score),
            "summary": lines[-1][:120] if lines else latest_weekly_path.name,
        }

    latest_review_path = next(iter(_read_latest_files("data/reviews/*.md", limit=1)), None)
    review_excerpt = "暂无复盘"
    if latest_review_path:
        text = latest_review_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                review_excerpt = cleaned[:120]
                break

    return {
        "daily": {
            "date": account.get("date", "--"),
            "total_asset": account.get("total_asset", 0.0),
            "profit": account.get("daily_profit", account.get("total_profit", 0.0)),
            "operation": (
                f"{latest_trade.get('executed_at', '--')} {latest_trade.get('direction', '')} "
                f"{latest_trade.get('name', latest_trade.get('symbol', ''))}"
                if latest_trade
                else "近期无交易"
            ),
            "review_excerpt": review_excerpt,
        },
        "weekly": weekly,
    }


def get_news_snapshot(limit: int = 20) -> Dict[str, Any]:
    """Return the latest news stream and counters from the database."""
    today = datetime.now().strftime("%Y-%m-%d")
    raw_news = query_sql(
        """
        SELECT title, sentiment, urgency, news_time, source, impact_score, event_types, sentiment_confidence,
               COALESCE(news_time, labeled_at) AS display_time
        FROM news_labels
        ORDER BY
            CASE urgency
                WHEN '紧急' THEN 4
                WHEN '高' THEN 3
                WHEN '中' THEN 2
                WHEN '低' THEN 1
                ELSE 0
            END DESC,
            COALESCE(impact_score, 0) DESC,
            COALESCE(news_time, labeled_at) DESC,
            id DESC
        LIMIT ?
        """,
        (max(limit * 5, 50),),
    )

    direction_map = {
        "positive": ("利多", "📈"),
        "negative": ("利空", "📉"),
        "neutral": ("中性", "➡️"),
    }
    recent_news = []
    seen_titles = set()
    for item in raw_news:
        title = str(item.get("title") or "").strip()
        if not title or title in seen_titles or _is_low_quality_news_item(item):
            continue

        sentiment = str(item.get("sentiment") or "neutral")
        direction_label, direction_icon = direction_map.get(sentiment, ("中性", "➡️"))
        impact_score = float(item.get("impact_score") or 0.0)
        urgency = item.get("urgency") or "低"
        event_types = _parse_json_array(item.get("event_types"))
        recent_news.append(
            {
                "title": title,
                "sentiment": sentiment,
                "direction_label": direction_label,
                "direction_icon": direction_icon,
                "urgency": urgency,
                "impact_score": impact_score,
                "strength_label": _impact_strength_label(impact_score, urgency),
                "news_time": item.get("news_time"),
                "display_time": item.get("display_time") or "--",
                "source": item.get("source") or "未知来源",
                "event_types": event_types,
                "event_types_display": " / ".join(event_types[:2]) if event_types else "未分类",
                "sentiment_confidence": float(item.get("sentiment_confidence") or 0.0),
            }
        )
        seen_titles.add(title)
        if len(recent_news) >= limit:
            break

    fallback_news = _get_recent_search_news(limit)
    for item in fallback_news:
        title = item.get("title")
        if not title or title in seen_titles or len(recent_news) >= limit:
            continue
        recent_news.append(item)
        seen_titles.add(title)

    recent_news.sort(
        key=lambda item: (
            str(item.get("display_time") or item.get("news_time") or ""),
            _urgency_rank(item.get("urgency")),
            float(item.get("impact_score") or 0.0),
        ),
        reverse=True,
    )
    recent_news = recent_news[:limit]

    today_count = sum(1 for item in recent_news if str(item.get("display_time", "")).startswith(today))
    urgent_count = sum(
        1 for item in recent_news
        if item.get("urgency") in {"高", "紧急"} or float(item.get("impact_score") or 0.0) >= 70
    )
    return {
        "today_count": today_count,
        "urgent_count": urgent_count,
        "news": recent_news,
    }

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
        cron_data = get_openclaw_cron_status()
        for task in cron_data:
            has_run = bool(task.get("last_run_raw"))
            task["run_count"] = 1 if has_run else 0
            task["success_count"] = 1 if task.get("status") == "ok" and has_run else 0
            task["error_count"] = int(task.get("consecutive_errors", 0) or 0)
            if task.get("status") == "error" and task["error_count"] == 0 and has_run:
                task["error_count"] = 1
            task["run_history"] = [task.get("status")] if has_run else []
            task["avg_duration_ms"] = int(task.get("duration_ms") or 0)

        duration_samples = [task["avg_duration_ms"] for task in cron_data if task.get("avg_duration_ms")]

        return {
            "cron_tasks": cron_data,
            "total_count": len(cron_data),
            "success_count": sum(1 for t in cron_data if t.get("status") == "ok"),
            "error_count": sum(1 for t in cron_data if t.get("status") == "error"),
            "running_count": sum(1 for t in cron_data if t.get("status") == "running"),
            "idle_count": sum(1 for t in cron_data if t.get("status") in ["idle", "waiting"]),
            "avg_duration_ms": (sum(duration_samples) // len(duration_samples)) if duration_samples else 0,
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
        .content-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 16px; }
        .banner-card { border-left: 4px solid var(--accent); }
        .banner-card.success { border-left-color: var(--success); }
        .banner-card.warning { border-left-color: var(--warning); }
        .banner-card.error { border-left-color: var(--error); }
        .banner-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
        .banner-desc { color: var(--text-secondary); font-size: 13px; line-height: 1.5; }
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
                <div class="card banner-card" id="monitor-autopilot-banner">
                    <div class="card-title"><span>托管驾驶舱</span><span class="badge" id="monitor-readonly-badge">加载中</span></div>
                    <div class="card-content">
                        <div class="banner-title" id="monitor-autopilot-title">加载托管状态...</div>
                        <div class="banner-desc" id="monitor-autopilot-desc">系统将根据 guardrails、数据新鲜度和关键 cron 状态生成托管建议。</div>
                    </div>
                </div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-label">A股风险等级</div><div class="stat-value"><span id="monitor-risk-level" class="risk-badge risk-low">🟢 低风险</span></div></div>
                    <div class="stat-card"><div class="stat-label">市场数据 API</div><div class="stat-value" id="monitor-market-api">--</div></div>
                    <div class="stat-card"><div class="stat-label">搜索 API</div><div class="stat-value" id="monitor-search-api">--</div></div>
                    <div class="stat-card"><div class="stat-label">熔断状态</div><div class="stat-value"><span id="monitor-circuit-status" class="risk-badge risk-low">🟢 正常</span></div></div>
                    <div class="stat-card"><div class="stat-label">托管模式</div><div class="stat-value" id="monitor-execution-mode">--</div><div class="stat-sub">模拟 / 实盘</div></div>
                    <div class="stat-card"><div class="stat-label">自动运行评级</div><div class="stat-value" id="monitor-readiness">--</div><div class="stat-sub">当前托管等级</div></div>
                    <div class="stat-card"><div class="stat-label">Guardrail 事件</div><div class="stat-value" id="monitor-guardrail-events">--</div><div class="stat-sub">最近事件</div></div>
                    <div class="stat-card"><div class="stat-label">数据新鲜度</div><div class="stat-value" id="monitor-freshness-score">--</div><div class="stat-sub">关键输入状态</div></div>
                </div>
                <div class="card"><div class="card-title"><span>API 健康状态</span><span class="badge" id="monitor-api-badge">--</span></div><div class="card-content" id="monitor-api-health"><p class="empty-tip">API状态数据待加载</p></div></div>
                <div class="content-grid">
                    <div class="card"><div class="card-title"><span>运行护栏</span><span class="badge" id="monitor-guardrail-badge">--</span></div><div class="card-content" id="monitor-guardrails"><p class="empty-tip">Guardrails 数据待加载</p></div></div>
                    <div class="card"><div class="card-title"><span>数据新鲜度</span><span class="badge" id="monitor-freshness-badge">--</span></div><div class="card-content" id="monitor-freshness"><p class="empty-tip">Freshness 数据待加载</p></div></div>
                </div>
                <div class="content-grid">
                    <div class="card"><div class="card-title"><span>自动托管检查</span><span class="badge" id="monitor-autopilot-badge">--</span></div><div class="card-content" id="monitor-mode-checks"><p class="empty-tip">自动托管检查结果待加载</p></div></div>
                    <div class="card"><div class="card-title"><span>最近 Guardrail 事件</span><span class="badge" id="monitor-events-badge">--</span></div><div class="card-content" id="monitor-events"><p class="empty-tip">暂无 Guardrail 事件</p></div></div>
                </div>
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
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">模拟订单</div><div class="status-meta" id="trading-open-orders">--</div></div></div>
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
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">准确率</div><div class="status-meta" id="report-week-profit">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">综合得分</div><div class="status-meta" id="report-week-yoy">--</div></div></div>
                    <div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">摘要</div><div class="status-meta" id="report-week-cumulative">--</div></div></div>
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
            const profitBadgeEl = document.getElementById('overview-profit-badge');
            profitEl.textContent = (profit >= 0 ? '+' : '') + '¥' + profit.toLocaleString('zh-CN', {minimumFractionDigits:2});
            profitEl.className = 'stat-value ' + (profit >= 0 ? 'positive' : 'negative');
            profitBadgeEl.textContent = profit >= 0 ? '盈利中' : '回撤中';
            profitBadgeEl.className = 'badge ' + (profit >= 0 ? 'badge-success' : 'badge-error');
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
            document.getElementById('market-style-cycle').textContent = style.cycle_defense?.cycle || 45;
            document.getElementById('market-style-defense').textContent = style.cycle_defense?.defense || 55;

            // 更新监控脚本统计
            const cronStatus = data.cron_status || {};
            const scheduled = data.scheduled_scripts || [];
            // 已运行：有last_run记录的脚本
            const executed = Object.entries(cronStatus).filter(([_, s]) => s.last_run).length;
            const running = Object.entries(cronStatus).filter(([_, s]) => s.running).length;
            document.getElementById('panel-scripts-running').textContent = executed;
            document.getElementById('panel-scripts-scheduled').textContent = scheduled.length;
            document.getElementById('overview-scripts-status').textContent = running > 0 ? ('🟢 ' + running + ' / ' + scheduled.length) : ('🟡 0 / ' + scheduled.length);
        }

        async function loadMonitoringData() {
            const data = await fetchAPI('/monitoring-summary', {});
            const risk = data.risk || {level: 'low', notes: '无风险记录'};
            const autopilot = data.autopilot || {};
            const riskEl = document.getElementById('monitor-risk-level');
            riskEl.textContent = risk.level === 'low' ? '🟢 低风险' : (risk.level === 'medium' ? '🟡 中风险' : '🔴 高风险');
            riskEl.className = 'risk-badge ' + (risk.level === 'low' ? 'risk-low' : (risk.level === 'medium' ? 'risk-medium' : 'risk-high'));
            const marketApi = data.market_api || {};
            const searchApi = data.search_api || {};
            const circuitBreaker = data.circuit_breaker || {};
            document.getElementById('monitor-market-api').textContent = marketApi.healthy ? ('🟢 ' + Math.round(marketApi.response_time_ms || 0) + 'ms') : '🔴 异常';
            document.getElementById('monitor-search-api').textContent = searchApi.healthy ? ('🟢 ' + Math.round(searchApi.response_time_ms || 0) + 'ms') : '🔴 异常';
            const circuitEl = document.getElementById('monitor-circuit-status');
            const circuitOk = circuitBreaker.status === 'ok' || circuitBreaker.status === 'idle' || circuitBreaker.status === 'waiting';
            circuitEl.textContent = circuitOk ? '🟢 正常' : (circuitBreaker.status === 'running' ? '🔵 执行中' : '🔴 异常');
            circuitEl.className = 'risk-badge ' + (circuitOk ? 'risk-low' : (circuitBreaker.status === 'running' ? 'risk-medium' : 'risk-high'));
            const health = data.api_health || {};
            const services = Array.isArray(health.services) ? health.services : [];
            const badgeEl = document.getElementById('monitor-api-badge');
            badgeEl.textContent = (health.healthy_count || 0) + ' / ' + (health.total_count || services.length || 0) + ' 正常';
            badgeEl.className = 'badge ' + ((health.healthy_count || 0) === (health.total_count || services.length || 0) ? 'badge-success' : 'badge-warning');
            const contentEl = document.getElementById('monitor-api-health');
            contentEl.innerHTML = services.map(service => {
                const healthy = !!service.healthy;
                const statusClass = healthy ? 'running' : 'error';
                const statusText = healthy ? '正常' : '异常';
                const response = service.response_time_ms ? Math.round(service.response_time_ms) + 'ms' : '--';
                const meta = service.last_error ? ('最近错误: ' + service.last_error) : ('最近检查: ' + (service.last_check || '--'));
                return '<div class="status-row"><div class="status-dot ' + statusClass + '"></div><div class="status-info"><div class="status-name">' + service.domain + ' / ' + service.channel + ' <span class="badge ' + (healthy ? 'badge-success' : 'badge-error') + '">' + statusText + '</span></div><div class="status-meta">响应 ' + response + ' | 连续失败 ' + (service.consecutive_failures || 0) + ' | ' + meta + '</div></div></div>';
            }).join('') + '<div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">风险备注</div><div class="status-meta">' + (risk.notes || '无补充说明') + '</div></div></div>' || '<p class="empty-tip">暂无 API 健康数据</p>';

            const readiness = autopilot.readiness || {};
            const executionMode = autopilot.execution_mode || {};
            const eventCounts = autopilot.event_counts || {};
            const selfHealing = autopilot.self_healing || {};
            const freshness = Array.isArray(autopilot.freshness) ? autopilot.freshness : [];
            const freshnessHealthy = freshness.filter(item => item.status === 'success').length;
            const freshnessTotal = freshness.length || 0;
            document.getElementById('monitor-execution-mode').textContent = executionMode.mode === 'simulation' ? '模拟' : '实盘';
            document.getElementById('monitor-readiness').textContent = readiness.label || '--';
            document.getElementById('monitor-guardrail-events').textContent = (eventCounts.errors || 0) + ' / ' + (eventCounts.warnings || 0);
            document.getElementById('monitor-freshness-score').textContent = freshnessTotal ? (freshnessHealthy + '/' + freshnessTotal) : '--';

            const banner = document.getElementById('monitor-autopilot-banner');
            banner.className = 'card banner-card ' + ((readiness.status === 'success') ? 'success' : (readiness.status === 'error' ? 'error' : 'warning'));
            document.getElementById('monitor-autopilot-title').textContent = (executionMode.label || '托管状态未知') + ' · ' + (readiness.label || '待评估');
            document.getElementById('monitor-autopilot-desc').textContent = readiness.detail || executionMode.detail || '暂无托管建议';
            const readonlyBadge = document.getElementById('monitor-readonly-badge');
            readonlyBadge.textContent = autopilot.force_read_only ? ((autopilot.read_only_source === 'automatic') ? '自动只读' : '手动只读') : '自动模式';
            readonlyBadge.className = 'badge ' + (autopilot.force_read_only ? 'badge-warning' : 'badge-success');

            const guardrailBadge = document.getElementById('monitor-guardrail-badge');
            guardrailBadge.textContent = autopilot.force_read_only ? '只读中' : ((autopilot.active_adjustments || 0) > 0 ? '调参中' : '已启用');
            guardrailBadge.className = 'badge ' + (autopilot.force_read_only ? 'badge-warning' : 'badge-success');
            document.getElementById('monitor-guardrails').innerHTML = [
                '<div class="status-row"><div class="status-dot ' + (autopilot.force_read_only ? 'error' : 'running') + '"></div><div class="status-info"><div class="status-name">执行模式</div><div class="status-meta">' + (executionMode.detail || '--') + (autopilot.read_only_reason ? (' | 只读原因: ' + autopilot.read_only_reason) : '') + '</div></div></div>',
                '<div class="status-row"><div class="status-dot idle"></div><div class="status-info"><div class="status-name">预测阈值</div><div class="status-meta">confidence_threshold = ' + ((autopilot.confidence_threshold || 0).toFixed ? autopilot.confidence_threshold.toFixed(2) : autopilot.confidence_threshold) + '</div></div></div>',
                '<div class="status-row"><div class="status-dot ' + ((autopilot.active_adjustments || 0) > 0 ? 'running' : 'idle') + '"></div><div class="status-info"><div class="status-name">学习调参</div><div class="status-meta">活跃调整 ' + (autopilot.active_adjustments || 0) + ' 次' + (autopilot.latest_rollback ? (' | 最近回滚: ' + (autopilot.latest_rollback.rollback_reason || autopilot.latest_rollback.reason || '已回滚')) : '') + '</div></div></div>',
                '<div class="status-row"><div class="status-dot ' + ((((selfHealing.recovery_count || 0) > 0) || ((selfHealing.fallback_count || 0) > 0)) ? 'idle' : 'running') + '"></div><div class="status-info"><div class="status-name">任务自愈</div><div class="status-meta">补跑 ' + (selfHealing.recovery_count || 0) + ' 次 | 备用源切换 ' + (selfHealing.fallback_count || 0) + ' 次</div></div></div>',
                '<div class="status-row"><div class="status-dot ' + ((eventCounts.errors || 0) > 0 ? 'error' : ((eventCounts.warnings || 0) > 0 ? 'idle' : 'running')) + '"></div><div class="status-info"><div class="status-name">最近事件</div><div class="status-meta">错误 ' + (eventCounts.errors || 0) + ' | 告警 ' + (eventCounts.warnings || 0) + '</div></div></div>'
            ].join('');

            const freshnessBadge = document.getElementById('monitor-freshness-badge');
            freshnessBadge.textContent = freshnessTotal ? (freshnessHealthy + '/' + freshnessTotal + ' 新鲜') : '无数据';
            freshnessBadge.className = 'badge ' + (freshness.some(item => item.status === 'error') ? 'badge-error' : (freshness.some(item => item.status === 'warning') ? 'badge-warning' : 'badge-success'));
            document.getElementById('monitor-freshness').innerHTML = freshness.map(item => {
                const dot = item.status === 'success' ? 'running' : (item.status === 'warning' ? 'idle' : 'error');
                const badge = item.status === 'success' ? 'badge-success' : (item.status === 'warning' ? 'badge-warning' : 'badge-error');
                return '<div class="status-row"><div class="status-dot ' + dot + '"></div><div class="status-info"><div class="status-name">' + item.label + ' <span class="badge ' + badge + '">' + item.summary + '</span></div><div class="status-meta">当前 ' + (item.age_display || '--') + ' | 阈值 ' + (item.limit_hours || '--') + 'h</div></div></div>';
            }).join('') || '<p class="empty-tip">暂无新鲜度数据</p>';

            const modeChecks = Array.isArray(autopilot.mode_checks) ? autopilot.mode_checks : [];
            const autopilotBadge = document.getElementById('monitor-autopilot-badge');
            autopilotBadge.textContent = modeChecks.length + ' 项';
            autopilotBadge.className = 'badge ' + (readiness.status === 'success' ? 'badge-success' : (readiness.status === 'error' ? 'badge-error' : 'badge-warning'));
            document.getElementById('monitor-mode-checks').innerHTML = modeChecks.map(item => {
                const dot = item.status === 'success' ? 'running' : (item.status === 'warning' ? 'idle' : 'error');
                const reasons = (item.reasons || []).concat(item.warnings || []);
                const meta = reasons.length ? reasons.join(' | ') : '当前未发现阻断项';
                return '<div class="status-row"><div class="status-dot ' + dot + '"></div><div class="status-info"><div class="status-name">' + item.label + '</div><div class="status-meta">' + meta + '</div></div></div>';
            }).join('') + ((selfHealing.recent_recoveries || []).slice(0, 2).map(item => {
                const dot = item.status === 'success' ? 'running' : 'idle';
                return '<div class="status-row"><div class="status-dot ' + dot + '"></div><div class="status-info"><div class="status-name">自动补跑 · ' + (item.task || '--') + '</div><div class="status-meta">' + (item.status === 'success' ? '补跑成功' : '补跑失败') + ' | ' + (item.reason || '--') + '</div></div></div>';
            }).join('')) || '<p class="empty-tip">暂无自动托管检查结果</p>';

            const recentEvents = Array.isArray(autopilot.recent_events) ? autopilot.recent_events : [];
            const eventsBadge = document.getElementById('monitor-events-badge');
            eventsBadge.textContent = recentEvents.length + ' 条';
            eventsBadge.className = 'badge ' + ((eventCounts.errors || 0) > 0 ? 'badge-error' : ((eventCounts.warnings || 0) > 0 ? 'badge-warning' : 'badge-success'));
            document.getElementById('monitor-events').innerHTML = recentEvents.map(item => {
                const level = item.level || 'info';
                const dot = level === 'error' ? 'error' : (level === 'warning' ? 'idle' : 'running');
                return '<div class="status-row"><div class="status-dot ' + dot + '"></div><div class="status-info"><div class="status-name">' + (item.task || 'system') + ' · ' + level + '</div><div class="status-meta">' + (item.time || '--') + ' | ' + (item.message || '--') + '</div></div></div>';
            }).join('') || '<p class="empty-tip">暂无近期 Guardrail 事件</p>';
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
                    let statusClass = task.status_color || 'warning';
                    let statusEmoji = '🟡';
                    const statusText = task.status_label || task.status || 'unknown';
                    if (statusClass === 'success') { statusEmoji = '🟢'; }
                    else if (statusClass === 'error') { statusEmoji = '🔴'; }
                    else if (statusClass === 'accent') { statusEmoji = '🔵'; }
                    const detail = task.status_detail ? (' | ' + task.status_detail) : '';

                    return '<div class="status-card" data-task-id="' + (task.id || '') + '">' +
                        '<div class="status-card-name">' + (task.name || '未知任务') + '</div>' +
                        '<div class="status-card-meta"><span class="badge badge-' + statusClass + '">' + statusEmoji + ' ' + statusText + '</span> | ' + (task.schedule || '--') + detail + '</div>' +
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
            const payload = await fetchAPI('/predictions', {});
            const data = Array.isArray(payload.predictions) ? payload.predictions : [];
            const stats = await fetchAPI('/predictions-stats', {});
            const today = new Date().toISOString().slice(0, 10);
            const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
            const settled = data.filter(p => ['correct', 'partial', 'wrong'].includes((p.result_status || p.result?.status || p.result || '').toString()));
            const recentSettled = settled.slice(0, 10);
            const recentCorrect = recentSettled.filter(p => (p.result_status || p.result?.status || p.result) === 'correct').length;
            const recentWinrate = recentSettled.length ? Math.round((recentCorrect / recentSettled.length) * 100) : 0;
            document.getElementById('pred-yesterday-count').textContent = data.filter(p => p.created_at?.slice(0, 10) === yesterday).length;
            document.getElementById('pred-today-count').textContent = data.filter(p => p.created_at?.slice(0, 10) === today).length;
            document.getElementById('pred-accuracy').textContent = (stats.accuracy || 0) + '%';
            document.getElementById('pred-recent-winrate').textContent = recentWinrate + '%';
            document.getElementById('pred-total-count-badge').textContent = data.length;
            const todayHighConfidence = data.filter(p => p.created_at?.slice(0, 10) === today && p.confidence >= 70).slice(0, 5);
            document.getElementById('pred-today-count-badge').textContent = todayHighConfidence.length;
            document.getElementById('pred-today-list').innerHTML = todayHighConfidence.map(p => '<div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center"><span>' + p.symbol + ' ' + (p.name || '') + '</span><span style="color:' + (p.direction === 'up' ? 'var(--success)' : (p.direction === 'down' ? 'var(--error)' : 'var(--warning)')) + '">看' + (p.direction === 'up' ? '涨' : (p.direction === 'down' ? '空' : '平')) + '</span><span style="color:var(--accent);font-weight:700">' + p.confidence + '%</span></div>').join('') || '<p class="empty-tip">暂无今日高置信度预测</p>';
            document.getElementById('pred-list-body').innerHTML = data.slice(0, 20).map(p => {
                const result = p.result_status || p.result?.status || p.result || '--';
                return '<tr><td>' + p.symbol + '</td><td><span class="tag ' + (p.direction === 'up' ? 'tag-buy' : (p.direction === 'down' ? 'tag-sell' : 'tag-neutral')) + '">' + (p.direction === 'up' ? '看涨' : (p.direction === 'down' ? '看空' : '中性')) + '</span></td><td>' + p.confidence + '%</td><td>' + (p.target_price || 0).toFixed(2) + '</td><td>' + (p.status || '--') + '</td><td>' + result + '</td><td>' + (p.created_at?.slice(0, 10) || '--') + '</td></tr>';
            }).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无预测</td></tr>';
        }

        async function loadSelectorData() {
            const payload = await fetchAPI('/selector-results', {});
            const data = Array.isArray(payload.results) ? payload.results : [];
            document.getElementById('selector-today-recommend').innerHTML = data.slice(0, 5).map(p => '<div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center"><span>' + p.symbol + ' ' + (p.name || '') + '</span><span style="color:var(--accent);font-weight:700">置信度 ' + p.confidence + '%</span></div>').join('') || '<p class="empty-tip">暂无近 7 日推荐</p>';
        }

        async function loadResearchData() {
            const data = await fetchAPI('/research-summary', {});
            const reports = Array.isArray(data.reports) ? data.reports : [];
            const hotTopics = Array.isArray(data.hot_topics) ? data.hot_topics : [];
            document.getElementById('research-today').innerHTML = reports.map(report => {
                const targetPrice = typeof report.target_price === 'number' ? report.target_price.toFixed(2) : (report.target_price || '--');
                return '<div style="padding:12px 0;border-bottom:1px solid var(--border)"><div style="color:var(--text-primary);margin-bottom:4px">' + (report.code || '--') + ' ' + (report.name || '未命名') + '</div><div style="color:var(--text-secondary);font-size:11px">' + (report.industry || '未分类') + ' | 评分 ' + (report.score || 0) + ' | 目标价 ¥' + targetPrice + '</div><div style="color:var(--text-secondary);font-size:11px;margin-top:4px">' + ((report.reasons || []).join(' / ') || (report.recommendation || '--')) + '</div></div>';
            }).join('') || '<p class="empty-tip">暂无近期开出的深度研报</p>';
            document.getElementById('research-hotnews').innerHTML = hotTopics.map(topic => '<div style="padding:12px 0;border-bottom:1px solid var(--border);color:var(--text-primary)">' + topic + '</div>').join('') || '<p class="empty-tip">暂无热点聚合结果</p>';
        }

        async function loadEventData() {
            const payload = await fetchAPI('/events-today', {});
            const data = Array.isArray(payload.events) ? payload.events : [];
            document.getElementById('event-policy-count').textContent = data.filter(e => String(e.event_types || '').includes('政策')).length || 0;
            document.getElementById('event-data-count').textContent = data.filter(e => String(e.event_types || '').includes('数据')).length || 0;
            document.getElementById('event-news-count').textContent = data.filter(e => String(e.event_types || '').includes('新闻')).length || 0;
            document.getElementById('event-total-count').textContent = data.length;
            document.getElementById('event-list-count').textContent = data.length;
            document.getElementById('event-list').innerHTML = data.slice(0, 10).map(e => '<div style="padding:12px 0;border-bottom:1px solid var(--border)"><div style="color:var(--text-primary);margin-bottom:4px">' + (e.title || '无标题') + '</div><div style="color:var(--text-secondary);font-size:11px">' + (e.event_types || '综合') + ' | 影响: ' + (e.impact_score || '未知') + ' | 关联股票 ' + (e['关联股票数'] || 0) + '</div></div>').join('') || '<p class="empty-tip">暂无今日事件</p>';
        }

        async function loadTradingData() {
            const data = await fetchAPI('/trading-summary', {});
            const acc = data.account || {};
            const todayTrades = Array.isArray(data.today_trades) ? data.today_trades : [];
            const orderMetrics = data.order_metrics || {};
            document.getElementById('trading-market-value').textContent = '¥' + (acc.market_value || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            document.getElementById('trading-today-profit').textContent = (acc.daily_profit || 0).toFixed(2);
            document.getElementById('trading-positions-count').textContent = data.positions?.length || 0;
            document.getElementById('trading-today-count').textContent = todayTrades.length;
            document.getElementById('trading-open-orders').textContent = '未完成 ' + (orderMetrics.open_order_count || 0) + ' 笔 | 部分成交 ' + (orderMetrics.partial_fill_count || 0) + ' 笔';
            document.getElementById('trading-today-body').innerHTML = todayTrades.map(trade => {
                const fillRatio = trade.fill_ratio ? (' | 成交率 ' + Math.round((trade.fill_ratio || 0) * 100) + '%') : '';
                const status = trade.execution_status ? (' | ' + trade.execution_status) : '';
                return '<tr><td>' + (trade.executed_at || '--') + '</td><td>' + (trade.symbol || '--') + '</td><td>' + (trade.direction || '--') + '</td><td>' + (trade.shares || 0) + '</td><td>' + (trade.price || 0).toFixed(2) + '</td><td>' + (trade.amount || 0).toFixed(2) + '</td><td>' + (trade.reason || '--') + status + fillRatio + '</td></tr>';
            }).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无今日交易</td></tr>';
        }

        async function loadPositionsData() {
            const data = await fetchAPI('/trading-summary', {});
            const positions = Array.isArray(data.positions) ? data.positions : [];
            document.getElementById('positions-count-badge').textContent = positions.length;
            document.getElementById('positions-body-full').innerHTML = positions.map(p => '<tr><td>' + p.symbol + '</td><td>' + (p.name || '') + '</td><td>' + (p.shares || 0) + '</td><td>' + (p.cost_price || 0).toFixed(2) + '</td><td>' + (p.current_price || 0).toFixed(2) + '</td><td>' + (p.market_value || (p.shares || 0) * (p.current_price || 0) || 0).toFixed(2) + '</td><td class="' + (p.profit_loss >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss || 0).toFixed(2) + '</td><td class="' + (p.profit_loss_pct >= 0 ? 'positive' : 'negative') + '">' + (p.profit_loss_pct || 0).toFixed(2) + '%</td><td><button class="btn btn-sm btn-secondary">详情</button></td></tr>').join('') || '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>';
            document.getElementById('positions-stop-loss').innerHTML = positions.map(p => {
                const takeProfit = typeof p.take_profit === 'number' ? p.take_profit.toFixed(2) : '--';
                const stopLoss = typeof p.stop_loss === 'number' ? p.stop_loss.toFixed(2) : '--';
                return '<tr><td>' + p.symbol + '</td><td>' + takeProfit + '</td><td>' + stopLoss + '</td><td>' + (p.status || 'holding') + '</td></tr>';
            }).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--text-secondary)">暂无持仓风控设置</td></tr>';
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

        async function loadBacktestData() {
            const data = await fetchAPI('/backtests', {});
            const rows = Array.isArray(data.results) ? data.results : [];
            document.getElementById('backtest-body').innerHTML = rows.map(row => '<tr><td>' + row.id + '</td><td>' + (row.strategy_name || '--') + '</td><td>' + (row.period || '--') + '</td><td>' + (row.return_pct || '--') + '</td><td>' + (row.max_drawdown || '--') + '</td><td>' + (row.sharpe_ratio || '--') + '</td><td>' + (row.created_at || '--') + '</td></tr>').join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无回测结果</td></tr>';
        }

        async function loadReportsData() {
            const data = await fetchAPI('/reports-summary', {});
            const daily = data.daily || {};
            const weekly = data.weekly || {};
            document.getElementById('report-today-date').textContent = daily.date || '--';
            document.getElementById('report-total-asset').textContent = '¥' + (daily.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            document.getElementById('report-today-profit').textContent = (daily.profit || 0).toFixed(2);
            document.getElementById('report-today-ops').textContent = daily.operation || '近期无交易';
            document.getElementById('report-week-date').textContent = weekly.period || '--';
            document.getElementById('report-week-profit').textContent = weekly.accuracy || '--';
            document.getElementById('report-week-yoy').textContent = weekly.score || '--';
            document.getElementById('report-week-cumulative').textContent = weekly.summary || '--';
        }

        async function loadNewsData() {
            const data = await fetchAPI('/news-summary', {});
            const news = Array.isArray(data.news) ? data.news : [];
            document.getElementById('news-today-count').textContent = data.today_count || 0;
            document.getElementById('news-urgent-count').textContent = data.urgent_count || 0;
            document.getElementById('news-stream').innerHTML = news.map(item => {
                const sentiment = item.sentiment || 'neutral';
                const directionColor = sentiment === 'positive' ? 'var(--success)' : (sentiment === 'negative' ? 'var(--error)' : 'var(--warning)');
                const confidence = Math.round((item.sentiment_confidence || 0) * 100);
                return '<div style="padding:12px 0;border-bottom:1px solid var(--border)">' +
                    '<div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px"><div style="color:var(--text-primary)">' + (item.title || '无标题') + '</div><div style="color:' + directionColor + ';white-space:nowrap">' + (item.direction_icon || '➡️') + ' ' + (item.direction_label || '中性') + '</div></div>' +
                    '<div style="color:var(--text-secondary);font-size:11px">' + (item.source || '未知来源') + ' | ' + (item.event_types_display || '未分类') + ' | 力度 ' + (item.strength_label || '--') + ' (' + (item.impact_score || '--') + ')</div>' +
                    '<div style="color:var(--text-secondary);font-size:11px;margin-top:4px">时间 ' + (item.display_time || item.news_time || '--') + ' | 置信度 ' + confidence + '% | 紧急度 ' + (item.urgency || '--') + '</div>' +
                '</div>';
            }).join('') || '<p class="empty-tip">暂无高质量新闻流数据</p>';
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


def handle_api_monitoring_summary():
    try:
        return get_monitoring_snapshot()
    except Exception as e:
        logger.error(f"Monitoring summary error: {e}")
        return {"error": str(e)}


def handle_api_research_summary():
    try:
        return get_research_snapshot()
    except Exception as e:
        logger.error(f"Research summary error: {e}")
        return {"error": str(e), "reports": [], "hot_topics": []}


def handle_api_trading_summary():
    try:
        return get_trading_snapshot()
    except Exception as e:
        logger.error(f"Trading summary error: {e}")
        return {"error": str(e), "account": {}, "positions": [], "today_trades": [], "recent_trades": [], "proposals": []}


def handle_api_backtests():
    try:
        return {"results": get_backtest_results(10)}
    except Exception as e:
        logger.error(f"Backtests error: {e}")
        return {"error": str(e), "results": []}


def handle_api_reports_summary():
    try:
        return get_reports_snapshot()
    except Exception as e:
        logger.error(f"Reports summary error: {e}")
        return {"error": str(e), "daily": {}, "weekly": {}}


def handle_api_news_summary():
    try:
        return get_news_snapshot(20)
    except Exception as e:
        logger.error(f"News summary error: {e}")
        return {"error": str(e), "today_count": 0, "urgent_count": 0, "news": []}

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
            elif endpoint == 'monitoring-summary':
                self.send_json(handle_api_monitoring_summary())
            elif endpoint == 'research-summary':
                self.send_json(handle_api_research_summary())
            elif endpoint == 'trading-summary':
                self.send_json(handle_api_trading_summary())
            elif endpoint == 'backtests':
                self.send_json(handle_api_backtests())
            elif endpoint == 'reports-summary':
                self.send_json(handle_api_reports_summary())
            elif endpoint == 'news-summary':
                self.send_json(handle_api_news_summary())
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
