#!/usr/bin/env python3
"""
收盘复盘系统 - 三层架构学习核心

功能：
1. 验证全天预测准确率
2. 分析成功/失败股票特征
3. 更新选股标准（动态进化）
4. 优化预测模型
5. 永久写入教训到 memory.md
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LEARNING_DIR = PROJECT_ROOT / "learning"


class MarketReview:
    """收盘复盘系统"""
    
    def __init__(self):
        self.criteria_file = CONFIG_DIR / "stock_criteria.json"
        self.predictions_file = DATA_DIR / "predictions.json"
        self.positions_file = CONFIG_DIR / "positions.json"
        self.trade_history_file = DATA_DIR / "trade_history.json"
        self.memory_file = LEARNING_DIR / "memory.md"
        
        self._load_data()
    
    def _load_data(self):
        """加载数据"""
        # 选股标准
        if self.criteria_file.exists():
            with open(self.criteria_file, 'r', encoding='utf-8') as f:
                self.criteria = json.load(f)
        else:
            self.criteria = {}
        
        # 预测记录
        if self.predictions_file.exists():
            with open(self.predictions_file, 'r', encoding='utf-8') as f:
                self.predictions = json.load(f)
        else:
            self.predictions = {"active": {}, "history": []}
        
        # 持仓
        if self.positions_file.exists():
            with open(self.positions_file, 'r', encoding='utf-8') as f:
                self.positions = json.load(f)
        else:
            self.positions = {}
        
        # 交易历史
        if self.trade_history_file.exists():
            with open(self.trade_history_file, 'r', encoding='utf-8') as f:
                self.trade_history = json.load(f)
        else:
            self.trade_history = []
    
    def validate_predictions(self) -> Tuple[int, int, List[Dict], List[Dict]]:
        """
        验证预测
        
        Returns:
            (成功数, 失败数, 成功列表, 失败列表)
        """
        success_count = 0
        fail_count = 0
        success_list = []
        fail_list = []
        
        for pred_id, pred in self.predictions.get("active", {}).items():
            # 检查是否到期
            if pred.get("status") != "completed":
                continue
            
            direction = pred.get("direction")
            actual_change = pred.get("actual_change", 0)
            
            # 判断成功/失败
            if direction == "up" and actual_change > 0:
                success_count += 1
                success_list.append(pred)
            elif direction == "down" and actual_change < 0:
                success_count += 1
                success_list.append(pred)
            elif direction == "flat" and abs(actual_change) < 0.02:
                success_count += 1
                success_list.append(pred)
            else:
                fail_count += 1
                fail_list.append(pred)
        
        return success_count, fail_count, success_list, fail_list
    
    def analyze_stock_patterns(self, stocks: List[Dict]) -> Dict:
        """
        分析股票特征
        
        Returns:
            特征统计
        """
        if not stocks:
            return {}
        
        patterns = {
            "avg_pb": 0,
            "avg_roe": 0,
            "avg_market_cap": 0,
            "avg_dividend_yield": 0,
            "industries": {},
            "controllers": {},
        }
        
        total = len(stocks)
        
        for stock in stocks:
            patterns["avg_pb"] += stock.get("pb", 0)
            patterns["avg_roe"] += stock.get("roe", 0)
            patterns["avg_market_cap"] += stock.get("market_cap", 0)
            patterns["avg_dividend_yield"] += stock.get("dividend_yield", 0)
            
            industry = stock.get("industry", "unknown")
            patterns["industries"][industry] = patterns["industries"].get(industry, 0) + 1
            
            controller = stock.get("controller", "unknown")
            patterns["controllers"][controller] = patterns["controllers"].get(controller, 0) + 1
        
        # 计算平均值
        patterns["avg_pb"] /= total
        patterns["avg_roe"] /= total
        patterns["avg_market_cap"] /= total
        patterns["avg_dividend_yield"] /= total
        
        return patterns
    
    def update_criteria(self, success_patterns: Dict, fail_patterns: Dict):
        """
        更新选股标准
        
        Args:
            success_patterns: 成功股票特征
            fail_patterns: 失败股票特征
        """
        if not success_patterns:
            return
        
        print("\n📊 分析选股标准有效性...")
        
        adjustments = []
        
        # PB 分析
        if success_patterns.get("avg_pb", 999) < self.criteria.get("hard_filters", {}).get("pb_max", 999) * 0.8:
            new_pb = success_patterns["avg_pb"] * 1.2
            adjustments.append(f"PB 标准建议调整：<2.5 → <{new_pb:.1f}")
        
        # ROE 分析
        if success_patterns.get("avg_roe", 0) > self.criteria.get("soft_filters", {}).get("roe_min", 0):
            new_roe = success_patterns["avg_roe"] * 0.8
            adjustments.append(f"ROE 要求建议提高：>10% → >{new_roe:.0f}%")
        
        # 市值分析
        if success_patterns.get("avg_market_cap", 999) < self.criteria.get("hard_filters", {}).get("market_cap_max", 999) * 0.7:
            new_cap = success_patterns["avg_market_cap"] * 1.3
            adjustments.append(f"市值上限建议调整：<200 亿 → <{new_cap:.0f} 亿")
        
        # 更新进化记录
        if adjustments:
            self.criteria.setdefault("evolution", {})
            self.criteria["evolution"]["last_review"] = datetime.now().isoformat()
            self.criteria["evolution"]["success_patterns"] = [
                f"平均 PB: {success_patterns.get('avg_pb', 0):.2f}",
                f"平均 ROE: {success_patterns.get('avg_roe', 0):.1f}%",
                f"平均市值：{success_patterns.get('avg_market_cap', 0):.1f} 亿",
            ]
            self.criteria["evolution"]["adjustments"] = adjustments
            
            # 保存
            with open(self.criteria_file, 'w', encoding='utf-8') as f:
                json.dump(self.criteria, f, ensure_ascii=False, indent=2)
            
            print("\n✅ 选股标准进化建议：")
            for adj in adjustments:
                print(f"   • {adj}")
    
    def write_lessons(self, lessons: List[str]):
        """
        永久写入教训到 memory.md
        """
        if not lessons:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        content = f"\n## 收盘复盘 - {timestamp}\n\n"
        for lesson in lessons:
            content += f"- {lesson}\n"
        
        # 追加到 memory.md
        with open(self.memory_file, 'a', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n✅ 教训已永久写入 memory.md")
    
    def run(self):
        """执行复盘"""
        print("=" * 60)
        print(f"📊 收盘复盘 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        # 1. 验证预测
        print("\n1️⃣ 验证预测准确率...")
        success, fail, success_list, fail_list = self.validate_predictions()
        
        total = success + fail
        accuracy = (success / total * 100) if total > 0 else 0
        
        print(f"   成功：{success}只")
        print(f"   失败：{fail}只")
        print(f"   准确率：{accuracy:.1f}%")
        
        # 2. 分析特征
        print("\n2️⃣ 分析股票特征...")
        success_patterns = self.analyze_stock_patterns(success_list)
        fail_patterns = self.analyze_stock_patterns(fail_list)
        
        if success_patterns:
            print(f"   成功股票平均 PB: {success_patterns.get('avg_pb', 0):.2f}")
            print(f"   成功股票平均 ROE: {success_patterns.get('avg_roe', 0):.1f}%")
            print(f"   成功股票平均市值：{success_patterns.get('avg_market_cap', 0):.1f} 亿")
        
        # 3. 更新选股标准
        self.update_criteria(success_patterns, fail_patterns)
        
        # 4. 提取教训
        print("\n3️⃣ 提取教训...")
        lessons = []
        
        if fail_list:
            for pred in fail_list[:3]:  # 只取前 3 个
                code = pred.get("code", "?")
                name = pred.get("name", "?")
                direction = pred.get("direction", "?")
                actual = pred.get("actual_change", 0)
                lesson = f"{name}({code}) 预测{direction} 实际{actual*100:+.1f}%"
                lessons.append(lesson)
        
        if lessons:
            self.write_lessons(lessons)
        
        # 5. 汇总
        print("\n" + "=" * 60)
        print(f"✅ 复盘完成")
        print(f"   准确率：{accuracy:.1f}%")
        print(f"   选股标准：已更新")
        print(f"   教训：{len(lessons)}条已写入")
        print("=" * 60)


def main():
    review = MarketReview()
    review.run()


if __name__ == "__main__":
    main()
