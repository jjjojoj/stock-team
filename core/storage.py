"""Shared filesystem paths and sync helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .predictions import normalize_prediction_collection, prediction_result_status

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = PROJECT_ROOT / "database"
LEARNING_DIR = PROJECT_ROOT / "learning"
LOG_DIR = PROJECT_ROOT / "logs"
WEB_DIR = PROJECT_ROOT / "web"

DB_PATH = DATABASE_DIR / "stock_team.db"
PERFORMANCE_DB_PATH = DATABASE_DIR / "performance.db"

POSITIONS_FILE = CONFIG_DIR / "positions.json"
WATCHLIST_FILE = CONFIG_DIR / "watchlist.json"
PORTFOLIO_FILE = CONFIG_DIR / "portfolio.json"
FEISHU_CONFIG_FILE = CONFIG_DIR / "feishu_config.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"
TRADE_HISTORY_FILE = DATA_DIR / "trade_history.json"
ACCURACY_FILE = LEARNING_DIR / "accuracy_stats.json"
RULES_FILE = LEARNING_DIR / "prediction_rules.json"
VALIDATION_POOL_FILE = LEARNING_DIR / "rule_validation_pool.json"
REJECTED_RULES_FILE = LEARNING_DIR / "rejected_rules.json"
REVIEW_DIR = DATA_DIR / "reviews"


class ManagedConnection(sqlite3.Connection):
    """SQLite connection that closes itself when used as a context manager."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def load_json(path: Path, default: Any) -> Any:
    """Load json from disk or return the default value."""
    if Path(path).exists():
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return default


def save_json(path: Path, data: Any) -> None:
    """Persist json data with UTF-8 encoding."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def get_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with row access by name."""
    conn = sqlite3.connect(db_path, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    return conn


def _load_json_blob(blob: Optional[str], default: Any) -> Any:
    """Decode a JSON blob stored in SQLite."""
    if not blob:
        return default
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return default


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return the set of column names present in a table."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _parse_timestamp(value: Any) -> datetime:
    """Best-effort timestamp parsing for rule-state reconciliation."""
    if not value:
        return datetime.min
    text = str(value).strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def ensure_storage_tables(db_path: Path = DB_PATH) -> None:
    """Create/upgrade SQLite tables used as the project's source of truth."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                name TEXT,
                direction TEXT,
                current_price REAL,
                target_price REAL,
                confidence INTEGER,
                timeframe TEXT,
                reasons TEXT,
                risks TEXT,
                source_agent TEXT,
                status TEXT,
                result TEXT,
                actual_end_price REAL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                verified_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT,
                shares INTEGER,
                cost_price REAL,
                current_price REAL,
                market_value REAL,
                profit_loss REAL,
                profit_loss_pct REAL,
                position_pct REAL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT DEFAULT 'holding',
                bought_at TIMESTAMP,
                sold_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT,
                direction TEXT NOT NULL,
                shares INTEGER,
                price REAL,
                amount REAL,
                commission REAL,
                reason TEXT,
                proposal_id INTEGER,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_asset REAL,
                cash REAL,
                market_value REAL,
                total_profit REAL,
                total_profit_pct REAL,
                daily_profit REAL,
                daily_profit_pct REAL,
                position_count INTEGER,
                max_drawdown REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT,
                industry TEXT,
                reason TEXT,
                target_price REAL,
                alert_price_high REAL,
                alert_price_low REAL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                condition TEXT,
                prediction TEXT,
                weight REAL,
                confidence_boost REAL,
                samples INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0,
                source TEXT,
                status TEXT DEFAULT 'active',
                data_json TEXT NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(category, rule_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_validation_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL UNIQUE,
                category TEXT,
                rule_text TEXT,
                testable_form TEXT,
                source TEXT,
                source_book TEXT,
                status TEXT DEFAULT 'validating',
                confidence REAL DEFAULT 0,
                backtest_samples INTEGER DEFAULT 0,
                backtest_success_rate REAL DEFAULT 0,
                live_samples INTEGER DEFAULT 0,
                live_success_rate REAL DEFAULT 0,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rejected_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL UNIQUE,
                category TEXT,
                rule_text TEXT,
                testable_form TEXT,
                source TEXT,
                source_book TEXT,
                status TEXT DEFAULT 'rejected',
                confidence REAL DEFAULT 0,
                reject_reason TEXT,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                rejected_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_rules_category
            ON prediction_rules(category)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prediction_rules_status
            ON prediction_rules(status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rule_validation_pool_status
            ON rule_validation_pool(status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rule_validation_pool_category
            ON rule_validation_pool(category)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rejected_rules_category
            ON rejected_rules(category)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS simulated_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                name TEXT,
                direction TEXT NOT NULL,
                order_type TEXT DEFAULT 'market',
                requested_shares INTEGER NOT NULL,
                filled_shares INTEGER DEFAULT 0,
                remaining_shares INTEGER DEFAULT 0,
                requested_price REAL,
                avg_fill_price REAL,
                fill_ratio REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                cash_effect REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                slippage_cost REAL DEFAULT 0,
                slippage_bps REAL DEFAULT 0,
                reference_price REAL,
                price_source TEXT,
                market_cap REAL,
                reason TEXT,
                prediction_id TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                last_fill_at TIMESTAMP,
                closed_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS simulated_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                shares INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                commission REAL DEFAULT 0,
                slippage_cost REAL DEFAULT 0,
                reference_price REAL,
                price_source TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_simulated_orders_status
            ON simulated_orders(status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_simulated_orders_symbol
            ON simulated_orders(symbol)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_simulated_fills_order
            ON simulated_fills(order_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_simulated_fills_created
            ON simulated_fills(created_at)
            """
        )

        watchlist_columns = _get_table_columns(conn, "watchlist")
        extra_watchlist_columns = {
            "priority": "TEXT",
            "stop_loss": "REAL",
            "score": "REAL",
            "status": "TEXT DEFAULT 'active'",
            "updated_at": "TIMESTAMP",
            "metadata": "TEXT",
        }
        for column_name, column_sql in extra_watchlist_columns.items():
            if column_name not in watchlist_columns:
                conn.execute(f"ALTER TABLE watchlist ADD COLUMN {column_name} {column_sql}")

        trade_columns = _get_table_columns(conn, "trades")
        extra_trade_columns = {
            "execution_order_id": "TEXT",
            "execution_status": "TEXT",
            "requested_shares": "INTEGER",
            "remaining_shares": "INTEGER",
            "price_source": "TEXT",
            "slippage_bps": "REAL",
            "slippage_cost": "REAL",
            "fill_ratio": "REAL",
            "simulated": "INTEGER DEFAULT 0",
            "pnl_amount": "REAL",
            "pnl_pct": "REAL",
        }
        for column_name, column_sql in extra_trade_columns.items():
            if column_name not in trade_columns:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {column_name} {column_sql}")


