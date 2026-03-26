"""Shared fundamental-data access with live/cache/snapshot fallback."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
LIVE_CACHE_FILE = DATA_DIR / "live_fundamentals_cache.json"

LIVE_CACHE_HOURS = 12


def _normalize_symbol(raw_code: str) -> str:
    raw = str(raw_code or "").strip()
    if raw.startswith(("sh.", "sz.", "bj.")):
        return raw
    if raw.isdigit():
        if raw.startswith(("6", "9")):
            return f"sh.{raw}"
        if raw.startswith(("4", "8")):
            return f"bj.{raw}"
        return f"sz.{raw}"
    return raw


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "--"):
        return None
    text = str(value).replace("%", "").replace(",", "").replace("+", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        logger.warning("Failed to load %s", path)
    return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _parse_snapshot_markdown() -> Dict[str, Dict[str, float]]:
    fundamentals_file = CONFIG_DIR / "fundamental_data.md"
    if not fundamentals_file.exists():
        return {}

    snapshot: Dict[str, Dict[str, float]] = {}
    in_code_block = False
    for raw_line in fundamentals_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"代码", "------"} or len(cells) < 8:
            continue

        symbol = _normalize_symbol(cells[0])
        pb = _safe_float(cells[2])
        pe = _safe_float(cells[3])
        roe = _safe_float(cells[4])
        growth = _safe_float(cells[5])
        dividend = _safe_float(cells[6])
        snapshot[symbol] = {
            "pb": pb or 0.0,
            "pe": pe or 0.0,
            "roe": roe or 0.0,
            "net_profit_growth": growth or 0.0,
            "dividend_yield": dividend or 0.0,
            "source": "snapshot",
        }

    return snapshot


def _cache_is_fresh(entry: Dict[str, Any], max_age_hours: int = LIVE_CACHE_HOURS) -> bool:
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(str(fetched_at))
    except ValueError:
        return False
    return datetime.now() - fetched <= timedelta(hours=max_age_hours)


def _query_live_market_snapshot(codes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    codes = [_normalize_symbol(code) for code in codes if code]
    if not codes or not VENV_PYTHON.exists():
        return {}

    helper = r"""
import json
import sys
from datetime import datetime

codes = sys.argv[1:]
result = {}

try:
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    if "代码" in df.columns:
        df["代码"] = df["代码"].astype(str).str.zfill(6)
    else:
        print(json.dumps({"__error__": "spot schema missing 代码"}, ensure_ascii=False))
        raise SystemExit(0)

    for raw_code in codes:
        symbol = raw_code.split(".", 1)[1] if "." in raw_code else raw_code
        row = df[df["代码"] == symbol]
        if row.empty:
            continue
        item = row.iloc[0]
        result[raw_code] = {
            "name": item.get("名称", ""),
            "price": item.get("最新价"),
            "market_cap": (float(item.get("总市值", 0)) / 1e8) if item.get("总市值") not in (None, "", "-") else None,
            "pe": item.get("市盈率-动态"),
            "pb": item.get("市净率"),
            "fetched_at": datetime.now().isoformat(),
            "source": "live",
        }
except Exception as exc:
    print(json.dumps({"__error__": str(exc)}, ensure_ascii=False))
    raise SystemExit(0)

print(json.dumps(result, ensure_ascii=False))
"""

    completed = subprocess.run(
        [str(VENV_PYTHON), "-c", helper, *codes],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )

    stdout = (completed.stdout or "").strip().splitlines()
    if not stdout:
        return {}

    last_line = stdout[-1]
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError:
        logger.warning("Live fundamentals query returned non-JSON output: %s", last_line[:200])
        return {}

    if "__error__" in payload:
        logger.warning("Live fundamentals query failed: %s", payload["__error__"])
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for code, item in payload.items():
        normalized[_normalize_symbol(code)] = {
            "name": item.get("name", ""),
            "price": _safe_float(item.get("price")),
            "market_cap": _safe_float(item.get("market_cap")),
            "pe": _safe_float(item.get("pe")),
            "pb": _safe_float(item.get("pb")),
            "fetched_at": item.get("fetched_at"),
            "source": item.get("source", "live"),
        }
    return normalized


def load_live_market_snapshot(codes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    requested = [_normalize_symbol(code) for code in codes if code]
    cache = _load_json(LIVE_CACHE_FILE, {})
    cache = cache if isinstance(cache, dict) else {}

    results: Dict[str, Dict[str, Any]] = {}
    missing: list[str] = []
    for code in requested:
        cached = cache.get(code)
        if isinstance(cached, dict) and _cache_is_fresh(cached):
            results[code] = dict(cached, source="cache")
        else:
            missing.append(code)

    if missing:
        live = _query_live_market_snapshot(missing)
        for code, item in live.items():
            cache[code] = item
            results[code] = item
        _save_json(LIVE_CACHE_FILE, cache)

    return results


def get_fundamental_bundles(
    codes: Iterable[str],
    *,
    watchlist_data: Optional[Dict[str, Dict[str, Any]]] = None,
    legacy_data: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    snapshot = _parse_snapshot_markdown()
    live = load_live_market_snapshot(codes)
    watchlist_data = watchlist_data or {}
    legacy_data = legacy_data or {}

    bundles: Dict[str, Dict[str, Any]] = {}
    for raw_code in codes:
        code = _normalize_symbol(raw_code)
        merged: Dict[str, Any] = {"symbol": code, "source": "unavailable"}

        for source_name, source_payload in (
            ("live", live.get(code, {})),
            ("snapshot", snapshot.get(code, {})),
            ("watchlist", watchlist_data.get(code, {})),
            ("legacy", legacy_data.get(code, {})),
        ):
            if not isinstance(source_payload, dict):
                continue
            for key in ("name", "price", "market_cap", "pe", "pb", "roe", "net_profit_growth", "dividend_yield"):
                value = source_payload.get(key)
                if value not in (None, "", "-", "--"):
                    existing = merged.get(key)
                    if existing not in (None, "", "-", "--"):
                        continue
                    merged[key] = _safe_float(value) if key not in {"name"} else value
            if merged.get("source") == "unavailable" and source_payload:
                merged["source"] = source_name
            if "fetched_at" in source_payload and source_payload.get("fetched_at"):
                merged.setdefault("fetched_at", source_payload.get("fetched_at"))

        merged.setdefault("name", code)
        merged.setdefault("price", None)
        merged.setdefault("market_cap", None)
        merged.setdefault("pe", 0.0)
        merged.setdefault("pb", 0.0)
        merged.setdefault("roe", 0.0)
        merged.setdefault("net_profit_growth", 0.0)
        merged.setdefault("dividend_yield", 0.0)
        if merged.get("source") in {"cache", "snapshot", "watchlist", "legacy"}:
            try:
                from .runtime_guardrails import record_datasource_fallback

                record_datasource_fallback(
                    "fundamentals",
                    "fundamentals",
                    str(merged.get("source")),
                    f"{code} 基本面改用 {merged.get('source')} 数据",
                )
            except Exception:
                pass
        bundles[code] = merged

    return bundles


def get_fundamental_bundle(
    code: str,
    *,
    watchlist_data: Optional[Dict[str, Dict[str, Any]]] = None,
    legacy_data: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    normalized = _normalize_symbol(code)
    return get_fundamental_bundles(
        [normalized],
        watchlist_data=watchlist_data,
        legacy_data=legacy_data,
    ).get(normalized, {"symbol": normalized, "source": "unavailable"})
