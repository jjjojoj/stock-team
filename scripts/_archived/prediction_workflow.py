#!/usr/bin/env python3
"""
预测系统自动化工作流
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from prediction_engine import PredictionEngine
from feishu_notifier import send_message

def daily_prediction_scan():
    """每日预测扫描"""
    engine = PredictionEngine()
    
    print("=" * 70)
    print("📊 每日预测扫描")
    print("=" * 70)
    
    # 1. 扫描股票池
    predictions = engine.scan_and_predict()
    
    if not predictions:
        print("未发现符合条件的股票")
        return
    
    # 2. 生成报告
    lines = [
        "📊 **今日预测扫描结果**",
        "",
        f"发现 {len(predictions)} 只潜在上涨股票:",
        ""
    ]
    
    for i, pred in enumerate(predictions[:10], 1):
        emoji = "🟢" if pred['direction'] == 'up' else "🟡"
        lines.append(f"{i}. {emoji} **{pred['name']}** ({pred['code']})")
        lines.append(f"   - 置信度: {pred['confidence']}%")
        lines.append(f"   - 理由: {', '.join(pred['reasons'])}")
        lines.append("")
    
    # 3. 添加到观察池
    added = engine.add_to_watchlist(predictions)
    lines.append(f"✅ 已添加 {added} 只股票到观察池")
    
    # 4. 发送飞书
    report = "\n".join(lines)
    send_message(report)
    
    print(report)


def weekly_verify_and_learn():
    """每周验证和学习"""
    engine = PredictionEngine()
    
    print("=" * 70)
    print("🧠 每周验证和学习")
    print("=" * 70)
    
    # 1. 验证到期预测
    result = engine.verify_predictions()
    
    # 2. 生成准确率报告
    accuracy_report = engine.get_accuracy_report()
    
    # 3. 生成学习总结
    learning_summary = engine.get_learning_summary()
    
    # 4. 发送飞书
    lines = [
        "🧠 **每周学习报告**",
        "",
        f"验证了 {result['verified']} 个预测",
        "",
        accuracy_report,
        "",
        learning_summary
    ]
    
    report = "\n".join(lines)
    send_message(report)
    
    print(report)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['scan', 'verify', 'report', 'learn'])
    
    args = parser.parse_args()
    
    engine = PredictionEngine()
    
    if args.command == 'scan':
        daily_prediction_scan()
    elif args.command == 'verify':
        weekly_verify_and_learn()
    elif args.command == 'report':
        print(engine.get_accuracy_report())
    elif args.command == 'learn':
        print(engine.get_learning_summary())
