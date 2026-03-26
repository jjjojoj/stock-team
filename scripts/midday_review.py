#!/usr/bin/env python3
"""
午盘反思系统（11:30）

目标：
1. 验证早盘预测
2. 记录午盘经验
3. 在样本和连续性满足门槛时，才小步调整长期阈值
4. 若后续表现恶化，自动回滚
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

sys.path.insert(0, str(PROJECT_ROOT))

from core.predictions import normalize_prediction_collection
from core.runtime_guardrails import (
    TaskLockedError,
    load_guardrail_config,
    load_guardrail_state,
    record_guardrail_event,
    record_guardrail_success,
    save_guardrail_state,
    task_lock,
)
from core.storage import load_json


def get_stock_price(code: str) -> float:
    """获取股票当前价（腾讯 API）"""
    try:
        secid = code.replace(".", "")
        url = f"http://qt.gtimg.cn/q={secid}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("gbk")
        if "=" in content:
            parts = content.split("=")[1].strip('"').split("~")
            if len(parts) >= 4:
                return float(parts[3]) if parts[3] else 0
    except Exception:
        pass
    return 0


def verify_predictions() -> dict:
    """验证早盘预测"""
    data = normalize_prediction_collection(
        load_json(DATA_DIR / "predictions.json", {"active": {}, "history": []})
    )

    results = {
        "verified": 0,
        "correct": 0,
        "wrong": 0,
        "details": [],
    }

    for pred in data.get("active", {}).values():
        if pred.get("status") != "active":
            continue

        code = pred.get("code")
        direction = pred.get("direction")
        created_price = float(pred.get("current_price", 0) or 0)
        current_price = get_stock_price(code)
        if current_price == 0 or created_price <= 0:
            continue

        results["verified"] += 1
        if direction == "up":
            correct = current_price > created_price
        elif direction == "down":
            correct = current_price < created_price
        else:
            change_pct = abs(current_price - created_price) / created_price * 100
            correct = change_pct < 2

        status = "✅ 正确" if correct else "❌ 错误"
        if correct:
            results["correct"] += 1
        else:
            results["wrong"] += 1

        results["details"].append(
            {
                "stock": f"{pred.get('name', '?')} ({code})",
                "direction": direction,
                "created_price": created_price,
                "current_price": current_price,
                "change": (current_price - created_price) / created_price * 100,
                "status": status,
            }
        )

    return results


def _accuracy(results: Dict) -> float:
    return round(results["correct"] / results["verified"] * 100, 2) if results["verified"] else 0.0


def _dominant_wrong_bias(results: Dict) -> Optional[str]:
    wrong_cases = [item for item in results["details"] if "❌" in item["status"]]
    directions = [item["direction"] for item in wrong_cases if item.get("direction") in {"up", "down"}]
    if not directions:
        return None
    return "up" if directions.count("up") >= directions.count("down") else "down"


def summarize_lessons(results: dict) -> list:
    """总结教训，并加上调参护栏"""
    learning_cfg = load_guardrail_config()["midday_learning"]
    lessons: List[Dict] = []
    wrong_cases = [item for item in results["details"] if "❌" in item["status"]]

    if results["verified"] < learning_cfg["min_verified_predictions"]:
        lessons.append(
            {
                "type": "info",
                "content": f"验证样本仅 {results['verified']} 个，低于自动调参门槛",
                "action": "仅记录，不调整长期参数",
                "actionable": False,
            }
        )

    if wrong_cases:
        bias = _dominant_wrong_bias(results)
        directions = [item["direction"] for item in wrong_cases if item.get("direction") in {"up", "down"}]
        bias_ratio = (directions.count(bias) / len(directions)) if bias and directions else 0.0

        if (
            results["verified"] >= learning_cfg["min_verified_predictions"]
            and len(wrong_cases) >= learning_cfg["min_wrong_cases"]
            and bias
            and bias_ratio >= learning_cfg["min_bias_ratio"]
        ):
            if bias == "up":
                lessons.append(
                    {
                        "type": "error",
                        "content": "早盘上涨判断偏乐观，错误集中在看多方向",
                        "action": "提高上涨预测置信度阈值",
                        "actionable": True,
                        "adjustment_direction": "up",
                    }
                )
            else:
                lessons.append(
                    {
                        "type": "error",
                        "content": "早盘下跌判断偏悲观，错误集中在看空方向",
                        "action": "降低上涨预测置信度阈值",
                        "actionable": True,
                        "adjustment_direction": "down",
                    }
                )
        elif not any(lesson["type"] == "info" for lesson in lessons):
            lessons.append(
                {
                    "type": "info",
                    "content": "错误案例存在，但未达到自动调参门槛",
                    "action": "仅记录，不调整长期参数",
                    "actionable": False,
                }
            )

    correct_cases = [item for item in results["details"] if "✅" in item["status"]]
    if correct_cases:
        lessons.append(
            {
                "type": "success",
                "content": f"早盘 {len(correct_cases)} 只预测正确",
                "action": "保持当前分析逻辑",
                "actionable": False,
            }
        )

    return lessons


def _append_memory_entry(results: Dict, lessons: List[Dict]) -> None:
    memory_file = PROJECT_ROOT / "learning" / "memory.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    if not memory_file.exists():
        memory_file.write_text(
            "# AI 炒股团队 - 长期记忆（HOT 层）\n\n> 出现 3 次相同模式 → 提升到 HOT 层，永久生效\n\n",
            encoding="utf-8",
        )

    entry = [
        "\n---\n",
        f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] 午盘学习 ⭐\n",
        f"\n**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"\n**验证样本**: {results['verified']} | **准确率**: {_accuracy(results):.1f}%\n\n",
    ]
    for lesson in lessons:
        emoji = "✅" if lesson["type"] == "success" else "⚠️" if lesson["type"] == "error" else "ℹ️"
        entry.append(f"{emoji} **{lesson['type'].upper()}**: {lesson['content']}\n")
        entry.append(f"   - **行动**: {lesson['action']}\n")
        entry.append(
            "   - **影响范围**: 所有未来预测（在护栏允许时才调参）\n\n"
            if lesson.get("actionable")
            else "   - **影响范围**: 仅记录，不直接调整系统参数\n\n"
        )

    with memory_file.open("a", encoding="utf-8") as handle:
        handle.write("".join(entry))


def _rollback_if_needed(config: Dict, state: Dict) -> Optional[str]:
    learning_cfg = load_guardrail_config()["midday_learning"]
    learning_state = state.setdefault("midday_learning", {"history": [], "adjustments": []})
    history = learning_state.setdefault("history", [])
    adjustments = learning_state.setdefault("adjustments", [])
    current_run_index = len(history)

    for adjustment in reversed(adjustments):
        if adjustment.get("status") != "active":
            continue
        if current_run_index < adjustment.get("evaluation_due_run", 10**9):
            continue
        post_runs = history[
            adjustment["applied_run_index"] : adjustment["applied_run_index"] + learning_cfg["rollback_window_runs"]
        ]
        if len(post_runs) < learning_cfg["rollback_window_runs"]:
            continue

        post_accuracy = mean(item.get("accuracy", 0.0) for item in post_runs)
        baseline = float(adjustment.get("baseline_accuracy", 0.0) or 0.0)
        if post_accuracy <= baseline - learning_cfg["rollback_drop_pct"]:
            config["confidence_threshold"] = adjustment["old_value"]
            config["confidence_threshold_updated"] = datetime.now().isoformat()
            config["confidence_threshold_reason"] = f"回滚 {adjustment.get('reason', 'midday learning')}"
            adjustment["status"] = "rolled_back"
            adjustment["rolled_back_at"] = datetime.now().isoformat()
            adjustment["rollback_reason"] = (
                f"连续{learning_cfg['rollback_window_runs']}次午盘后平均准确率 {post_accuracy:.1f}% "
                f"低于基线 {baseline:.1f}%"
            )
            return f"已回滚置信度阈值到 {adjustment['old_value']:.2f}"
    return None


def apply_to_future(lessons: list, results: dict):
    """记录午盘学习，并在满足护栏时小步调参"""
    learning_cfg = load_guardrail_config()["midday_learning"]
    state = load_guardrail_state()
    learning_state = state.setdefault("midday_learning", {"history": [], "adjustments": []})
    history = learning_state.setdefault("history", [])
    adjustments = learning_state.setdefault("adjustments", [])

    history.append(
        {
            "timestamp": datetime.now().isoformat(),
            "verified": results["verified"],
            "correct": results["correct"],
            "wrong": results["wrong"],
            "accuracy": _accuracy(results),
            "dominant_bias": _dominant_wrong_bias(results),
        }
    )
    learning_state["history"] = history[-30:]

    _append_memory_entry(results, lessons)

    config_file = CONFIG_DIR / "prediction_config.json"
    config = load_json(config_file, {})
    rollback_message = _rollback_if_needed(config, state)
    if rollback_message:
        print(f"↩️ {rollback_message}")

    actionable = next((lesson for lesson in lessons if lesson.get("actionable")), None)
    if actionable:
        recent_runs = learning_state["history"][-learning_cfg["consecutive_error_runs"] :]
        same_bias_runs = [
            run
            for run in recent_runs
            if run.get("dominant_bias") == actionable.get("adjustment_direction")
            and run.get("wrong", 0) >= learning_cfg["min_wrong_cases"]
        ]
        active_adjustment = any(item.get("status") == "active" for item in adjustments[-2:])
        if len(same_bias_runs) >= learning_cfg["consecutive_error_runs"] and not active_adjustment:
            current_threshold = float(config.get("confidence_threshold", 0.8) or 0.8)
            step = float(learning_cfg["adjustment_step"])
            if actionable["adjustment_direction"] == "up":
                new_threshold = min(float(learning_cfg["max_confidence_threshold"]), current_threshold + step)
            else:
                new_threshold = max(float(learning_cfg["min_confidence_threshold"]), current_threshold - step)

            if abs(new_threshold - current_threshold) >= 1e-9:
                config["confidence_threshold"] = round(new_threshold, 4)
                config["confidence_threshold_updated"] = datetime.now().isoformat()
                config["confidence_threshold_reason"] = actionable["content"]
                adjustments.append(
                    {
                        "applied_at": datetime.now().isoformat(),
                        "applied_run_index": len(learning_state["history"]),
                        "old_value": current_threshold,
                        "new_value": round(new_threshold, 4),
                        "reason": actionable["content"],
                        "baseline_accuracy": round(mean(item["accuracy"] for item in same_bias_runs), 2),
                        "evaluation_due_run": len(learning_state["history"]) + learning_cfg["rollback_window_runs"],
                        "status": "active",
                    }
                )
                print(f"📌 护栏调参：置信度阈值 {current_threshold:.2f} → {new_threshold:.2f}")
            else:
                print("📌 护栏评估后无需调整阈值")
        else:
            print("📌 已记录偏差，但未满足连续错误条件，不调整阈值")
    else:
        print("📌 本次仅记录学习结果，不调整阈值")

    with config_file.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)

    save_guardrail_state(state)

    log_file = LOG_DIR / f"learning_{datetime.now().strftime('%Y%m')}.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M')} 午盘学习\n")
        for lesson in lessons:
            handle.write(f"- {lesson['type'].upper()}: {lesson['content']}\n")
            handle.write(f"  → {lesson['action']}\n")


def send_feishu_report(results: dict, lessons: list):
    """发送午盘报告到飞书"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from feishu_notifier import send_feishu_message

        title = f"📊 午盘反思 - {datetime.now().strftime('%Y-%m-%d')}"
        message = f"""时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

预测验证
- 验证预测：{results['verified']}个
- 正确：{results['correct']}个
- 错误：{results['wrong']}个
- 准确率：{_accuracy(results):.1f}%

详情
"""
        for detail in results["details"][:5]:
            message += f"{detail['status']} {detail['stock']}: {detail['change']:+.1f}%\n"

        if lessons:
            message += "\n总结\n"
            for lesson in lessons:
                emoji = "✅" if lesson["type"] == "success" else "⚠️" if lesson["type"] == "error" else "ℹ️"
                message += f"{emoji} {lesson['content']}\n"
                message += f"   → {lesson['action']}\n"

        send_feishu_message(title=title, content=message, level="info")
    except Exception as exc:
        print(f"发送飞书通知失败：{exc}")


