"""Shared filesystem paths and sync helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