def sync_watchlist_to_db(
    watchlist_data: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Mirror watchlist data into SQLite."""
    ensure_storage_tables(db_path)
    watchlist_data = watchlist_data or {}
    now = datetime.now().isoformat()

    with get_db(db_path) as conn:
        current_symbols = set(watchlist_data.keys())
        if current_symbols:
            placeholders = ",".join("?" for _ in current_symbols)
            conn.execute(
                f"DELETE FROM watchlist WHERE symbol NOT IN ({placeholders})",
                tuple(current_symbols),
            )
        else:
            conn.execute("DELETE FROM watchlist")

        for symbol, entry in watchlist_data.items():
            entry = dict(entry or {})
            added_at = entry.get("added_at") or entry.get("added_date") or now
            metadata = json.dumps(entry, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO watchlist (
                    symbol, name, industry, reason, target_price,
                    alert_price_high, alert_price_low, added_at,
                    priority, stop_loss, score, status, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    industry = excluded.industry,
                    reason = excluded.reason,
                    target_price = excluded.target_price,
                    alert_price_high = excluded.alert_price_high,
                    alert_price_low = excluded.alert_price_low,
                    added_at = excluded.added_at,
                    priority = excluded.priority,
                    stop_loss = excluded.stop_loss,
                    score = excluded.score,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    symbol,
                    entry.get("name", ""),
                    entry.get("industry", ""),
                    entry.get("reason") or entry.get("added_reason", ""),
                    entry.get("target_price"),
                    entry.get("alert_price_high"),
                    entry.get("alert_price_low"),
                    added_at,
                    entry.get("priority"),
                    entry.get("stop_loss"),
                    entry.get("score"),
                    entry.get("status", "active"),
                    now,
                    metadata,
                ),
            )


def load_watchlist(
    default: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Load watchlist from SQLite, bootstrapping from JSON if necessary."""
    ensure_storage_tables(db_path)

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, name, industry, reason, target_price,
                   alert_price_high, alert_price_low, added_at,
                   priority, stop_loss, score, status, updated_at, metadata
            FROM watchlist
            ORDER BY COALESCE(updated_at, added_at) DESC, symbol
            """
        ).fetchall()

    if rows:
        watchlist: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            entry = _load_json_blob(row["metadata"], {})
            entry.setdefault("name", row["name"] or "")
            entry.setdefault("industry", row["industry"] or "")
            if row["reason"] and not entry.get("reason") and not entry.get("added_reason"):
                entry["reason"] = row["reason"]
            if row["target_price"] is not None and "target_price" not in entry:
                entry["target_price"] = row["target_price"]
            if row["alert_price_high"] is not None and "alert_price_high" not in entry:
                entry["alert_price_high"] = row["alert_price_high"]
            if row["alert_price_low"] is not None and "alert_price_low" not in entry:
                entry["alert_price_low"] = row["alert_price_low"]
            if row["stop_loss"] is not None and "stop_loss" not in entry:
                entry["stop_loss"] = row["stop_loss"]
            if row["score"] is not None and "score" not in entry:
                entry["score"] = row["score"]
            if row["priority"] and "priority" not in entry:
                entry["priority"] = row["priority"]
            if row["status"] and "status" not in entry:
                entry["status"] = row["status"]
            if row["added_at"] and not entry.get("added_at") and not entry.get("added_date"):
                entry["added_date"] = str(row["added_at"])[:10]
            watchlist[row["symbol"]] = entry
        return watchlist

    fallback = load_json(WATCHLIST_FILE, default or {})
    if isinstance(fallback, dict) and fallback:
        sync_watchlist_to_db(fallback, db_path=db_path)
    return fallback if isinstance(fallback, dict) else (default or {})


def save_watchlist(
    watchlist_data: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Persist watchlist to SQLite and JSON mirror."""
    sync_watchlist_to_db(watchlist_data, db_path=db_path)
    save_json(WATCHLIST_FILE, watchlist_data)


def load_positions(
    default: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Load current holding positions from SQLite, falling back to JSON."""
    try:
        with get_db(db_path) as conn:
            rows = conn.execute(
                """
                SELECT symbol, name, shares, cost_price, current_price, market_value,
                       profit_loss, profit_loss_pct, position_pct, stop_loss,
                       take_profit, status, bought_at, sold_at, updated_at
                FROM positions
                WHERE status = 'holding'
                ORDER BY symbol
                """
            ).fetchall()
    except sqlite3.Error:
        rows = []

    if rows:
        positions: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            positions[row["symbol"]] = {
                "name": row["name"] or row["symbol"],
                "shares": int(row["shares"] or 0),
                "cost_price": float(row["cost_price"] or 0.0),
                "current_price": float(row["current_price"] or row["cost_price"] or 0.0),
                "market_value": float(row["market_value"] or 0.0),
                "profit_loss": float(row["profit_loss"] or 0.0),
                "profit_loss_pct": float(row["profit_loss_pct"] or 0.0),
                "position_pct": float(row["position_pct"] or 0.0),
                "stop_loss": row["stop_loss"],
                "take_profit": row["take_profit"],
                "status": row["status"] or "holding",
                "bought_at": row["bought_at"],
                "sold_at": row["sold_at"],
                "updated_at": row["updated_at"],
            }
        return positions

    fallback = load_json(POSITIONS_FILE, default or {})
    return fallback if isinstance(fallback, dict) else (default or {})


def load_account(
    default: Optional[Dict[str, Any]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Load the latest account snapshot from SQLite, if available."""
    try:
        with get_db(db_path) as conn:
            row = conn.execute(
                """
                SELECT date, total_asset, cash, market_value, total_profit,
                       total_profit_pct, daily_profit, daily_profit_pct,
                       position_count, max_drawdown, updated_at
                FROM account
                ORDER BY date DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        row = None

    if row:
        return dict(row)

    fallback = load_json(PORTFOLIO_FILE, default or {})
    return fallback if isinstance(fallback, dict) else (default or {})


def build_portfolio_snapshot(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Build a current portfolio snapshot from DB holdings plus portfolio cash."""
    positions = load_positions({}, db_path=db_path)
    latest_account = load_account({}, db_path=db_path)
    raw_portfolio = load_json(PORTFOLIO_FILE, {})

    position_details = []
    total_value = 0.0
    total_profit = 0.0

    for symbol, position in positions.items():
        shares = int(position.get("shares", 0) or 0)
        cost_price = float(position.get("cost_price", 0.0) or 0.0)
        current_price = float(position.get("current_price", cost_price) or cost_price)
        market_value = float(position.get("market_value", current_price * shares) or 0.0)
        profit = float(position.get("profit_loss", (current_price - cost_price) * shares) or 0.0)
        profit_pct = float(
            position.get(
                "profit_loss_pct",
                ((current_price - cost_price) / cost_price * 100) if cost_price else 0.0,
            )
            or 0.0
        )

        total_value += market_value
        total_profit += profit
        position_details.append(
            {
                "name": position.get("name", symbol),
                "code": symbol,
                "shares": shares,
                "cost_price": cost_price,
                "current_price": current_price,
                "market_value": market_value,
                "profit": profit,
                "profit_pct": profit_pct,
            }
        )

    available_cash = raw_portfolio.get("available_cash")
    if available_cash is None:
        available_cash = latest_account.get("cash", 0.0)
    available_cash = float(available_cash or 0.0)

    total_capital = raw_portfolio.get("total_capital")
    if total_capital is None:
        inferred_total_capital = latest_account.get("total_asset", 0.0) - latest_account.get("total_profit", 0.0)
        total_capital = inferred_total_capital if inferred_total_capital else (available_cash + total_value)
    total_capital = float(total_capital or 0.0)

    total_assets = available_cash + total_value
    current_total_profit = total_assets - total_capital
    total_profit_pct = (current_total_profit / total_capital * 100) if total_capital else 0.0
    override_present = raw_portfolio.get("available_cash") is not None or raw_portfolio.get("total_capital") is not None
    snapshot_date = datetime.now().strftime("%Y-%m-%d") if override_present else (latest_account.get("date") if latest_account else None)
    snapshot_updated_at = datetime.now().isoformat() if override_present else (latest_account.get("updated_at") if latest_account else None)
    account_snapshot = dict(latest_account or {})
    account_snapshot.update(
        {
            "date": snapshot_date or account_snapshot.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "total_asset": total_assets,
            "cash": available_cash,
            "market_value": total_value,
            "total_profit": current_total_profit,
            "total_profit_pct": total_profit_pct,
            "position_count": len(position_details),
            "updated_at": snapshot_updated_at or account_snapshot.get("updated_at") or datetime.now().isoformat(),
        }
    )

    return {
        "total_capital": total_capital,
        "available_cash": available_cash,
        "total_value": total_value,
        "total_profit": current_total_profit,
        "total_profit_pct": total_profit_pct,
        "total_assets": total_assets,
        "positions": sorted(position_details, key=lambda item: item.get("profit_pct", 0.0), reverse=True),
        "account": account_snapshot,
    }


def sync_rules_to_db(rules_data: Dict[str, Dict[str, Dict[str, Any]]], db_path: Path = DB_PATH) -> None:
    """Mirror prediction rule library into SQLite."""
    ensure_storage_tables(db_path)
    rules_data = rules_data or {}
    now = datetime.now().isoformat()

    with get_db(db_path) as conn:
        current_keys = {
            (category, rule_id)
            for category, category_rules in rules_data.items()
            for rule_id in category_rules.keys()
        }

        if current_keys:
            placeholders = ",".join("(?, ?)" for _ in current_keys)
            params: list[Any] = []
            for category, rule_id in current_keys:
                params.extend([category, rule_id])
            conn.execute(
                f"""
                DELETE FROM prediction_rules
                WHERE (category, rule_id) NOT IN ({placeholders})
                """,
                tuple(params),
            )
        else:
            conn.execute("DELETE FROM prediction_rules")

        for category, category_rules in rules_data.items():
            for rule_id, rule in category_rules.items():
                rule = dict(rule or {})
                conn.execute(
                    """
                    INSERT INTO prediction_rules (
                        category, rule_id, condition, prediction, weight,
                        confidence_boost, samples, success_rate, source,
                        status, data_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(category, rule_id) DO UPDATE SET
                        condition = excluded.condition,
                        prediction = excluded.prediction,
                        weight = excluded.weight,
                        confidence_boost = excluded.confidence_boost,
                        samples = excluded.samples,
                        success_rate = excluded.success_rate,
                        source = excluded.source,
                        status = excluded.status,
                        data_json = excluded.data_json,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        category,
                        rule_id,
                        rule.get("condition"),
                        rule.get("prediction"),
                        rule.get("weight"),
                        rule.get("confidence_boost"),
                        rule.get("samples", 0),
                        rule.get("success_rate", 0.0),
                        rule.get("source"),
                        rule.get("status", "active"),
                        json.dumps(rule, ensure_ascii=False),
                        rule.get("created_at"),
                        rule.get("updated_at") or now,
                    ),
                )


def load_rules(
    default: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load prediction rules from SQLite, bootstrapping from JSON if necessary."""
    ensure_storage_tables(db_path)

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT category, rule_id, data_json
            FROM prediction_rules
            ORDER BY category, rule_id
            """
        ).fetchall()

    if rows:
        rules: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            rules.setdefault(row["category"], {})[row["rule_id"]] = _load_json_blob(row["data_json"], {})
        return rules

    fallback = load_json(RULES_FILE, default or {})
    if isinstance(fallback, dict) and fallback:
        sync_rules_to_db(fallback, db_path=db_path)
    return fallback if isinstance(fallback, dict) else (default or {})


def save_rules(
    rules_data: Dict[str, Dict[str, Dict[str, Any]]],
    db_path: Path = DB_PATH,
) -> None:
    """Persist prediction rules to SQLite and JSON mirror."""
    sync_rules_to_db(rules_data, db_path=db_path)
    save_json(RULES_FILE, rules_data)


def sync_validation_pool_to_db(
    validation_pool: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Mirror rule validation pool into SQLite."""
    ensure_storage_tables(db_path)
    validation_pool = validation_pool or {}
    now = datetime.now().isoformat()

    with get_db(db_path) as conn:
        current_ids = set(validation_pool.keys())
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            conn.execute(
                f"DELETE FROM rule_validation_pool WHERE rule_id NOT IN ({placeholders})",
                tuple(current_ids),
            )
        else:
            conn.execute("DELETE FROM rule_validation_pool")

        for rule_id, rule in validation_pool.items():
            rule = dict(rule or {})
            backtest = rule.get("backtest") or {}
            live_test = rule.get("live_test") or {}
            conn.execute(
                """
                INSERT INTO rule_validation_pool (
                    rule_id, category, rule_text, testable_form, source,
                    source_book, status, confidence, backtest_samples,
                    backtest_success_rate, live_samples, live_success_rate,
                    data_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    category = excluded.category,
                    rule_text = excluded.rule_text,
                    testable_form = excluded.testable_form,
                    source = excluded.source,
                    source_book = excluded.source_book,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    backtest_samples = excluded.backtest_samples,
                    backtest_success_rate = excluded.backtest_success_rate,
                    live_samples = excluded.live_samples,
                    live_success_rate = excluded.live_success_rate,
                    data_json = excluded.data_json,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    rule_id,
                    rule.get("category"),
                    rule.get("rule"),
                    rule.get("testable_form"),
                    rule.get("source"),
                    rule.get("source_book"),
                    rule.get("status", "validating"),
                    rule.get("confidence", 0.0),
                    backtest.get("samples", 0),
                    backtest.get("success_rate", 0.0),
                    live_test.get("samples", 0),
                    live_test.get("success_rate", 0.0),
                    json.dumps(rule, ensure_ascii=False),
                    rule.get("created_at"),
                    rule.get("updated_at") or now,
                ),
            )


def load_validation_pool(
    default: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Load validation pool from SQLite, bootstrapping from JSON if necessary."""
    ensure_storage_tables(db_path)

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT rule_id, data_json
            FROM rule_validation_pool
            ORDER BY COALESCE(updated_at, created_at) DESC, rule_id
            """
        ).fetchall()

    if rows:
        return {
            row["rule_id"]: _load_json_blob(row["data_json"], {})
            for row in rows
        }

    fallback = load_json(VALIDATION_POOL_FILE, default or {})
    if isinstance(fallback, dict) and fallback:
        sync_validation_pool_to_db(fallback, db_path=db_path)
    return fallback if isinstance(fallback, dict) else (default or {})


def save_validation_pool(
    validation_pool: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Persist validation pool to SQLite and JSON mirror."""
    sync_validation_pool_to_db(validation_pool, db_path=db_path)
    save_json(VALIDATION_POOL_FILE, validation_pool)


def sync_rejected_rules_to_db(
    rejected_rules: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Mirror rejected rules into SQLite."""
    ensure_storage_tables(db_path)
    rejected_rules = rejected_rules or {}
    now = datetime.now().isoformat()

    with get_db(db_path) as conn:
        current_ids = set(rejected_rules.keys())
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            conn.execute(
                f"DELETE FROM rejected_rules WHERE rule_id NOT IN ({placeholders})",
                tuple(current_ids),
            )
        else:
            conn.execute("DELETE FROM rejected_rules")

        for rule_id, rule in rejected_rules.items():
            rule = dict(rule or {})
            conn.execute(
                """
                INSERT INTO rejected_rules (
                    rule_id, category, rule_text, testable_form, source,
                    source_book, status, confidence, reject_reason,
                    data_json, created_at, updated_at, rejected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    category = excluded.category,
                    rule_text = excluded.rule_text,
                    testable_form = excluded.testable_form,
                    source = excluded.source,
                    source_book = excluded.source_book,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    reject_reason = excluded.reject_reason,
                    data_json = excluded.data_json,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    rejected_at = excluded.rejected_at
                """,
                (
                    rule_id,
                    rule.get("category"),
                    rule.get("rule") or rule.get("condition"),
                    rule.get("testable_form"),
                    rule.get("source"),
                    rule.get("source_book"),
                    rule.get("status", "rejected"),
                    rule.get("confidence", 0.0),
                    rule.get("reject_reason") or rule.get("reason"),
                    json.dumps(rule, ensure_ascii=False),
                    rule.get("created_at"),
                    rule.get("updated_at") or now,
                    rule.get("rejected_at"),
                ),
            )


def load_rejected_rules(
    default: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Load rejected rules from SQLite, bootstrapping from JSON if necessary."""
    ensure_storage_tables(db_path)

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT rule_id, data_json
            FROM rejected_rules
            ORDER BY COALESCE(rejected_at, updated_at, created_at) DESC, rule_id
            """
        ).fetchall()

    if rows:
        return {
            row["rule_id"]: _load_json_blob(row["data_json"], {})
            for row in rows
        }

    fallback = load_json(REJECTED_RULES_FILE, default or {})
    if isinstance(fallback, dict) and fallback:
        sync_rejected_rules_to_db(fallback, db_path=db_path)
    return fallback if isinstance(fallback, dict) else (default or {})


def save_rejected_rules(
    rejected_rules: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> None:
    """Persist rejected rules to SQLite and JSON mirror."""
    sync_rejected_rules_to_db(rejected_rules, db_path=db_path)
    save_json(REJECTED_RULES_FILE, rejected_rules)


def reconcile_rule_stores(
    rules_data: Dict[str, Dict[str, Dict[str, Any]]],
    validation_pool: Dict[str, Dict[str, Any]],
    rejected_rules: Dict[str, Dict[str, Any]],
) -> Tuple[
    Dict[str, Dict[str, Dict[str, Any]]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Any],
]:
    """Resolve duplicate rule IDs across active/pool/rejected stores."""
    rules_data = {
        category: {rule_id: dict(rule or {}) for rule_id, rule in (category_rules or {}).items()}
        for category, category_rules in (rules_data or {}).items()
    }
    validation_pool = {rule_id: dict(rule or {}) for rule_id, rule in (validation_pool or {}).items()}
    rejected_rules = {rule_id: dict(rule or {}) for rule_id, rule in (rejected_rules or {}).items()}

    candidates: Dict[str, list[Dict[str, Any]]] = {}

    for category, category_rules in rules_data.items():
        for rule_id, rule in category_rules.items():
            candidates.setdefault(rule_id, []).append(
                {
                    "store": "active",
                    "category": category,
                    "rule_id": rule_id,
                    "rule": rule,
                    "timestamp": _parse_timestamp(
                        rule.get("updated_at") or rule.get("promoted_at") or rule.get("created_at")
                    ),
                }
            )

    for rule_id, rule in validation_pool.items():
        candidates.setdefault(rule_id, []).append(
            {
                "store": "validation_pool",
                "category": None,
                "rule_id": rule_id,
                "rule": rule,
                "timestamp": _parse_timestamp(
                    rule.get("updated_at") or rule.get("created_at") or rule.get("started_at")
                ),
            }
        )

    for rule_id, rule in rejected_rules.items():
        candidates.setdefault(rule_id, []).append(
            {
                "store": "rejected",
                "category": rule.get("category"),
                "rule_id": rule_id,
                "rule": rule,
                "timestamp": _parse_timestamp(
                    rule.get("rejected_at") or rule.get("updated_at") or rule.get("created_at")
                ),
            }
        )

    clean_rules: Dict[str, Dict[str, Dict[str, Any]]] = {}
    clean_pool: Dict[str, Dict[str, Any]] = {}
    clean_rejected: Dict[str, Dict[str, Any]] = {}
    removed: Dict[str, list[str]] = {"active": [], "validation_pool": [], "rejected": []}

    for rule_id, entries in candidates.items():
        active_entries = [entry for entry in entries if entry["store"] == "active"]
        pool_entries = [entry for entry in entries if entry["store"] == "validation_pool"]
        rejected_entries = [entry for entry in entries if entry["store"] == "rejected"]

        if active_entries:
            winner = max(active_entries, key=lambda item: item["timestamp"])
            latest_rejected = max(rejected_entries, key=lambda item: item["timestamp"]) if rejected_entries else None
            if latest_rejected and latest_rejected["timestamp"] > winner["timestamp"]:
                winner = latest_rejected
        elif pool_entries:
            winner = max(pool_entries, key=lambda item: item["timestamp"])
            latest_rejected = max(rejected_entries, key=lambda item: item["timestamp"]) if rejected_entries else None
            if latest_rejected and latest_rejected["timestamp"] > winner["timestamp"]:
                winner = latest_rejected
        else:
            winner = max(rejected_entries, key=lambda item: item["timestamp"])

        for entry in entries:
            if entry is not winner:
                removed[entry["store"]].append(rule_id)

        if winner["store"] == "active":
            category = winner["category"] or "uncategorized"
            clean_rules.setdefault(category, {})[rule_id] = winner["rule"]
        elif winner["store"] == "validation_pool":
            clean_pool[rule_id] = winner["rule"]
        else:
            clean_rejected[rule_id] = winner["rule"]

    clean_rules = {category: category_rules for category, category_rules in clean_rules.items() if category_rules}
    changed = any(removed.values()) or (
        len(clean_rules) != len(rules_data)
        or len(clean_pool) != len(validation_pool)
        or len(clean_rejected) != len(rejected_rules)
    )

    return clean_rules, clean_pool, clean_rejected, {"changed": changed, "removed": removed}


def load_rule_state(
    default_rules: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    default_validation_pool: Optional[Dict[str, Dict[str, Any]]] = None,
    default_rejected_rules: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Path = DB_PATH,
) -> Tuple[
    Dict[str, Dict[str, Dict[str, Any]]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Any],
]:
    """Load and reconcile active rules, validation pool, and rejected rules."""
    rules_data = load_rules(default_rules or {}, db_path=db_path)
    validation_pool = load_validation_pool(default_validation_pool or {}, db_path=db_path)
    rejected_rules = load_rejected_rules(default_rejected_rules or {}, db_path=db_path)
    return reconcile_rule_stores(rules_data, validation_pool, rejected_rules)


def save_rule_state(
    rules_data: Dict[str, Dict[str, Dict[str, Any]]],
    validation_pool: Dict[str, Dict[str, Any]],
    rejected_rules: Dict[str, Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Persist a reconciled rule-state snapshot to SQLite and JSON mirrors."""
    clean_rules, clean_pool, clean_rejected, summary = reconcile_rule_stores(
        rules_data,
        validation_pool,
        rejected_rules,
    )
    save_rules(clean_rules, db_path=db_path)
    save_validation_pool(clean_pool, db_path=db_path)
    save_rejected_rules(clean_rejected, db_path=db_path)
    return summary


def sync_predictions_to_db(predictions_data: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    """Mirror normalized predictions into the dashboard database."""
    normalized = normalize_prediction_collection(predictions_data)
    now = datetime.now().isoformat()

    with get_db(db_path) as conn:
        existing_rows = conn.execute(
            "SELECT id, symbol, created_at, status FROM predictions"
        ).fetchall()
        existing = {(row["symbol"], row["created_at"]): row["id"] for row in existing_rows}

        current_keys = set()
        all_predictions = list(normalized["active"].values()) + normalized["history"]

        for pred in all_predictions:
            key = (pred.get("code"), pred.get("created_at"))
            if not key[0] or not key[1]:
                continue

            current_keys.add(key)
            result = pred.get("result") or {}
            result_status = prediction_result_status(pred)
            reasons = json.dumps(pred.get("reasons", []), ensure_ascii=False)
            risks = json.dumps(pred.get("risks", []), ensure_ascii=False)
            params = (
                pred.get("code"),
                pred.get("name", ""),
                pred.get("direction", "neutral"),
                pred.get("current_price", 0.0),
                pred.get("target_price", 0.0),
                pred.get("confidence", 0),
                pred.get("timeframe", "1周"),
                reasons,
                risks,
                pred.get("source_agent", "prediction_system"),
                pred.get("status", "active"),
                result_status,
                result.get("final_price"),
                pred.get("created_at"),
                now,
                pred.get("verified_at"),
            )

            if key in existing:
                conn.execute(
                    """
                    UPDATE predictions SET
                        symbol = ?, name = ?, direction = ?, current_price = ?, target_price = ?,
                        confidence = ?, timeframe = ?, reasons = ?, risks = ?, source_agent = ?,
                        status = ?, result = ?, actual_end_price = ?, created_at = ?, updated_at = ?, verified_at = ?
                    WHERE id = ?
                    """,
                    params + (existing[key],),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO predictions (
                        symbol, name, direction, current_price, target_price,
                        confidence, timeframe, reasons, risks, source_agent,
                        status, result, actual_end_price, created_at, updated_at, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                existing[key] = cursor.lastrowid

        for row in existing_rows:
            key = (row["symbol"], row["created_at"])
            if row["status"] == "active" and key not in current_keys:
                conn.execute(
                    """
                    UPDATE predictions
                    SET status = 'expired', result = 'expired', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )


def sync_positions_and_account_to_db(
    positions: Dict[str, Dict[str, Any]],
    cash: float,
    portfolio: Optional[Dict[str, Any]] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, float]:
    """Mirror positions plus account summary into the dashboard database."""
    portfolio_data = dict(portfolio or {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    total_market_value = 0.0

    with get_db(db_path) as conn:
        db_rows = conn.execute(
            "SELECT id, symbol FROM positions WHERE status = 'holding'"
        ).fetchall()
        db_symbols = {row["symbol"] for row in db_rows}
        current_symbols = set(positions.keys())

        for symbol in db_symbols - current_symbols:
            conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))

        for symbol, position in positions.items():
            name = position.get("name", "")
            shares = int(position.get("shares", 0) or 0)
            cost_price = float(position.get("cost_price", 0) or 0.0)
            current_price = float(position.get("current_price", cost_price) or cost_price)
            stop_loss = float(position.get("stop_loss", round(cost_price * 0.92, 2)) or 0.0)
            take_profit = float(position.get("take_profit", round(cost_price * 1.2, 2)) or 0.0)
            bought_at = position.get("buy_date") or position.get("bought_at") or now
            market_value = current_price * shares
            profit_loss = (current_price - cost_price) * shares
            profit_loss_pct = ((current_price - cost_price) / cost_price * 100) if cost_price else 0.0

            total_market_value += market_value

            params = (
                name,
                shares,
                cost_price,
                current_price,
                market_value,
                profit_loss,
                profit_loss_pct,
                stop_loss,
                take_profit,
                now,
                symbol,
            )

            if symbol in db_symbols:
                conn.execute(
                    """
                    UPDATE positions SET
                        name = ?, shares = ?, cost_price = ?, current_price = ?,
                        market_value = ?, profit_loss = ?, profit_loss_pct = ?,
                        stop_loss = ?, take_profit = ?, updated_at = ?
                    WHERE symbol = ? AND status = 'holding'
                    """,
                    params,
                )
            else:
                conn.execute(
                    """
                    INSERT INTO positions (
                        symbol, name, shares, cost_price, current_price,
                        market_value, profit_loss, profit_loss_pct,
                        stop_loss, take_profit, status, bought_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'holding', ?, ?)
                    """,
                    (
                        symbol,
                        name,
                        shares,
                        cost_price,
                        current_price,
                        market_value,
                        profit_loss,
                        profit_loss_pct,
                        stop_loss,
                        take_profit,
                        bought_at,
                        now,
                    ),
                )

        total_capital = float(portfolio_data.get("total_capital", cash + total_market_value) or 0.0)
        total_asset = cash + total_market_value
        total_profit = total_asset - total_capital
        total_profit_pct = (total_profit / total_capital * 100) if total_capital else 0.0
        daily_profit = float(portfolio_data.get("daily_profit", 0.0) or 0.0)
        daily_profit_pct = float(portfolio_data.get("daily_profit_pct", 0.0) or 0.0)
        max_drawdown = float(portfolio_data.get("max_drawdown", 0.0) or 0.0)
        position_count = len(positions)

        account_row = conn.execute(
            "SELECT id FROM account WHERE date = ? ORDER BY id DESC LIMIT 1",
            (today,),
        ).fetchone()

        account_params = (
            today,
            total_asset,
            cash,
            total_market_value,
            total_profit,
            total_profit_pct,
            daily_profit,
            daily_profit_pct,
            position_count,
            max_drawdown,
            now,
        )

        if account_row:
            conn.execute(
                """
                UPDATE account SET
                    date = ?, total_asset = ?, cash = ?, market_value = ?,
                    total_profit = ?, total_profit_pct = ?, daily_profit = ?,
                    daily_profit_pct = ?, position_count = ?, max_drawdown = ?, updated_at = ?
                WHERE id = ?
                """,
                account_params + (account_row["id"],),
            )
        else:
            conn.execute(
                """
                INSERT INTO account (
                    date, total_asset, cash, market_value,
                    total_profit, total_profit_pct, daily_profit,
                    daily_profit_pct, position_count, max_drawdown, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                account_params,
            )

    return {
        "cash": cash,
        "market_value": total_market_value,
        "total_asset": total_asset,
        "total_profit": total_profit,
        "total_profit_pct": total_profit_pct,
        "position_count": float(len(positions)),
    }


def load_recent_simulated_orders(limit: int = 20, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Return recent simulated paper-trading orders from SQLite."""
    ensure_storage_tables(db_path)
    try:
        with get_db(db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM simulated_orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.Error:
        rows = []
    return [dict(row) for row in rows]


def load_open_simulated_orders(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Return pending or partially-filled paper-trading orders."""
    ensure_storage_tables(db_path)
    try:
        with get_db(db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM simulated_orders
                WHERE status IN ('pending', 'partial_filled')
                ORDER BY created_at ASC
                """
            ).fetchall()
    except sqlite3.Error:
        rows = []
    return [dict(row) for row in rows]


def get_simulated_order_metrics(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Summarize the current paper-trading execution ledger."""
    ensure_storage_tables(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    default = {
        "today_order_count": 0,
        "today_filled_count": 0,
        "open_order_count": 0,
        "partial_fill_count": 0,
        "today_commission": 0.0,
        "today_slippage_cost": 0.0,
        "recent_orders": [],
    }
    try:
        with get_db(db_path) as conn:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS today_order_count,
                    SUM(CASE WHEN status IN ('filled', 'partial_filled') THEN 1 ELSE 0 END) AS today_filled_count,
                    SUM(CASE WHEN status IN ('pending', 'partial_filled') THEN 1 ELSE 0 END) AS open_order_count,
                    SUM(CASE WHEN status = 'partial_filled' THEN 1 ELSE 0 END) AS partial_fill_count,
                    SUM(CASE WHEN commission IS NOT NULL THEN commission ELSE 0 END) AS today_commission,
                    SUM(CASE WHEN slippage_cost IS NOT NULL THEN slippage_cost ELSE 0 END) AS today_slippage_cost
                FROM simulated_orders
                WHERE substr(created_at, 1, 10) = ?
                """,
                (today,),
            ).fetchone()
            recent_orders = conn.execute(
                """
                SELECT *
                FROM simulated_orders
                ORDER BY created_at DESC
                LIMIT 10
                """
            ).fetchall()
    except sqlite3.Error:
        return default

    payload = dict(summary or {})
    return {
        **default,
        **{
            "today_order_count": int(payload.get("today_order_count") or 0),
            "today_filled_count": int(payload.get("today_filled_count") or 0),
            "open_order_count": int(payload.get("open_order_count") or 0),
            "partial_fill_count": int(payload.get("partial_fill_count") or 0),
            "today_commission": float(payload.get("today_commission") or 0.0),
            "today_slippage_cost": float(payload.get("today_slippage_cost") or 0.0),
            "recent_orders": [dict(row) for row in recent_orders],
        },
    }
