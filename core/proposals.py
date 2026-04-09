"""Shared proposal pipeline helpers for the stock-team workflow."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .storage import DB_PATH, get_db, get_portfolio_baseline_date

OPEN_PROPOSAL_STATUSES = ("pending", "quant_validated", "risk_checked", "approved")
TERMINAL_PROPOSAL_STATUSES = ("rejected", "executed", "cancelled")


def ensure_pipeline_tables(db_path=DB_PATH) -> None:
    """Create the proposal workflow tables when missing."""
    with get_db(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                direction TEXT NOT NULL,
                thesis TEXT,
                target_price REAL,
                stop_loss REAL,
                source_agent TEXT NOT NULL,
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                executed_at TIMESTAMP,
                metadata JSON
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quant_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                ma5 REAL,
                ma10 REAL,
                ma20 REAL,
                ma60 REAL,
                macd TEXT,
                kdj TEXT,
                rsi REAL,
                volume_ratio REAL,
                technical_score INTEGER,
                recommendation TEXT,
                analysis_result JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_assessment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                risk_level TEXT,
                suggested_position REAL,
                max_position REAL,
                var_95 REAL,
                volatility REAL,
                industry_concentration REAL,
                correlation_market REAL,
                risk_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _loads_metadata(blob: Any) -> Dict[str, Any]:
    if isinstance(blob, dict):
        return dict(blob)
    if not blob:
        return {}
    try:
        value = json.loads(blob)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _with_history(
    metadata: Dict[str, Any],
    *,
    agent: str,
    stage: str,
    note: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    history = list(metadata.get("history") or [])
    entry: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "stage": stage,
        "note": note,
    }
    if payload:
        entry["payload"] = payload
    history.append(entry)
    metadata["history"] = history[-30:]
    metadata["workflow"] = _deep_merge(
        metadata.get("workflow", {}),
        {
            "last_agent": agent,
            "last_stage": stage,
            "last_note": note,
            "last_updated_at": entry["timestamp"],
        },
    )
    return metadata


def _record_agent_log(agent: str, event_type: str, event_data: Dict[str, Any], *, db_path=DB_PATH) -> None:
    ensure_pipeline_tables(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_logs (agent, event_type, event_data)
            VALUES (?, ?, ?)
            """,
            (agent, event_type, json.dumps(event_data, ensure_ascii=False)),
        )
        conn.commit()


def _baseline_filter_sql(column: str = "created_at") -> tuple[str, tuple[Any, ...]]:
    baseline_date = get_portfolio_baseline_date()
    if baseline_date:
        return f" AND substr({column}, 1, 10) >= ?", (baseline_date,)
    return "", ()


