#!/usr/bin/env python3
"""
下午开盘前更新

基于午盘反思、当前预测、自选池和资金状态，生成一条统一的下午策略卡片。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from core.storage import PREDICTIONS_FILE, load_json, load_watchlist


def load_midday_review() -> Dict:
    today_file = PROJECT_ROOT / "data" / f"midday_review_{datetime.now().strftime('%Y%m%d')}.json"
    return load_json(today_file, {})


def load_portfolio() -> Dict:
    return load_json(PROJECT_ROOT / "config" / "portfolio.json", {})


def load_positions() -> Dict:
    return load_json(PROJECT_ROOT / "config" / "positions.json", {})


def load_predictions() -> List[Dict]:
    raw = load_json(PREDICTIONS_FILE, {"active": {}, "history": []})
    active = raw.get("active", {})
    if isinstance(active, dict):
        return list(active.values())
    return []


def summarize_predictions(predictions: List[Dict]) -> List[str]:
    ranked = sorted(
        predictions,
        key=lambda item: (item.get("confidence", 0), item.get("direction") == "up"),
        reverse=True,
    )[:5]

    lines = []
    for pred in ranked:
        direction = {"up": "看多", "down": "看空"}.get(pred.get("direction"), "观望")
        lines.append(
            f"- {pred.get('name', pred.get('code', '未知'))}: {direction} | "
            f"置信度 {pred.get('confidence', 0)}% | 目标价 ¥{pred.get('target_price', 0):.2f}"
        )
    return lines or ["- 当前暂无活跃预测"]


def summarize_lessons(midday: Dict) -> List[str]:
    lessons = midday.get("lessons") or []
    if not lessons:
        return ["- 今日暂无午盘反思结论，维持既有配置"]

    lines = []
    for lesson in lessons[:3]:
        content = lesson.get("content", "未提供")
        action = lesson.get("action", "保持观察")
        lines.append(f"- {content} → {action}")
    return lines


def build_report() -> str:
    midday = load_midday_review()
    portfolio = load_portfolio()
    positions = load_positions()
    watchlist = load_watchlist({})
    predictions = load_predictions()

    available_cash = portfolio.get("available_cash", 0)
    total_assets = portfolio.get("total_capital", 0)
    midday_results = midday.get("results", {})
    verified = midday_results.get("verified", 0)
    correct = midday_results.get("correct", 0)
    wrong = midday_results.get("wrong", 0)
    accuracy = (correct / verified * 100) if verified else 0

    lines = [
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "午盘反思摘要",
        f"- 已验证预测：{verified} 个",
        f"- 正确：{correct} | 错误：{wrong} | 准确率：{accuracy:.1f}%",
        "",
        "下午策略调整",
        *summarize_lessons(midday),
        "",
        "重点跟踪预测",
        *summarize_predictions(predictions),
        "",
        "资金与观察池",
        f"- 持仓数量：{len(positions)} 只",
        f"- 可用现金：¥{available_cash:,.2f}",
        f"- 总资金：¥{total_assets:,.2f}",
        f"- 观察池：{len(watchlist)} 只",
    ]
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    report_dir = PROJECT_ROOT / "data" / "reviews"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"afternoon_update_{datetime.now().strftime('%Y-%m-%d')}.md"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n✅ 下午更新已保存: {report_path}")

    try:
        from feishu_notifier import send_feishu_message

        send_feishu_message(
            title=f"🕐 下午开盘前更新 - {datetime.now().strftime('%Y-%m-%d')}",
            content=report,
            level="info",
        )
        print("✅ 飞书通知已发送")
    except Exception as exc:
        print(f"⚠️ 飞书通知发送失败: {exc}")


if __name__ == "__main__":
    main()
