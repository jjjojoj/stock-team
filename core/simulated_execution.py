"""Paper-trading execution engine with order, fill, fee, and partial-fill tracking."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .storage import DB_PATH, get_db, load_json, ensure_storage_tables

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "paper_execution.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "board_lot": 100,
    "min_commission": 5.0,
    "commission_rate": 0.0003,
    "transfer_fee_rate": 0.00001,
    "stamp_duty_rate": 0.0005,
    "buy_slippage_bps": 6.0,
    "sell_slippage_bps": 8.0,
    "fallback_slippage_bps": 14.0,
    "simulated_price_slippage_bps": 35.0,
    "min_capacity_value": 150000.0,
    "capacity_value_per_yi_market_cap": 6000.0,
    "partial_fill_min_ratio": 0.2,
    "stale_order_minutes": 120,
}


def load_paper_execution_config() -> Dict[str, Any]:
    payload = load_json(CONFIG_FILE, {})
    config = dict(DEFAULT_CONFIG)
    if isinstance(payload, dict):
        config.update(payload)
    return config


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class PaperExecutionEngine:
    """Persist realistic simulated orders and fills into the main SQLite ledger."""

    def __init__(self, db_path: Path = DB_PATH, config: Optional[Dict[str, Any]] = None):
        self.db_path = Path(db_path)
        self.config = config or load_paper_execution_config()
        ensure_storage_tables(self.db_path)

    def _generate_order_id(self, symbol: str, direction: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"sim_{direction}_{symbol.replace('.', '')}_{stamp}_{uuid4().hex[:6]}"

    def _normalize_requested_shares(
        self,
        requested_shares: int,
        *,
        direction: str,
        available_shares: Optional[int] = None,
    ) -> int:
        requested_shares = int(requested_shares or 0)
        if requested_shares <= 0:
            return 0

        board_lot = max(1, int(self.config.get("board_lot", 100) or 100))
        if direction == "sell" and available_shares is not None:
            requested_shares = min(requested_shares, int(available_shares or 0))
            if requested_shares <= 0:
                return 0
            if requested_shares < board_lot:
                return requested_shares
            normalized = (requested_shares // board_lot) * board_lot
            return normalized or requested_shares

        return (requested_shares // board_lot) * board_lot

    def _estimate_capacity_value(self, market_cap: Optional[float]) -> float:
        market_cap_yi = max(0.0, _safe_float(market_cap))
        return max(
            _safe_float(self.config.get("min_capacity_value"), 150000.0),
            market_cap_yi * _safe_float(self.config.get("capacity_value_per_yi_market_cap"), 6000.0),
        )

    def _estimate_slippage_bps(
        self,
        *,
        direction: str,
        price_source: str,
        requested_amount: float,
        market_cap: Optional[float],
    ) -> float:
        base = _safe_float(
            self.config.get("buy_slippage_bps" if direction == "buy" else "sell_slippage_bps"),
            6.0 if direction == "buy" else 8.0,
        )
        normalized_source = str(price_source or "unknown").lower()
        if normalized_source not in {"live", "live_api", "adapter"}:
            base = max(base, _safe_float(self.config.get("fallback_slippage_bps"), 14.0))
        if "simulated" in normalized_source:
            base = max(base, _safe_float(self.config.get("simulated_price_slippage_bps"), 35.0))

        capacity_value = self._estimate_capacity_value(market_cap)
        pressure = requested_amount / max(capacity_value, 1.0)
        if pressure <= 0.7:
            return round(base, 2)
        return round(base + min(60.0, (pressure - 0.7) * 18.0), 2)

    def _estimate_fillable_shares(
        self,
        *,
        direction: str,
        requested_shares: int,
        price: float,
        cash_available: Optional[float],
        market_cap: Optional[float],
        available_shares: Optional[int],
    ) -> int:
        if requested_shares <= 0 or price <= 0:
            return 0

        board_lot = max(1, int(self.config.get("board_lot", 100) or 100))
        normalized = requested_shares

        if direction == "buy":
            gross_cash = max(0.0, _safe_float(cash_available))
            fee_buffer = (
                1
                + _safe_float(self.config.get("commission_rate"), 0.0003)
                + _safe_float(self.config.get("transfer_fee_rate"), 0.00001)
                + _safe_float(self.config.get("buy_slippage_bps"), 6.0) / 10000
            )
            affordable = int(gross_cash // max(price * fee_buffer, 0.01)) if gross_cash else requested_shares
            affordable = (affordable // board_lot) * board_lot
            normalized = min(normalized, affordable) if affordable > 0 else 0
        elif available_shares is not None:
            normalized = min(normalized, int(available_shares or 0))

        if normalized <= 0:
            return 0

        capacity_value = self._estimate_capacity_value(market_cap)
        capacity_shares = int(capacity_value // price)
        if direction == "buy" or normalized >= board_lot:
            capacity_shares = (capacity_shares // board_lot) * board_lot

        if direction == "sell" and available_shares is not None and available_shares < board_lot:
            capacity_shares = max(capacity_shares, available_shares)

        if capacity_shares <= 0:
            return 0
        if normalized <= capacity_shares:
            return normalized

        partial_ratio = max(
            _safe_float(self.config.get("partial_fill_min_ratio"), 0.2),
            min(1.0, capacity_shares / max(normalized, 1)),
        )
        partial_shares = int(normalized * partial_ratio)
        if direction == "buy" or partial_shares >= board_lot:
            partial_shares = (partial_shares // board_lot) * board_lot
        if direction == "sell" and available_shares is not None and available_shares < board_lot:
            partial_shares = min(available_shares, max(partial_shares, 1))
        return min(normalized, max(partial_shares, capacity_shares if capacity_shares < normalized else partial_shares))

    def _estimate_fees(self, *, direction: str, amount: float) -> Dict[str, float]:
        commission = max(
            _safe_float(self.config.get("min_commission"), 5.0),
            amount * _safe_float(self.config.get("commission_rate"), 0.0003),
        )
        transfer_fee = amount * _safe_float(self.config.get("transfer_fee_rate"), 0.00001)
        stamp_duty = amount * _safe_float(self.config.get("stamp_duty_rate"), 0.0005) if direction == "sell" else 0.0
        total = commission + transfer_fee + stamp_duty
        return {
            "commission_only": round(commission, 4),
            "transfer_fee": round(transfer_fee, 4),
            "stamp_duty": round(stamp_duty, 4),
            "total": round(total, 4),
        }

    def _insert_trade_fill(
        self,
        conn,
        *,
        order_id: str,
        symbol: str,
        name: str,
        direction: str,
        requested_shares: int,
        filled_shares: int,
        remaining_shares: int,
        status: str,
        fill_price: float,
        reference_price: float,
        price_source: str,
        slippage_bps: float,
        slippage_cost: float,
        amount: float,
        commission: float,
        cash_effect: float,
        reason: str,
        prediction_id: Optional[str],
        pnl_amount: Optional[float],
        pnl_pct: Optional[float],
        notes: str,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO simulated_fills (
                order_id, symbol, direction, shares, price, amount,
                commission, slippage_cost, reference_price, price_source,
                notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                symbol,
                direction,
                filled_shares,
                round(fill_price, 4),
                round(amount, 4),
                round(commission, 4),
                round(slippage_cost, 4),
                round(reference_price, 4),
                price_source,
                notes,
                created_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO trades (
                symbol, name, direction, shares, price, amount,
                commission, reason, executed_at, execution_order_id,
                execution_status, requested_shares, remaining_shares,
                price_source, slippage_bps, slippage_cost, fill_ratio,
                simulated, pnl_amount, pnl_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                symbol,
                name,
                direction,
                filled_shares,
                round(fill_price, 4),
                round(amount, 4),
                round(commission, 4),
                reason,
                created_at,
                order_id,
                status,
                requested_shares,
                remaining_shares,
                price_source,
                round(slippage_bps, 2),
                round(slippage_cost, 4),
                round(filled_shares / max(requested_shares, 1), 4),
                None if pnl_amount is None else round(pnl_amount, 4),
                None if pnl_pct is None else round(pnl_pct, 4),
            ),
        )

    def _build_result(
        self,
        *,
        order_id: str,
        symbol: str,
        name: str,
        direction: str,
        requested_shares: int,
        filled_shares: int,
        remaining_shares: int,
        status: str,
        fill_price: Optional[float],
        reference_price: float,
        commission: float,
        slippage_bps: float,
        slippage_cost: float,
        cash_effect: float,
        reason: str,
        price_source: str,
        prediction_id: Optional[str],
        market_cap: Optional[float],
        metadata: Optional[Dict[str, Any]],
        pnl_amount: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        fill_amount = round((_safe_float(fill_price) * filled_shares), 4) if fill_price else 0.0
        return {
            "ok": filled_shares > 0 or status in {"cancelled", "rejected"},
            "order_id": order_id,
            "symbol": symbol,
            "name": name,
            "direction": direction,
            "requested_shares": requested_shares,
            "filled_shares": filled_shares,
            "remaining_shares": remaining_shares,
            "status": status,
            "fill_ratio": round(filled_shares / max(requested_shares, 1), 4),
            "fill_price": round(fill_price, 4) if fill_price else None,
            "reference_price": round(reference_price, 4),
            "fill_amount": fill_amount,
            "commission": round(commission, 4),
            "slippage_bps": round(slippage_bps, 2),
            "slippage_cost": round(slippage_cost, 4),
            "cash_effect": round(cash_effect, 4),
            "reason": reason,
            "price_source": price_source,
            "prediction_id": prediction_id,
            "market_cap": _safe_float(market_cap, 0.0),
            "metadata": metadata or {},
            "pnl_amount": None if pnl_amount is None else round(pnl_amount, 4),
            "pnl_pct": None if pnl_pct is None else round(pnl_pct, 4),
            "note": note,
            "created_at": datetime.now().isoformat(),
        }

    def _create_order(
        self,
        conn,
        *,
        order_id: str,
        symbol: str,
        name: str,
        direction: str,
        order_type: str,
        requested_shares: int,
        requested_price: float,
        reference_price: float,
        price_source: str,
        market_cap: Optional[float],
        reason: str,
        prediction_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> str:
        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO simulated_orders (
                order_id, symbol, name, direction, order_type,
                requested_shares, filled_shares, remaining_shares,
                requested_price, avg_fill_price, fill_ratio, status,
                cash_effect, commission, slippage_cost, slippage_bps,
                reference_price, price_source, market_cap, reason,
                prediction_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 0, 'pending', 0, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                symbol,
                name,
                direction,
                order_type,
                requested_shares,
                requested_shares,
                round(requested_price, 4),
                round(reference_price, 4),
                price_source,
                _safe_float(market_cap, 0.0),
                reason,
                prediction_id,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        return now

    def _load_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM simulated_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        return dict(row) if row else None

    def _apply_fill(
        self,
        conn,
        order: Dict[str, Any],
        *,
        fillable_shares: int,
        reference_price: float,
        price_source: str,
        reason: str,
        cost_basis_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        direction = str(order["direction"])
        requested_shares = int(order["requested_shares"] or 0)
        already_filled = int(order.get("filled_shares") or 0)
        remaining_before = int(order.get("remaining_shares") or 0)
        market_cap = _safe_float(order.get("market_cap"))
        slippage_bps = self._estimate_slippage_bps(
            direction=direction,
            price_source=price_source,
            requested_amount=reference_price * max(remaining_before, 1),
            market_cap=market_cap,
        )
        direction_multiplier = 1 if direction == "buy" else -1
        fill_price = reference_price * (1 + direction_multiplier * slippage_bps / 10000)
        amount = fill_price * fillable_shares
        fee_info = self._estimate_fees(direction=direction, amount=amount)
        commission = fee_info["total"]
        slippage_cost = abs(fill_price - reference_price) * fillable_shares
        cash_effect = -(amount + commission) if direction == "buy" else (amount - commission)
        total_filled = already_filled + fillable_shares
        remaining_after = max(0, requested_shares - total_filled)
        fill_ratio = total_filled / max(requested_shares, 1)
        status = "filled" if remaining_after == 0 else "partial_filled"
        now = datetime.now().isoformat()

        total_cash_effect = _safe_float(order.get("cash_effect")) + cash_effect
        total_commission = _safe_float(order.get("commission")) + commission
        total_slippage_cost = _safe_float(order.get("slippage_cost")) + slippage_cost
        weighted_avg_price = (
            (_safe_float(order.get("avg_fill_price")) * already_filled + fill_price * fillable_shares) / max(total_filled, 1)
        )

        pnl_amount = None
        pnl_pct = None
        if direction == "sell" and cost_basis_price and cost_basis_price > 0:
            gross_profit = (fill_price - cost_basis_price) * fillable_shares
            pnl_amount = gross_profit - commission
            pnl_pct = pnl_amount / (cost_basis_price * fillable_shares) * 100

        conn.execute(
            """
            UPDATE simulated_orders SET
                filled_shares = ?, remaining_shares = ?, avg_fill_price = ?,
                fill_ratio = ?, status = ?, cash_effect = ?, commission = ?,
                slippage_cost = ?, slippage_bps = ?, reference_price = ?,
                price_source = ?, updated_at = ?, last_fill_at = ?, closed_at = ?
            WHERE order_id = ?
            """,
            (
                total_filled,
                remaining_after,
                round(weighted_avg_price, 4),
                round(fill_ratio, 4),
                status,
                round(total_cash_effect, 4),
                round(total_commission, 4),
                round(total_slippage_cost, 4),
                round(slippage_bps, 2),
                round(reference_price, 4),
                price_source,
                now,
                now,
                now if remaining_after == 0 else None,
                order["order_id"],
            ),
        )

        self._insert_trade_fill(
            conn,
            order_id=order["order_id"],
            symbol=order["symbol"],
            name=order.get("name") or order["symbol"],
            direction=direction,
            requested_shares=requested_shares,
            filled_shares=fillable_shares,
            remaining_shares=remaining_after,
            status=status,
            fill_price=fill_price,
            reference_price=reference_price,
            price_source=price_source,
            slippage_bps=slippage_bps,
            slippage_cost=slippage_cost,
            amount=amount,
            commission=commission,
            cash_effect=cash_effect,
            reason=reason,
            prediction_id=order.get("prediction_id"),
            pnl_amount=pnl_amount,
            pnl_pct=pnl_pct,
            notes="simulated_fill",
            created_at=now,
        )

        return self._build_result(
            order_id=order["order_id"],
            symbol=order["symbol"],
            name=order.get("name") or order["symbol"],
            direction=direction,
            requested_shares=requested_shares,
            filled_shares=fillable_shares,
            remaining_shares=remaining_after,
            status=status,
            fill_price=fill_price,
            reference_price=reference_price,
            commission=commission,
            slippage_bps=slippage_bps,
            slippage_cost=slippage_cost,
            cash_effect=cash_effect,
            reason=reason,
            price_source=price_source,
            prediction_id=order.get("prediction_id"),
            market_cap=market_cap,
            metadata=json.loads(order.get("metadata_json") or "{}"),
            pnl_amount=pnl_amount,
            pnl_pct=pnl_pct,
            note="partial_fill" if remaining_after > 0 else "filled",
        )

    def submit_order(
        self,
        *,
        symbol: str,
        name: str,
        direction: str,
        requested_shares: int,
        reference_price: float,
        price_source: str,
        reason: str,
        cash_available: Optional[float] = None,
        available_shares: Optional[int] = None,
        prediction_id: Optional[str] = None,
        market_cap: Optional[float] = None,
        requested_price: Optional[float] = None,
        order_type: str = "market",
        metadata: Optional[Dict[str, Any]] = None,
        cost_basis_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        direction = str(direction or "").lower()
        normalized_shares = self._normalize_requested_shares(
            requested_shares,
            direction=direction,
            available_shares=available_shares,
        )
        order_id = self._generate_order_id(symbol, direction)

        if direction not in {"buy", "sell"} or normalized_shares <= 0 or reference_price <= 0:
            with get_db(self.db_path) as conn:
                created_at = self._create_order(
                    conn,
                    order_id=order_id,
                    symbol=symbol,
                    name=name,
                    direction=direction or "unknown",
                    order_type=order_type,
                    requested_shares=max(normalized_shares, 0),
                    requested_price=requested_price or reference_price or 0.0,
                    reference_price=reference_price or 0.0,
                    price_source=price_source or "unavailable",
                    market_cap=market_cap,
                    reason=reason,
                    prediction_id=prediction_id,
                    metadata=metadata,
                )
                conn.execute(
                    """
                    UPDATE simulated_orders SET
                        status = 'rejected', closed_at = ?, updated_at = ?
                    WHERE order_id = ?
                    """,
                    (created_at, created_at, order_id),
                )
            return self._build_result(
                order_id=order_id,
                symbol=symbol,
                name=name,
                direction=direction or "unknown",
                requested_shares=max(normalized_shares, 0),
                filled_shares=0,
                remaining_shares=max(normalized_shares, 0),
                status="rejected",
                fill_price=None,
                reference_price=reference_price or 0.0,
                commission=0.0,
                slippage_bps=0.0,
                slippage_cost=0.0,
                cash_effect=0.0,
                reason=reason,
                price_source=price_source or "unavailable",
                prediction_id=prediction_id,
                market_cap=market_cap,
                metadata=metadata,
                note="invalid_order",
            )

        fillable_shares = self._estimate_fillable_shares(
            direction=direction,
            requested_shares=normalized_shares,
            price=reference_price,
            cash_available=cash_available,
            market_cap=market_cap,
            available_shares=available_shares,
        )

        with get_db(self.db_path) as conn:
            self._create_order(
                conn,
                order_id=order_id,
                symbol=symbol,
                name=name,
                direction=direction,
                order_type=order_type,
                requested_shares=normalized_shares,
                requested_price=requested_price or reference_price,
                reference_price=reference_price,
                price_source=price_source,
                market_cap=market_cap,
                reason=reason,
                prediction_id=prediction_id,
                metadata=metadata,
            )
            order = {
                "order_id": order_id,
                "symbol": symbol,
                "name": name,
                "direction": direction,
                "requested_shares": normalized_shares,
                "filled_shares": 0,
                "remaining_shares": normalized_shares,
                "reference_price": reference_price,
                "price_source": price_source,
                "market_cap": _safe_float(market_cap),
                "reason": reason,
                "prediction_id": prediction_id,
                "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
            }

            if fillable_shares <= 0:
                now = datetime.now().isoformat()
                conn.execute(
                    """
                    UPDATE simulated_orders SET
                        status = 'rejected', updated_at = ?, closed_at = ?
                    WHERE order_id = ?
                    """,
                    (now, now, order_id),
                )
                return self._build_result(
                    order_id=order_id,
                    symbol=symbol,
                    name=name,
                    direction=direction,
                    requested_shares=normalized_shares,
                    filled_shares=0,
                    remaining_shares=normalized_shares,
                    status="rejected",
                    fill_price=None,
                    reference_price=reference_price,
                    commission=0.0,
                    slippage_bps=0.0,
                    slippage_cost=0.0,
                    cash_effect=0.0,
                    reason=reason,
                    price_source=price_source,
                    prediction_id=prediction_id,
                    market_cap=market_cap,
                    metadata=metadata,
                    note="insufficient_liquidity_or_cash",
                )

            return self._apply_fill(
                conn,
                order,
                fillable_shares=fillable_shares,
                reference_price=reference_price,
                price_source=price_source,
                reason=reason,
                cost_basis_price=cost_basis_price,
            )

    def reconcile_open_orders(
        self,
        quote_provider: Callable[[str], Dict[str, Any]],
        *,
        cash_available: Optional[float] = None,
        available_shares_provider: Optional[Callable[[str], int]] = None,
        max_orders: int = 20,
    ) -> List[Dict[str, Any]]:
        """Try to fill pending partial orders or cancel stale remainders."""
        ensure_storage_tables(self.db_path)
        results: List[Dict[str, Any]] = []
        stale_after = timedelta(minutes=int(self.config.get("stale_order_minutes", 120) or 120))
        local_cash = None if cash_available is None else float(cash_available)

        with get_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM simulated_orders
                WHERE status IN ('pending', 'partial_filled')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max_orders,),
            ).fetchall()

            for row in rows:
                order = dict(row)
                created_at = _parse_timestamp(order.get("created_at")) or datetime.now()
                if datetime.now() - created_at > stale_after:
                    now = datetime.now().isoformat()
                    conn.execute(
                        """
                        UPDATE simulated_orders SET
                            status = 'cancelled', updated_at = ?, closed_at = ?
                        WHERE order_id = ?
                        """,
                        (now, now, order["order_id"]),
                    )
                    results.append(
                        self._build_result(
                            order_id=order["order_id"],
                            symbol=order["symbol"],
                            name=order.get("name") or order["symbol"],
                            direction=order["direction"],
                            requested_shares=int(order.get("requested_shares") or 0),
                            filled_shares=0,
                            remaining_shares=int(order.get("remaining_shares") or 0),
                            status="cancelled",
                            fill_price=None,
                            reference_price=_safe_float(order.get("reference_price")),
                            commission=0.0,
                            slippage_bps=0.0,
                            slippage_cost=0.0,
                            cash_effect=0.0,
                            reason=str(order.get("reason") or ""),
                            price_source=str(order.get("price_source") or "unknown"),
                            prediction_id=order.get("prediction_id"),
                            market_cap=_safe_float(order.get("market_cap")),
                            metadata=json.loads(order.get("metadata_json") or "{}"),
                            note="stale_order_cancelled",
                        )
                    )
                    continue

                quote = quote_provider(order["symbol"]) or {}
                price = _safe_float(quote.get("price"))
                if price <= 0:
                    continue

                remaining_shares = int(order.get("remaining_shares") or 0)
                available_shares = None
                if available_shares_provider is not None and str(order["direction"]) == "sell":
                    try:
                        available_shares = int(available_shares_provider(order["symbol"]) or 0)
                    except Exception:
                        available_shares = remaining_shares
                fillable_shares = self._estimate_fillable_shares(
                    direction=str(order["direction"]),
                    requested_shares=remaining_shares,
                    price=price,
                    cash_available=local_cash if str(order["direction"]) == "buy" else None,
                    market_cap=_safe_float(quote.get("market_cap"), _safe_float(order.get("market_cap"))),
                    available_shares=available_shares if str(order["direction"]) == "sell" else None,
                )
                if fillable_shares <= 0:
                    continue

                order["market_cap"] = _safe_float(quote.get("market_cap"), _safe_float(order.get("market_cap")))
                result = self._apply_fill(
                    conn,
                    order,
                    fillable_shares=fillable_shares,
                    reference_price=price,
                    price_source=str(quote.get("source") or order.get("price_source") or "unknown"),
                    reason=str(order.get("reason") or ""),
                    cost_basis_price=_safe_float((quote or {}).get("cost_basis_price")),
                )
                if local_cash is not None and str(order["direction"]) == "buy":
                    local_cash += float(result.get("cash_effect") or 0.0)
                results.append(result)
        return results
