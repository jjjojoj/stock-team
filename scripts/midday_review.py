#!/usr/bin/env python3
"""
午盘反思系统（11:30）

功能：
1. 验证早盘预测准确率
2. 总结：哪里对/哪里错
3. 立即应用到下午预测
4. 生成午盘报告
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
import urllib.request

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

sys.path.insert(0, str(PROJECT_ROOT))

from core.predictions import normalize_prediction_collection
from core.storage import load_json


def get_stock_price(code: str) -> float:
    """获取股票当前价（腾讯 API）"""
    try:
        secid = code.replace('.', '')
        url = f"http://qt.gtimg.cn/q={secid}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('gbk')
        if '=' in content:
            parts = content.split('=')[1].strip('"').split('~')
            if len(parts) >= 4:
                return float(parts[3]) if parts[3] else 0
    except:
        pass
    return 0


def verify_predictions() -> dict:
    """验证早盘预测"""
    data = normalize_prediction_collection(
        load_json(DATA_DIR / "predictions.json", {"active": {}, "history": []})
    )
    
    results = {
        'verified': 0,
        'correct': 0,
        'wrong': 0,
        'details': []
    }
    
    # 验证活跃预测
    for pred_id, pred in data.get('active', {}).items():
        if pred.get('status') != 'active':
            continue
        
        code = pred.get('code')
        direction = pred.get('direction')  # up/down/neutral
        target = pred.get('target_price', 0)
        created_price = pred.get('current_price', 0)
        
        # 获取当前价
        current_price = get_stock_price(code)
        if current_price == 0:
            continue
        
        results['verified'] += 1
        
        # 判断方向是否正确
        if direction == 'up':
            if current_price > created_price:
                results['correct'] += 1
                status = '✅ 正确'
            else:
                results['wrong'] += 1
                status = '❌ 错误'
        elif direction == 'down':
            if current_price < created_price:
                results['correct'] += 1
                status = '✅ 正确'
            else:
                results['wrong'] += 1
                status = '❌ 错误'
        else:  # neutral
            change_pct = abs(current_price - created_price) / created_price * 100
            if change_pct < 2:
                results['correct'] += 1
                status = '✅ 正确'
            else:
                results['wrong'] += 1
                status = '❌ 错误'
        
        name = pred.get('name', '?')
        change = (current_price - created_price) / created_price * 100
        
        results['details'].append({
            'stock': f"{name} ({code})",
            'direction': direction,
            'created_price': created_price,
            'current_price': current_price,
            'change': change,
            'status': status,
        })
    
    return results


def summarize_lessons(results: dict) -> list:
    """总结教训"""
    lessons = []
    
    # 分析错误案例
    wrong_cases = [d for d in results['details'] if '❌' in d['status']]
    
    if wrong_cases:
        # 找共同点
        directions = [c['direction'] for c in wrong_cases]
        if directions.count('up') > len(directions) / 2:
            lessons.append({
                'type': 'error',
                'content': '早盘过于乐观，上涨预测准确率低',
                'action': '下午降低上涨预测置信度阈值',
            })
        
        # 检查是否集中在某个行业
        # （简化版，实际应该分析行业）
    
    # 分析成功案例
    correct_cases = [d for d in results['details'] if '✅' in d['status']]
    if correct_cases:
        lessons.append({
            'type': 'success',
            'content': f"早盘{len(correct_cases)}只预测正确",
            'action': '保持当前分析逻辑',
        })
    
    return lessons


def apply_to_future(lessons: list):
    """
    应用到未来所有预测（永久学习）
    
    1. 写入学习记忆 (learning/memory.md)
    2. 更新规则权重 (prediction_engine.py)
    3. 调整配置 (prediction_config.json)
    """
    from datetime import datetime
    
    # 1. 写入学习记忆（HOT 层 - 永久生效）
    memory_file = PROJECT_ROOT / "learning" / "memory.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 检查文件是否存在，不存在则创建头部
    if not memory_file.exists():
        with open(memory_file, 'w', encoding='utf-8') as f:
            f.write("# AI 炒股团队 - 长期记忆（HOT 层）\n\n")
            f.write("> 出现 3 次相同模式 → 提升到 HOT 层，永久生效\n\n")
    
    memory_entry = f"\n---\n\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] 午盘学习 ⭐\n\n"
    memory_entry += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    
    for lesson in lessons:
        emoji = "✅" if lesson['type'] == 'success' else "⚠️"
        memory_entry += f"{emoji} **{lesson['type'].upper()}**: {lesson['content']}\n"
        memory_entry += f"   - **行动**: {lesson['action']}\n"
        memory_entry += f"   - **影响范围**: 所有未来预测（永久生效）\n"
        memory_entry += f"   - **应用时机**: 午盘反思 → 立即写入记忆 → 明日起生效\n\n"
    
    # 追加到记忆文件
    with open(memory_file, 'a', encoding='utf-8') as f:
        f.write(memory_entry)
    print(f"📚 已写入学习记忆（HOT 层）：{memory_file}")
    print(f"   教训数量：{len(lessons)}条")
    print(f"   影响范围：所有未来预测（永久）")
    
    # 2. 更新规则权重（简化版：调整置信度阈值）
    config_file = CONFIG_DIR / "prediction_config.json"
    config = {}
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # 根据教训调整全局参数
    for lesson in lessons:
        if lesson['type'] == 'error':
            if '过于乐观' in lesson['content'] or '降低' in lesson['action']:
                # 提高置信度阈值（永久）
                current_threshold = config.get('confidence_threshold', 0.8)
                new_threshold = min(0.9, current_threshold + 0.05)
                config['confidence_threshold'] = new_threshold
                config['confidence_threshold_updated'] = datetime.now().isoformat()
                config['confidence_threshold_reason'] = lesson['content']
                print(f"📌 永久调整：置信度阈值 {current_threshold:.2f} → {new_threshold:.2f}")
            
            elif '过于悲观' in lesson['content'] or '提高' in lesson['action']:
                # 降低置信度阈值（永久）
                current_threshold = config.get('confidence_threshold', 0.8)
                new_threshold = max(0.6, current_threshold - 0.05)
                config['confidence_threshold'] = new_threshold
                config['confidence_threshold_updated'] = datetime.now().isoformat()
                config['confidence_threshold_reason'] = lesson['content']
                print(f"📌 永久调整：置信度阈值 {current_threshold:.2f} → {new_threshold:.2f}")
    
    # 保存配置
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"📌 已更新预测配置：{config_file}")
    
    # 3. 记录到日志
    log_file = LOG_DIR / f"learning_{datetime.now().strftime('%Y%m')}.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M')} 午盘学习\n")
        for lesson in lessons:
            f.write(f"- {lesson['type'].upper()}: {lesson['content']}\n")
            f.write(f"  → {lesson['action']}\n")


def send_feishu_report(results: dict, lessons: list):
    """发送午盘报告到飞书"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from feishu_notifier import send_feishu_message

        accuracy = results['correct'] / results['verified'] * 100 if results['verified'] > 0 else 0

        title = f"📊 午盘反思 - {datetime.now().strftime('%Y-%m-%d')}"
        message = f"""时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

预测验证
- 验证预测：{results['verified']}个
- 正确：{results['correct']}个
- 错误：{results['wrong']}个
- 准确率：{accuracy:.1f}%

详情
"""
        for d in results['details'][:5]:  # 最多显示 5 个
            message += f"{d['status']} {d['stock']}: {d['change']:+.1f}%\n"

        if lessons:
            message += "\n总结\n"
            for lesson in lessons:
                emoji = "✅" if lesson['type'] == 'success' else "⚠️"
                message += f"{emoji} {lesson['content']}\n"
                message += f"   → {lesson['action']}\n"

        send_feishu_message(title=title, content=message, level='info')
    except Exception as e:
        print(f"发送飞书通知失败：{e}")


