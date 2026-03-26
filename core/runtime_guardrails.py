"""Runtime guardrails for long-running OpenClaw-managed tasks."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "runtime_guardrails.json"
STATE_FILE = PROJECT_ROOT / "data" / "runtime_guardrails_state.json"
LOCK_DIR = PROJECT_ROOT / "data" / "runtime_locks"
DAILY_SEARCH_DIR = PROJECT_ROOT / "data" / "daily_search"
PREDICTIONS_FILE = PROJECT_ROOT / "data" / "predictions.json"
FUNDAMENTAL_SNAPSHOT_FILE = PROJECT_ROOT / "config" / "fundamental_data.md"
STOCK_POOL_FILE = PROJECT_ROOT / "config" / "stock_pool.md"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "force_read_only": False,
    "lock_stale_seconds": 7200,
    "autopilot": {
        "auto_read_only_enabled": True,
        "critical_tasks": [
            "ai_predictor",
            "selector",
            "daily_stock_research",
            "midday_review",
            "auto_trader_v3_buy",
            "auto_trader_v3_sell",
        ],
        "consecutive_error_threshold": 2,
        "auto_read_only_minutes": 180,
        "recovery_success_threshold": 2,
    },
    "freshness": {
        "daily_search_hours": 18,
        "predictions_hours": 36,
        "fundamental_snapshot_hours": 240,
        "stock_pool_hours": 240,
    },
    "midday_learning": {
        "min_verified_predictions": 4,
        "min_wrong_cases": 3,
        "min_bias_ratio": 0.6,
        "consecutive_error_runs": 2,
        "adjustment_step": 0.02,
        "min_confidence_threshold": 0.65,
        "max_confidence_threshold": 0.9,
        "rollback_window_runs": 3,
        "rollback_drop_pct": 8.0,
    },
}


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        pass
    return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_guardrail_config() -> Dict[str, Any]:
    payload = _load_json(CONFIG_FILE, {})
    config = dict(DEFAULT_CONFIG)
    config.update(payload if isinstance(payload, dict) else {})
    config["autopilot"] = {
        **DEFAULT_CONFIG["autopilot"],
        **(payload.get("autopilot", {}) if isinstance(payload, dict) else {}),
    }
    config["freshness"] = {
        **DEFAULT_CONFIG["freshness"],
        **(payload.get("freshness", {}) if isinstance(payload, dict) else {}),
    }
    config["midday_learning"] = {
        **DEFAULT_CONFIG["midday_learning"],
        **(payload.get("midday_learning", {}) if isinstance(payload, dict) else {}),
    }
    return config


def load_guardrail_state() -> Dict[str, Any]:
    payload = _load_json(STATE_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("events", [])
    payload.setdefault("midday_learning", {"history": [], "adjustments": []})
    payload.setdefault(
        "autopilot",
        {
            "auto_read_only": {
                "active": False,
                "reason": "",
                "triggered_by": "",
                "triggered_at": None,
                "expires_at": None,
                "recovered_successes": 0,
            },
            "task_health": {},
            "last_transition": None,
        },
    )
    payload["autopilot"].setdefault(
        "auto_read_only",
        {
            "active": False,
            "reason": "",
            "triggered_by": "",
            "triggered_at": None,
            "expires_at": None,
            "recovered_successes": 0,
        },
    )
    payload["autopilot"].setdefault("task_health", {})
    payload["autopilot"].setdefault("last_transition", None)
    return payload


def save_guardrail_state(state: Dict[str, Any]) -> None:
    _save_json(STATE_FILE, state)


def _append_event(state: Dict[str, Any], task: str, level: str, message: str) -> None:
    events = state.setdefault("events", [])
    events.append(
        {
            "time": datetime.now().isoformat(),
            "task": task,
            "level": level,
            "message": message,
        }
    )
    state["events"] = events[-200:]


def _expire_auto_read_only_if_needed(state: Dict[str, Any]) -> bool:
    auto = state.setdefault("autopilot", {}).setdefault("auto_read_only", {})
    if not auto.get("active"):
        return False

    expires_at = auto.get("expires_at")
    if not expires_at:
        return False

    try:
        expires = datetime.fromisoformat(str(expires_at))
    except ValueError:
        expires = None

    if expires and datetime.now() >= expires:
        auto["active"] = False
        auto["expired_at"] = datetime.now().isoformat()
        auto["recovered_successes"] = 0
        state["autopilot"]["last_transition"] = {
            "status": "expired",
            "time": datetime.now().isoformat(),
            "reason": auto.get("reason", ""),
            "triggered_by": auto.get("triggered_by", ""),
        }
        _append_event(state, "autopilot", "info", "自动只读已到期，恢复普通模式")
        return True
    return False


def _set_auto_read_only(state: Dict[str, Any], task: str, message: str, config: Dict[str, Any]) -> None:
    autopilot = state["autopilot"]
    auto = autopilot.setdefault("auto_read_only", {})
    duration = int(config["autopilot"].get("auto_read_only_minutes", 180))
    now = datetime.now()
    expires_at = (now + timedelta(minutes=duration)).isoformat()
    already_active = bool(auto.get("active"))

    auto.update(
        {
            "active": True,
            "reason": message,
            "triggered_by": task,
            "triggered_at": auto.get("triggered_at") if already_active else now.isoformat(),
            "last_extended_at": now.isoformat() if already_active else None,
            "expires_at": expires_at,
            "recovered_successes": 0,
        }
    )
    autopilot["last_transition"] = {
        "status": "activated" if not already_active else "extended",
        "time": now.isoformat(),
        "reason": message,
        "triggered_by": task,
        "expires_at": expires_at,
    }
    event_message = (
        f"自动切换只读: {task} 连续异常，暂停自动买入/预测生成 {duration} 分钟"
        if not already_active
        else f"自动只读续期: {task} 再次异常，延长保护到 {expires_at}"
    )
    _append_event(state, "autopilot", "warning", event_message)


def _clear_auto_read_only(state: Dict[str, Any], task: str, reason: str) -> None:
    autopilot = state["autopilot"]
    auto = autopilot.setdefault("auto_read_only", {})
    if not auto.get("active"):
        return

    auto.update(
        {
            "active": False,
            "cleared_at": datetime.now().isoformat(),
            "cleared_by": task,
            "clear_reason": reason,
            "recovered_successes": 0,
        }
    )
    autopilot["last_transition"] = {
        "status": "recovered",
        "time": datetime.now().isoformat(),
        "reason": reason,
        "triggered_by": task,
    }
    _append_event(state, "autopilot", "info", f"退出自动只读: {reason}")


def get_guardrail_control_state(
    config: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    config = config or load_guardrail_config()
    state = state or load_guardrail_state()
    changed = _expire_auto_read_only_if_needed(state)
    if changed and persist:
        save_guardrail_state(state)

    auto = state.get("autopilot", {}).get("auto_read_only", {})
    manual = bool(config.get("force_read_only"))
    automatic = bool(auto.get("active"))
    active = manual or automatic
    source = "manual" if manual else ("automatic" if automatic else "none")

    return {
        "active": active,
        "manual": manual,
        "automatic": automatic,
        "source": source,
        "reason": "配置强制只读" if manual else auto.get("reason", ""),
        "triggered_by": auto.get("triggered_by"),
        "triggered_at": auto.get("triggered_at"),
        "expires_at": auto.get("expires_at"),
        "recovered_successes": int(auto.get("recovered_successes", 0) or 0),
    }


def _update_task_health(
    task: str,
    level: str,
    message: str,
    *,
    emit_event: bool,
) -> None:
    config = load_guardrail_config()
    state = load_guardrail_state()
    changed = _expire_auto_read_only_if_needed(state)
    autopilot = state.setdefault("autopilot", {})
    task_health = autopilot.setdefault("task_health", {})
    health = task_health.setdefault(
        task,
        {
            "consecutive_errors": 0,
            "consecutive_successes": 0,
            "last_level": None,
            "last_message": "",
            "last_time": None,
        },
    )
    now = datetime.now().isoformat()

    if emit_event:
        _append_event(state, task, level, message)

    if level == "error":
        health["consecutive_errors"] = int(health.get("consecutive_errors", 0) or 0) + 1
        health["consecutive_successes"] = 0
    elif level == "success":
        health["consecutive_successes"] = int(health.get("consecutive_successes", 0) or 0) + 1
        health["consecutive_errors"] = 0
    elif level == "warning":
        health["consecutive_successes"] = 0

    health["last_level"] = level
    health["last_message"] = message
    health["last_time"] = now

    critical_tasks = set(config["autopilot"].get("critical_tasks", []))
    auto_cfg = config["autopilot"]
    auto = autopilot.setdefault("auto_read_only", {})
    if task in critical_tasks and auto_cfg.get("auto_read_only_enabled", True):
        if level == "error" and int(health.get("consecutive_errors", 0) or 0) >= int(
            auto_cfg.get("consecutive_error_threshold", 2)
        ):
            if not config.get("force_read_only"):
                _set_auto_read_only(state, task, message, config)
        elif level == "success":
            if auto.get("active") and auto.get("triggered_by") == task:
                auto["recovered_successes"] = int(auto.get("recovered_successes", 0) or 0) + 1
                if int(auto.get("recovered_successes", 0) or 0) >= int(
                    auto_cfg.get("recovery_success_threshold", 2)
                ):
                    _clear_auto_read_only(
                        state,
                        task,
                        f"{task} 连续恢复 {auto_cfg.get('recovery_success_threshold', 2)} 次",
                    )
            elif auto.get("active") and auto.get("triggered_by") != task:
                auto["recovered_successes"] = int(auto.get("recovered_successes", 0) or 0)
        elif level in {"warning", "error"} and auto.get("active") and auto.get("triggered_by") == task:
            auto["recovered_successes"] = 0

    if changed or True:
        save_guardrail_state(state)


def record_guardrail_event(task: str, level: str, message: str) -> None:
    _update_task_health(task, level, message, emit_event=True)


def record_guardrail_success(task: str, message: str = "任务执行完成") -> None:
    _update_task_health(task, "success", message, emit_event=False)


def _file_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 3600


def _latest_daily_search_age_hours() -> Optional[float]:
    if not DAILY_SEARCH_DIR.exists():
        return None
    files = sorted(path for path in DAILY_SEARCH_DIR.glob("*.json") if path.stem[:8].isdigit())
    if not files:
        return None
    return _file_age_hours(files[-1])


def get_runtime_snapshot() -> Dict[str, Optional[float]]:
    return {
        "daily_search_age_hours": _latest_daily_search_age_hours(),
        "predictions_age_hours": _file_age_hours(PREDICTIONS_FILE),
        "fundamental_snapshot_age_hours": _file_age_hours(FUNDAMENTAL_SNAPSHOT_FILE),
        "stock_pool_age_hours": _file_age_hours(STOCK_POOL_FILE),
    }


@dataclass
class GuardrailResult:
    ok: bool
    mode: str
    reasons: List[str]
    warnings: List[str]
    snapshot: Dict[str, Optional[float]]


def evaluate_runtime_mode(
    mode: str,
    *,
    universe_count: int = 0,
    active_prediction_count: int = 0,
    available_cash: Optional[float] = None,
) -> GuardrailResult:
    config = load_guardrail_config()
    control = get_guardrail_control_state(config=config)
    snapshot = get_runtime_snapshot()
    reasons: List[str] = []
    warnings: List[str] = []

    if control.get("active") and mode in {"trade_buy", "prediction_generate"}:
        if control.get("source") == "automatic":
            reasons.append("系统当前处于只读模式（自动保护）")
        else:
            reasons.append("系统当前处于只读模式")

    freshness = config["freshness"]
    daily_search_age = snapshot.get("daily_search_age_hours")
    predictions_age = snapshot.get("predictions_age_hours")
    fundamentals_age = snapshot.get("fundamental_snapshot_age_hours")
    stock_pool_age = snapshot.get("stock_pool_age_hours")

    if mode in {"selection", "research"}:
        if stock_pool_age is None:
            reasons.append("股票池配置缺失")
        elif stock_pool_age > freshness["stock_pool_hours"]:
            warnings.append(f"股票池配置已超过 {freshness['stock_pool_hours']} 小时未更新")

        if fundamentals_age is None:
            warnings.append("基本面快照缺失，将完全依赖实时行情与缓存")
        elif fundamentals_age > freshness["fundamental_snapshot_hours"]:
            warnings.append(f"基本面快照已超过 {freshness['fundamental_snapshot_hours']} 小时未更新")

    if mode == "prediction_generate":
        if universe_count <= 0:
            reasons.append("预测股票池为空")
        if daily_search_age is not None and daily_search_age > freshness["daily_search_hours"]:
            warnings.append(f"daily_search 已超过 {freshness['daily_search_hours']} 小时未更新")

    if mode == "trade_buy":
        if universe_count <= 0:
            reasons.append("观察池为空，禁止自动买入")
        if active_prediction_count <= 0:
            reasons.append("没有可用的活跃预测，禁止自动买入")
        if predictions_age is None:
            reasons.append("预测数据缺失，禁止自动买入")
        elif predictions_age > freshness["predictions_hours"]:
            reasons.append(f"预测数据已超过 {freshness['predictions_hours']} 小时未更新")
        if available_cash is not None and available_cash <= 0:
            reasons.append("可用现金不足，禁止自动买入")

    if mode == "trade_sell":
        if predictions_age is None:
            warnings.append("预测数据缺失，卖出逻辑将只依赖价格风控")

    return GuardrailResult(
        ok=not reasons,
        mode=mode,
        reasons=reasons,
        warnings=warnings,
        snapshot=snapshot,
    )


class TaskLockedError(RuntimeError):
    """Raised when a task lock already exists."""


@contextmanager
def task_lock(task_name: str, stale_seconds: Optional[int] = None) -> Iterator[Path]:
    config = load_guardrail_config()
    stale_after = stale_seconds or int(config.get("lock_stale_seconds", 7200))
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{task_name}.lock"

    if lock_path.exists():
        try:
            payload = _load_json(lock_path, {})
            created_at = datetime.fromisoformat(str(payload.get("created_at")))
        except Exception:
            created_at = datetime.fromtimestamp(lock_path.stat().st_mtime)

        if datetime.now() - created_at <= timedelta(seconds=stale_after):
            raise TaskLockedError(f"任务 {task_name} 已在运行中")
        lock_path.unlink(missing_ok=True)

    _save_json(
        lock_path,
        {
            "task_name": task_name,
            "created_at": datetime.now().isoformat(),
            "pid": os.getpid(),
        },
    )
    try:
        yield lock_path
    finally:
        lock_path.unlink(missing_ok=True)