def main():
    try:
        with task_lock("midday_review"):
            print("=" * 60)
            print(f"📝 午盘反思 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print("=" * 60)

            print("\n1️⃣ 验证早盘预测...")
            results = verify_predictions()
            print(f"   验证：{results['verified']}个")
            print(f"   正确：{results['correct']}个")
            print(f"   错误：{results['wrong']}个")
            print(f"   准确率：{_accuracy(results):.1f}%")

            print("\n2️⃣ 总结教训...")
            lessons = summarize_lessons(results)
            for lesson in lessons:
                emoji = "✅" if lesson["type"] == "success" else "⚠️" if lesson["type"] == "error" else "ℹ️"
                print(f"   {emoji} {lesson['content']}")
                print(f"      → {lesson['action']}")

            print("\n3️⃣ 应用到未来所有预测（受护栏控制）...")
            apply_to_future(lessons, results)

            print("\n4️⃣ 发送午盘报告...")
            send_feishu_report(results, lessons)

            report_file = DATA_DIR / f"midday_review_{datetime.now().strftime('%Y%m%d')}.json"
            with report_file.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "date": datetime.now().isoformat(),
                        "results": results,
                        "lessons": lessons,
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
            print(f"\n📄 报告已保存：{report_file}")
            print("\n" + "=" * 60)
            record_guardrail_success("midday_review", f"午盘学习完成，验证 {results['verified']} 条")
    except TaskLockedError as exc:
        print(f"⚠️ {exc}")
        record_guardrail_event("midday_review", "warning", str(exc))


if __name__ == "__main__":
    main()