def main():
    print("=" * 60)
    print(f"📝 午盘反思 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 1. 验证预测
    print("\n1️⃣ 验证早盘预测...")
    results = verify_predictions()
    print(f"   验证：{results['verified']}个")
    print(f"   正确：{results['correct']}个")
    print(f"   错误：{results['wrong']}个")
    
    accuracy = results['correct'] / results['verified'] * 100 if results['verified'] > 0 else 0
    print(f"   准确率：{accuracy:.1f}%")
    
    # 2. 总结教训
    print("\n2️⃣ 总结教训...")
    lessons = summarize_lessons(results)
    for lesson in lessons:
        emoji = "✅" if lesson['type'] == 'success' else "⚠️"
        print(f"   {emoji} {lesson['content']}")
        print(f"      → {lesson['action']}")
    
    # 3. 应用到未来所有预测
    print("\n3️⃣ 应用到未来所有预测（永久学习）...")
    apply_to_future(lessons)
    
    # 4. 发送报告
    print("\n4️⃣ 发送午盘报告...")
    send_feishu_report(results, lessons)
    
    # 5. 保存记录
    report_file = DATA_DIR / f"midday_review_{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'date': datetime.now().isoformat(),
            'results': results,
            'lessons': lessons,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📄 报告已保存：{report_file}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
