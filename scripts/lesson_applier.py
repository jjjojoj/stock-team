#!/usr/bin/env python3
"""
教训应用器

功能：
1. 读取 learning/memory.md 中的教训
2. 解析教训并转化为可执行规则
3. 更新 prediction_rules.json
4. 记录应用日志

使用方法：
    python scripts/lesson_applier.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
LEARNING_DIR = PROJECT_ROOT / "learning"
MEMORY_FILE = LEARNING_DIR / "memory.md"
RULES_FILE = LEARNING_DIR / "prediction_rules.json"
APPLY_LOG_FILE = LEARNING_DIR / "lesson_apply_log.json"


class LessonApplier:
    """教训应用器"""

    def __init__(self):
        self.lessons = []
        self.rules = {}
        self.apply_log = []

        self._load_data()

    def _load_data(self):
        """加载数据"""
        # 加载记忆文件
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            self.lessons = self._parse_lessons(content)

        # 加载规则库
        if RULES_FILE.exists():
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)

        # 加载应用日志
        if APPLY_LOG_FILE.exists():
            with open(APPLY_LOG_FILE, 'r', encoding='utf-8') as f:
                self.apply_log = json.load(f)

    def _parse_lessons(self, content: str) -> List[Dict]:
        """
        解析 memory.md 中的教训

        支持的格式：
        1. ## ❌ 失败教训
        2. ### [日期] 教训标题
        3. **关键教训**：...
        4. **改进**：...
        """
        lessons = []

        # 提取失败教训部分
        failure_section = self._extract_section(content, "## ❌ 失败教训")
        if failure_section:
            # 使用正则表达式提取具体教训
            pattern = r'###\s*\[([^\]]+)\]\s*([^\n]+)\s*(.*?)\n(?=###|##|$)'
            matches = re.findall(pattern, failure_section, re.DOTALL)

            for date, title, body in matches:
                lesson = {
                    "date": date.strip(),
                    "title": title.strip(),
                    "content": body.strip(),
                    "type": "failure"
                }

                # 提取关键教训
                key_lesson_match = re.search(r'\*\*关键教训\*\*：\s*(.+)', body)
                if key_lesson_match:
                    lesson["key_lesson"] = key_lesson_match.group(1).strip()

                # 提取改进建议
                improvement_match = re.search(r'\*\*改进\*\*：\s*(.+)', body)
                if improvement_match:
                    lesson["improvement"] = improvement_match.group(1).strip()

                lessons.append(lesson)

        # 提取关键发现（从复盘报告中）
        review_section = self._extract_section(content, "## 🚨 核心问题")
        if review_section:
            # 提取具体问题
            problems = re.findall(r'\*\*\d+\.\s*([^\*]+)\*\*\s*\n([^*]+)', review_section)
            for title, body in problems:
                lessons.append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "title": title.strip(),
                    "content": body.strip(),
                    "type": "review"
                })

        return lessons

    def _extract_section(self, content: str, section_title: str) -> str:
        """提取指定章节内容"""
        # 找到章节开始位置
        start_pos = content.find(section_title)
        if start_pos == -1:
            return ""

        # 找到下一个同级章节
        next_section_pattern = r'\n##\s+'
        match = re.search(next_section_pattern, content[start_pos + 1:])

        if match:
            end_pos = start_pos + 1 + match.start()
            return content[start_pos:end_pos]
        else:
            return content[start_pos:]

    def _convert_lesson_to_rule(self, lesson: Dict) -> Optional[Dict]:
        """
        将教训转化为规则

        映射规则：
        1. 方向预测失败 → direction_rules
        2. 幅度预测偏差 → magnitude_rules
        3. 时间判断错误 → timing_rules
        4. 置信度判断 → confidence_rules
        """
        content = lesson.get("content", "") + " " + lesson.get("key_lesson", "") + " " + lesson.get("improvement", "")

        # 生成规则ID
        lesson_id = f"lesson_{lesson.get('date', 'unknown').replace('-', '')}_{hash(content) % 1000}"

        # 判断规则类型
        rule_type = self._determine_rule_type(content)

        # 生成规则条件
        condition = self._generate_condition(content, rule_type)

        # 生成预测描述
        prediction = self._generate_prediction(content, rule_type)

        # 计算置信度调整
        confidence_boost = self._calculate_confidence_boost(content, rule_type)

        if not all([condition, prediction]):
            return None

        return {
            "condition": condition,
            "prediction": prediction,
            "confidence_boost": confidence_boost,
            "samples": 0,
            "success_rate": 0.0,
            "source": "lesson",
            "source_lesson": lesson["title"],
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "lesson_date": lesson.get("date"),
                "lesson_type": lesson.get("type")
            }
        }

    def _determine_rule_type(self, content: str) -> str:
        """根据教训内容判断规则类型"""
        content_lower = content.lower()

        # 方向预测相关
        if any(kw in content_lower for kw in ["方向", "上涨", "下跌", "看涨", "看空", "预测方向"]):
            return "direction_rules"

        # 幅度预测相关
        if any(kw in content_lower for kw in ["幅度", "涨幅", "跌幅", "目标价", "盈亏比"]):
            return "magnitude_rules"

        # 时间判断相关
        if any(kw in content_lower for kw in ["时间", "周期", "日期", "验证周期", "止损时间"]):
            return "timing_rules"

        # 置信度相关
        if any(kw in content_lower for kw in ["置信度", "果断", "观望", "谨慎"]):
            return "confidence_rules"

        # 默认为方向规则
        return "direction_rules"

    def _generate_condition(self, content: str, rule_type: str) -> Optional[str]:
        """生成规则条件"""
        content_lower = content.lower()

        # 从教训中提取关键条件
        if "周期低位" in content_lower:
            return "行业周期低位 + 企稳信号确认"
        elif "周期高位" in content_lower:
            return "行业周期高位 + 优先回避"
        elif "大盘" in content_lower and "情绪" in content_lower:
            return "大盘情绪配合（上证>0）+ 技术确认"
        elif "技术" in content_lower and "信号" in content_lower:
            return "多维度技术信号共振"
        elif "突破" in content_lower and "放量" in content_lower:
            return "突破关键技术位 + 成交量放大>1.5倍"
        elif "中性" in content_lower and "波动" in content_lower:
            return "震荡市场 + 波动范围<1%"
        elif "止损" in content_lower:
            return "亏损达到8% 立即止损"
        elif "止盈" in content_lower:
            return "盈利达到15% 分批止盈"

        # 默认条件
        return None

    def _generate_prediction(self, content: str, rule_type: str) -> Optional[str]:
        """生成预测描述"""
        content_lower = content.lower()

        if "上涨" in content_lower or "看涨" in content_lower:
            if rule_type == "direction_rules":
                return "未来5日上涨概率>60%"
            elif rule_type == "magnitude_rules":
                return "上涨幅度3-5%"
        elif "下跌" in content_lower or "看空" in content_lower:
            if rule_type == "direction_rules":
                return "未来5日下跌概率>60%"
            elif rule_type == "magnitude_rules":
                return "下跌幅度3-5%"
        elif "观望" in content_lower:
            return "保持观望，等待明确信号"
        elif "止损" in content_lower:
            return "严格止损，控制单笔亏损<8%"

        # 默认预测
        return "提高预测准确性"

    def _calculate_confidence_boost(self, content: str, rule_type: str) -> int:
        """计算置信度调整"""
        content_lower = content.lower()

        # 风险相关（降低置信度）
        if any(kw in content_lower for kw in ["风险", "失败", "错误", "教训"]):
            return -10

        # 改进相关（可能提高置信度）
        if any(kw in content_lower for kw in ["改进", "优化", "提升", "有效"]):
            return 5

        # 谨慎相关
        if any(kw in content_lower for kw in ["谨慎", "观望", "确认"]):
            return -5

        # 默认不调整
        return 0

    def apply_lessons(self) -> Dict:
        """应用教训到规则库"""
        print("=" * 60)
        print("📚 教训应用器")
        print("=" * 60)
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        stats = {
            "total_lessons": len(self.lessons),
            "applied": 0,
            "skipped": 0,
            "rules_updated": 0
        }

        print(f"📋 发现 {len(self.lessons)} 条教训")
        print()

        for lesson in self.lessons:
            print(f"\n处理: {lesson.get('title', '未知')} ({lesson.get('date', 'unknown')})")

            # 转化为规则
            rule = self._convert_lesson_to_rule(lesson)
            if not rule:
                print("  ⏭️ 跳过：无法转化为规则")
                stats["skipped"] += 1
                continue

            # 确定规则类别
            rule_type = self._determine_rule_type(lesson.get("content", ""))

            # 生成规则ID
            rule_id = f"lesson_{lesson.get('date', 'unknown').replace('-', '')}_{hash(lesson.get('title', '')) % 1000}"

            # 添加到规则库
            if rule_type not in self.rules:
                self.rules[rule_type] = {}

            # 检查是否已存在相似规则
            existing = False
            for existing_id, existing_rule in self.rules[rule_type].items():
                if existing_rule.get("condition") == rule["condition"]:
                    print(f"  ⚠️ 规则已存在: {existing_id}")
                    existing = True
                    break

            if existing:
                stats["skipped"] += 1
                continue

            # 添加新规则
            self.rules[rule_type][rule_id] = rule
            stats["applied"] += 1
            stats["rules_updated"] += 1

            print(f"  ✅ 已添加规则: {rule_id}")
            print(f"     条件: {rule['condition']}")
            print(f"     预测: {rule['prediction']}")
            print(f"     置信度调整: {rule['confidence_boost']:+d}")

            # 记录应用日志
            self.apply_log.append({
                "date": datetime.now().isoformat(),
                "lesson_title": lesson.get("title"),
                "lesson_date": lesson.get("date"),
                "rule_id": rule_id,
                "rule_type": rule_type,
                "action": "applied"
            })

        # 保存更新
        self._save_data()

        # 输出总结
        print("\n" + "=" * 60)
        print("📊 应用总结")
        print("=" * 60)
        print(f"总教训: {stats['total_lessons']}")
        print(f"✅ 已应用: {stats['applied']}")
        print(f"⏭️ 已跳过: {stats['skipped']}")
        print(f"📝 更新规则: {stats['rules_updated']} 条")
        print("=" * 60)

        return stats

    def _save_data(self):
        """保存数据"""
        # 保存规则库
        with open(RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)

        # 保存应用日志
        with open(APPLY_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.apply_log, f, ensure_ascii=False, indent=2)


def main():
    """主函数"""
    applier = LessonApplier()
    stats = applier.apply_lessons()
    return stats


if __name__ == "__main__":
    main()