def get_latest_open_proposal(symbol: str, *, direction: str = "buy", db_path=DB_PATH) -> Optional[Dict[str, Any]]:
    ensure_pipeline_tables(db_path)
    extra_sql, params = _baseline_filter_sql("created_at")
    with get_db(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT *
            FROM proposals
            WHERE symbol = ?
              AND direction = ?
              AND status IN ({",".join("?" for _ in OPEN_PROPOSAL_STATUSES)})
              {extra_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (symbol, direction, *OPEN_PROPOSAL_STATUSES, *params),
        ).fetchone()
    return dict(row) if row else None


def get_pipeline_candidates(
    statuses: Sequence[str],
    *,
    direction: str = "buy",
    db_path=DB_PATH,
) -> List[Dict[str, Any]]:
    ensure_pipeline_tables(db_path)
    placeholders = ",".join("?" for _ in statuses)
    extra_sql, params = _baseline_filter_sql("created_at")
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM proposals
            WHERE direction = ?
              AND status IN ({placeholders})
              {extra_sql}
            ORDER BY created_at ASC, id ASC
            """,
            (direction, *statuses, *params),
        ).fetchall()
    return [dict(row) for row in rows]


def create_or_update_research_proposal(analysis: Dict[str, Any], *, db_path=DB_PATH) -> Dict[str, Any]:
    """Create or refresh the Research handoff proposal for a stock."""
    ensure_pipeline_tables(db_path)
    symbol = str(analysis["code"])
    now = datetime.now().isoformat()
    research_metadata = {
        "research": {
            "score": int(analysis.get("score") or 0),
            "recommendation": analysis.get("recommendation"),
            "industry": analysis.get("industry"),
            "current_price": float(analysis.get("price") or 0.0),
            "target_price": float(analysis.get("target_price") or 0.0),
            "stop_loss": float(analysis.get("stop_loss") or 0.0),
            "reasons": list(analysis.get("reasons") or []),
            "fundamental_source": analysis.get("fundamental_source", "snapshot"),
            "report_date": analysis.get("date"),
        }
    }
    priority = "high" if int(analysis.get("score") or 0) >= 70 else "normal"
    thesis = "；".join(analysis.get("reasons") or []) or str(analysis.get("industry") or "")

    with get_db(db_path) as conn:
        existing = get_latest_open_proposal(symbol, db_path=db_path)
        if existing:
            metadata = _deep_merge(_loads_metadata(existing.get("metadata")), research_metadata)
            metadata = _with_history(
                metadata,
                agent="Research",
                stage="research_refresh",
                note="研究结论已刷新，等待量化验证",
                payload={"proposal_id": existing["id"], "score": analysis.get("score")},
            )
            conn.execute(
                """
                UPDATE proposals
                SET name = ?, thesis = ?, target_price = ?, stop_loss = ?, priority = ?, metadata = ?
                WHERE id = ?
                """,
                (
                    analysis.get("name"),
                    thesis,
                    float(analysis.get("target_price") or 0.0),
                    float(analysis.get("stop_loss") or 0.0),
                    priority,
                    json.dumps(metadata, ensure_ascii=False),
                    existing["id"],
                ),
            )
            proposal_id = existing["id"]
            status = existing.get("status") or "pending"
        else:
            metadata = _with_history(
                research_metadata,
                agent="Research",
                stage="research_created",
                note="研究提案已创建，等待量化验证",
                payload={"score": analysis.get("score")},
            )
            cursor = conn.execute(
                """
                INSERT INTO proposals (
                    symbol, name, direction, thesis, target_price, stop_loss,
                    source_agent, priority, status, created_at, metadata
                ) VALUES (?, ?, 'buy', ?, ?, ?, 'Research', ?, 'pending', ?, ?)
                """,
                (
                    symbol,
                    analysis.get("name"),
                    thesis,
                    float(analysis.get("target_price") or 0.0),
                    float(analysis.get("stop_loss") or 0.0),
                    priority,
                    now,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            proposal_id = int(cursor.lastrowid)
            status = "pending"
        conn.commit()

    payload = {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "name": analysis.get("name"),
        "status": status,
        "score": analysis.get("score"),
    }
    _record_agent_log("Research", "proposal_handoff", payload, db_path=db_path)
    return payload


def create_or_update_selection_proposal(stock: Dict[str, Any], *, db_path=DB_PATH) -> Dict[str, Any]:
    """Create or refresh a proposal sourced from the selector ranking."""
    ensure_pipeline_tables(db_path)
    symbol = str(stock["code"])
    now = datetime.now().isoformat()
    score = stock.get("score") or {}
    technical = stock.get("technical") or {}
    selection_metadata = {
        "selection": {
            "score": int(score.get("total") or 0),
            "details": score.get("details") or "",
            "industry": f"{stock.get('sector', '')} > {stock.get('sub_sector', '')}".strip(" >"),
            "current_price": float(stock.get("price") or 0.0),
            "target_price": float(stock.get("target_price") or 0.0),
            "stop_loss": float(stock.get("stop_loss") or 0.0),
            "reasons": list(stock.get("proposal_reasons") or []),
            "technical_score": technical.get("technical_score"),
            "technical_recommendation": technical.get("recommendation"),
            "updated_date": datetime.now().strftime("%Y-%m-%d"),
        }
    }
    priority = "high" if int(score.get("total") or 0) >= 60 else "normal"
    thesis = "；".join(stock.get("proposal_reasons") or []) or str(score.get("details") or "")

    with get_db(db_path) as conn:
        existing = get_latest_open_proposal(symbol, db_path=db_path)
        if existing:
            metadata = _deep_merge(_loads_metadata(existing.get("metadata")), selection_metadata)
            metadata = _with_history(
                metadata,
                agent="Selector",
                stage="selection_refresh",
                note="动态选股候选已刷新，等待量化验证",
                payload={"proposal_id": existing["id"], "score": score.get("total")},
            )
            conn.execute(
                """
                UPDATE proposals
                SET name = ?, thesis = ?, target_price = ?, stop_loss = ?, priority = ?, metadata = ?
                WHERE id = ?
                """,
                (
                    stock.get("name"),
                    thesis,
                    float(stock.get("target_price") or 0.0),
                    float(stock.get("stop_loss") or 0.0),
                    priority,
                    json.dumps(metadata, ensure_ascii=False),
                    existing["id"],
                ),
            )
            proposal_id = existing["id"]
            status = existing.get("status") or "pending"
        else:
            metadata = _with_history(
                selection_metadata,
                agent="Selector",
                stage="selection_created",
                note="动态选股候选已创建，等待量化验证",
                payload={"score": score.get("total")},
            )
            cursor = conn.execute(
                """
                INSERT INTO proposals (
                    symbol, name, direction, thesis, target_price, stop_loss,
                    source_agent, priority, status, created_at, metadata
                ) VALUES (?, ?, 'buy', ?, ?, ?, 'Selector', ?, 'pending', ?, ?)
                """,
                (
                    symbol,
                    stock.get("name"),
                    thesis,
                    float(stock.get("target_price") or 0.0),
                    float(stock.get("stop_loss") or 0.0),
                    priority,
                    now,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            proposal_id = int(cursor.lastrowid)
            status = "pending"
        conn.commit()

    payload = {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "name": stock.get("name"),
        "status": status,
        "score": int(score.get("total") or 0),
    }
    _record_agent_log("Selector", "proposal_handoff", payload, db_path=db_path)
    return payload


def record_quant_validation(
    symbol: str,
    prediction: Dict[str, Any],
    *,
    technicals: Optional[Dict[str, Any]] = None,
    db_path=DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Attach Quant validation to an open research proposal."""
    ensure_pipeline_tables(db_path)
    proposal = get_latest_open_proposal(symbol, db_path=db_path)
    if not proposal:
        return None

    technicals = technicals or {}
    recommendation = str(
        technicals.get("recommendation")
        or ("buy" if prediction.get("direction") == "up" and int(prediction.get("confidence") or 0) >= 65 else "hold")
    )
    analysis_payload = {
        "prediction_id": prediction.get("id"),
        "direction": prediction.get("direction"),
        "confidence": int(prediction.get("confidence") or 0),
        "target_price": float(prediction.get("target_price") or 0.0),
        "reasons": list(prediction.get("reasons") or []),
        "risks": list(prediction.get("risks") or []),
        "rules_used": list(prediction.get("rules_used") or []),
        "signals": prediction.get("signals") or {},
        "technicals": technicals,
    }

    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO quant_analysis (
                proposal_id, symbol, ma5, ma10, ma20, ma60, macd, kdj, rsi,
                volume_ratio, technical_score, recommendation, analysis_result, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["id"],
                symbol,
                technicals.get("ma5"),
                technicals.get("ma10"),
                technicals.get("ma20"),
                technicals.get("ma60"),
                technicals.get("macd"),
                technicals.get("kdj"),
                technicals.get("rsi"),
                technicals.get("volume_ratio"),
                technicals.get("technical_score"),
                recommendation,
                json.dumps(analysis_payload, ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        metadata = _deep_merge(
            _loads_metadata(proposal.get("metadata")),
            {"quant": analysis_payload},
        )
        metadata = _with_history(
            metadata,
            agent="Quant",
            stage="quant_validated",
            note="量化验证完成，等待风控评估",
            payload={"proposal_id": proposal["id"], "confidence": prediction.get("confidence")},
        )
        next_status = (
            proposal.get("status")
            if str(proposal.get("status") or "") in {"risk_checked", "approved", "executed"}
            else "quant_validated"
        )
        conn.execute(
            """
            UPDATE proposals
            SET status = ?, metadata = ?, target_price = COALESCE(?, target_price)
            WHERE id = ?
            """,
            (
                next_status,
                json.dumps(metadata, ensure_ascii=False),
                float(prediction.get("target_price") or 0.0) or None,
                proposal["id"],
            ),
        )
        conn.commit()

    payload = {
        "proposal_id": proposal["id"],
        "symbol": symbol,
        "status": next_status,
        "confidence": int(prediction.get("confidence") or 0),
        "direction": prediction.get("direction"),
    }
    _record_agent_log("Quant", "proposal_handoff", payload, db_path=db_path)
    return payload


def record_risk_review(
    proposal_id: int,
    symbol: str,
    *,
    risk_level: str,
    notes: str,
    passed: bool,
    suggested_position: float,
    max_position: float,
    var_95: float = 0.05,
    volatility: float = 0.15,
    industry_concentration: float = 0.30,
    correlation_market: float = 0.80,
    db_path=DB_PATH,
) -> Dict[str, Any]:
    """Persist Risk review and move the proposal into risk_checked state."""
    ensure_pipeline_tables(db_path)
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError(f"proposal {proposal_id} not found")
        proposal = dict(row)
        conn.execute(
            """
            INSERT INTO risk_assessment (
                proposal_id, symbol, risk_level, suggested_position, max_position,
                var_95, volatility, industry_concentration, correlation_market, risk_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                symbol,
                risk_level,
                suggested_position,
                max_position,
                var_95,
                volatility,
                industry_concentration,
                correlation_market,
                notes,
            ),
        )
        metadata = _deep_merge(
            _loads_metadata(proposal.get("metadata")),
            {
                "risk": {
                    "passed": passed,
                    "risk_level": risk_level,
                    "notes": notes,
                    "suggested_position": suggested_position,
                    "max_position": max_position,
                }
            },
        )
        metadata = _with_history(
            metadata,
            agent="Risk",
            stage="risk_checked",
            note="风控评估完成，等待 CIO 审批",
            payload={"proposal_id": proposal_id, "passed": passed, "risk_level": risk_level},
        )
        conn.execute(
            """
            UPDATE proposals
            SET status = 'risk_checked', metadata = ?
            WHERE id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), proposal_id),
        )
        conn.commit()

    payload = {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "status": "risk_checked",
        "passed": passed,
        "risk_level": risk_level,
    }
    _record_agent_log("Risk", "proposal_handoff", payload, db_path=db_path)
    return payload


def apply_cio_decision(
    proposal_id: int,
    *,
    approved: bool,
    reason: str,
    summary: Optional[Dict[str, Any]] = None,
    db_path=DB_PATH,
) -> Dict[str, Any]:
    """Approve or reject a proposal after risk review."""
    ensure_pipeline_tables(db_path)
    status = "approved" if approved else "rejected"
    now = datetime.now().isoformat()
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError(f"proposal {proposal_id} not found")
        proposal = dict(row)
        metadata = _deep_merge(
            _loads_metadata(proposal.get("metadata")),
            {
                "cio": {
                    "approved": approved,
                    "reason": reason,
                    "summary": summary or {},
                    "reviewed_at": now,
                }
            },
        )
        metadata = _with_history(
            metadata,
            agent="CIO",
            stage=status,
            note=reason,
            payload={"proposal_id": proposal_id, "approved": approved},
        )
        conn.execute(
            """
            UPDATE proposals
            SET status = ?, approved_at = ?, metadata = ?
            WHERE id = ?
            """,
            (status, now, json.dumps(metadata, ensure_ascii=False), proposal_id),
        )
        conn.commit()

    payload = {
        "proposal_id": proposal_id,
        "symbol": proposal.get("symbol"),
        "status": status,
        "reason": reason,
    }
    _record_agent_log("CIO", "proposal_decision", payload, db_path=db_path)
    return payload


def mark_proposal_executed(
    proposal_id: int,
    execution: Dict[str, Any],
    *,
    db_path=DB_PATH,
) -> Dict[str, Any]:
    """Mark a proposal as executed and backfill related trade rows when possible."""
    ensure_pipeline_tables(db_path)
    order_id = execution.get("order_id")
    executed_at = execution.get("created_at") or datetime.now().isoformat()
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError(f"proposal {proposal_id} not found")
        proposal = dict(row)
        metadata = _deep_merge(
            _loads_metadata(proposal.get("metadata")),
            {
                "trader": {
                    "order_id": order_id,
                    "fill_price": execution.get("fill_price"),
                    "filled_shares": execution.get("filled_shares"),
                    "status": execution.get("status"),
                    "executed_at": executed_at,
                }
            },
        )
        metadata = _with_history(
            metadata,
            agent="Trader",
            stage="executed",
            note="模拟交易已执行",
            payload={"proposal_id": proposal_id, "order_id": order_id},
        )
        conn.execute(
            """
            UPDATE proposals
            SET status = 'executed', executed_at = ?, metadata = ?
            WHERE id = ?
            """,
            (executed_at, json.dumps(metadata, ensure_ascii=False), proposal_id),
        )

        trade_columns = {
            row_info["name"]
            for row_info in conn.execute("PRAGMA table_info(trades)").fetchall()
        }
        if order_id and "proposal_id" in trade_columns and "execution_order_id" in trade_columns:
            conn.execute(
                """
                UPDATE trades
                SET proposal_id = ?
                WHERE execution_order_id = ?
                """,
                (proposal_id, order_id),
            )
        conn.commit()

    payload = {
        "proposal_id": proposal_id,
        "symbol": proposal.get("symbol"),
        "status": "executed",
        "order_id": order_id,
    }
    _record_agent_log("Trader", "proposal_executed", payload, db_path=db_path)
    return payload


def get_pipeline_snapshot(*, db_path=DB_PATH, limit: int = 8) -> Dict[str, Any]:
    """Return status counts and recent handoffs for dashboard/useful summaries."""
    ensure_pipeline_tables(db_path)
    extra_sql, params = _baseline_filter_sql("created_at")
    with get_db(db_path) as conn:
        counts_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'quant_validated' THEN 1 ELSE 0 END) AS quant_validated,
                SUM(CASE WHEN status = 'risk_checked' THEN 1 ELSE 0 END) AS risk_checked,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) AS executed,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM proposals
            WHERE 1 = 1 {extra_sql}
            """,
            params,
        ).fetchone()
        logs = conn.execute(
            """
            SELECT agent, event_type, event_data, created_at
            FROM agent_logs
            WHERE event_type IN ('proposal_handoff', 'proposal_decision', 'proposal_executed')
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    counts = dict(counts_row) if counts_row else {}
    recent_handoffs: List[Dict[str, Any]] = []
    for row in logs:
        payload = _loads_metadata(row["event_data"])
        recent_handoffs.append(
            {
                "agent": row["agent"],
                "event_type": row["event_type"],
                "symbol": payload.get("symbol"),
                "status": payload.get("status"),
                "reason": payload.get("reason"),
                "created_at": row["created_at"],
            }
        )
    return {
        "counts": {key: int(value or 0) for key, value in counts.items()},
        "recent_handoffs": recent_handoffs,
    }
