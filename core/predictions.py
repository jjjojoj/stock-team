"""Shared helpers for prediction lifecycle and result normalization."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

TIMEFRAME_TO_DAYS = {
    "1天": 1,
    "1日": 1,
    "1周": 7,
    "1个月": 30,
    "1月": 30,
}


def parse_iso_timestamp(value: Optional[str]) -> datetime:
    """Parse an ISO timestamp while tolerating missing values."""
    if not value:
        return datetime.now()
    return datetime.fromisoformat(value)


def timeframe_to_days(timeframe: Optional[str]) -> int:
    """Convert a human timeframe label into validation days."""
    return TIMEFRAME_TO_DAYS.get(timeframe or "1周", 7)


def derive_prediction_id(payload: Dict[str, Any], created_at: datetime) -> str:
    """Build a stable prediction id from code and creation time."""
    code = payload.get("code", "unknown")
    return f"{code}_{created_at.strftime('%Y%m%d_%H%M')}"


def normalize_prediction_result(result: Any) -> Optional[Dict[str, Any]]:
    """Normalize result payloads from legacy and new formats."""
    if result in (None, "", {}):
        return None

    if isinstance(result, str):
        status = "wrong" if result == "incorrect" else result
        return {
            "status": status,
            "correct": status == "correct",
            "partial": status == "partial",
        }

    if not isinstance(result, dict):
        return None

    normalized = dict(result)
    status = normalized.get("status")
    correct = bool(normalized.get("correct"))
    partial = bool(normalized.get("partial"))

    if status == "incorrect":
        status = "wrong"

    if status is None:
        if correct:
            status = "correct"
        elif partial:
            status = "partial"
        elif normalized.get("verified_at") or normalized.get("final_price") is not None:
            status = "wrong"
        else:
            status = "pending"

    if status == "correct":
        correct = True
        partial = False
    elif status == "partial":
        correct = False
        partial = True
    elif status in {"wrong", "pending", "expired"}:
        correct = False
        partial = False

    normalized["status"] = status
    normalized["correct"] = correct
    normalized["partial"] = partial
    return normalized


def prediction_result_status(prediction: Dict[str, Any]) -> str:
    """Return a consistent result status for dashboards and validators."""
    result = normalize_prediction_result(prediction.get("result"))
    if result:
        return result["status"]

    status = prediction.get("status")
    if status == "expired":
        return "expired"
    return "pending"


def normalize_prediction_record(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one prediction record without mutating the input."""
    normalized = deepcopy(prediction)
    created_at = parse_iso_timestamp(normalized.get("created_at"))

    normalized["created_at"] = created_at.isoformat()
    normalized["timeframe"] = normalized.get("timeframe") or "1周"
    normalized["id"] = normalized.get("id") or derive_prediction_id(normalized, created_at)
    normalized.setdefault("updates", [])
    normalized.setdefault("analysis", None)
    normalized.setdefault("reasons", [])
    normalized.setdefault("risks", [])

    rules_used = normalized.get("rules_used") or normalized.get("matched_rules") or []
    normalized["rules_used"] = list(dict.fromkeys(rules_used))
    normalized["matched_rules"] = list(dict.fromkeys(normalized.get("matched_rules") or normalized["rules_used"]))

    due_at = normalized.get("due_at")
    if not due_at:
        due_at = created_at + timedelta(days=timeframe_to_days(normalized["timeframe"]))
        normalized["due_at"] = due_at.isoformat()
    else:
        normalized["due_at"] = parse_iso_timestamp(due_at).isoformat()

    normalized["result"] = normalize_prediction_result(normalized.get("result"))
    verified_at = normalized.get("verified_at") or (normalized["result"] or {}).get("verified_at")
    if verified_at:
        normalized["verified_at"] = parse_iso_timestamp(verified_at).isoformat()

    normalized["result_status"] = prediction_result_status(normalized)
    normalized["verified"] = normalized["result_status"] in {"correct", "partial", "wrong"}

    if normalized["verified"]:
        normalized["status"] = "verified"
    else:
        normalized["status"] = normalized.get("status") or "active"

    return normalized


def normalize_prediction_collection(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize the full predictions payload."""
    payload = data or {"active": {}, "history": []}
    normalized = {"active": {}, "history": []}

    for prediction_id, prediction in payload.get("active", {}).items():
        if not isinstance(prediction, dict):
            continue
        record = normalize_prediction_record({**prediction, "id": prediction.get("id", prediction_id)})
        if record["status"] == "active":
            normalized["active"][record["id"]] = record
        else:
            normalized["history"].append(record)

    for prediction in payload.get("history", []):
        if not isinstance(prediction, dict):
            continue
        record = normalize_prediction_record(prediction)
        if record["status"] == "active":
            normalized["active"][record["id"]] = record
        else:
            normalized["history"].append(record)

    normalized["history"].sort(key=lambda item: item.get("created_at", ""))
    return normalized


def build_prediction_record(
    prediction: Dict[str, Any],
    prediction_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a normalized active prediction record."""
    created = created_at or datetime.now()
    payload = dict(prediction)
    payload["id"] = prediction_id or payload.get("id") or derive_prediction_id(payload, created)
    payload["created_at"] = created.isoformat()
    payload["status"] = payload.get("status") or "active"
    return normalize_prediction_record(payload)


def is_prediction_due(prediction: Dict[str, Any], as_of: Optional[datetime] = None) -> bool:
    """Return whether an active prediction reached its validation time."""
    record = normalize_prediction_record(prediction)
    if record.get("status") != "active":
        return False
    now = as_of or datetime.now()
    return parse_iso_timestamp(record["due_at"]) <= now


def build_verification_result(
    direction: str,
    start_price: float,
    target_price: float,
    current_price: float,
    verified_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compute a unified verification result payload."""
    verified_time = (verified_at or datetime.now()).isoformat()
    price_change = (current_price / start_price - 1) * 100 if start_price else 0.0

    correct = False
    partial = False

    if direction == "up":
        if current_price >= target_price:
            correct = True
        elif price_change > 0:
            partial = True
    elif direction == "down":
        if current_price <= target_price:
            correct = True
        elif price_change < 0:
            partial = True
    else:
        if abs(price_change) < 2:
            correct = True
        elif abs(price_change) < 5:
            partial = True

    status = "correct" if correct else "partial" if partial else "wrong"
    return {
        "verified_at": verified_time,
        "final_price": current_price,
        "price_change_pct": round(price_change, 2),
        "correct": correct,
        "partial": partial,
        "status": status,
    }


def apply_prediction_verdict(
    prediction: Dict[str, Any],
    current_price: float,
    verified_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return a verified prediction record with a normalized result payload."""
    record = normalize_prediction_record(prediction)
    record["result"] = build_verification_result(
        direction=record.get("direction", "neutral"),
        start_price=float(record.get("current_price") or 0.0),
        target_price=float(record.get("target_price") or 0.0),
        current_price=float(current_price),
        verified_at=verified_at,
    )
    record["verified_at"] = record["result"]["verified_at"]
    record["result_status"] = record["result"]["status"]
    record["verified"] = True
    record["status"] = "verified"
    return record
