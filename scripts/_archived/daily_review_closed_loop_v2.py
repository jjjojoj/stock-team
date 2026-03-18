#!/usr/bin/env python3
"""
每日复盘闭环系统 v2.1 (修复版)
- 修复规则 ID 匹配问题
- 正确更新规则权重
- 正确更新验证池样本
"""

import sys
import os
import json
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
ACCURACY_FILE = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
RULES_FILE = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
VALIDATION_POOL_FILE = os.path.join(PROJECT_ROOT, "learning", "rule_validation_pool.json")
MEMORY_FILE = os.path.join(PROJECT_ROOT, "learning", "memory.md")
REVIEW_DIR = os.path.join(PROJECT_ROOT, "data", "reviews")


class ClosedLoopReview:
    """复盘闭环系统 v2.1"""
    
    # 规则映射：提取的规则ID → 规则库中的规则ID
    RULE_MAPPING = {
        "industry_cycle_low": ["industry_cycle_up"],
        "industry_cycle_high": ["industry_cycle_down"],
        "positive_signals": ["rsi_oversold", "macd_golden_cross", "break_ma20", "volume_surge"],
        "news_positive": ["positive_news"],
        "news_negative": [],
        "state_owned": ["low_pe", "high_roe"],  # 央企通常对应基本面
        "cycle_bottom_fishing": ["industry_cycle_up"],
        "default": []
    }
    
    def __init__(self):
        self._ensure_dirs()
        self.predictions = self._load_json(PREDICTIONS_FILE, {"active": {}, "history": []})
        self.accuracy = self._load_json(ACCURACY_FILE, self._init_accuracy())
        self.rules = self._load_json(RULES_FILE, {})
        self.validation_pool = self._load_json(VALIDATION_POOL_FILE, {})
        
    def _ensure_dirs(self):
        os.makedirs(REVIEW_DIR, exist_ok=True)
        
    def _load_json(self, path: str, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    
    def _save_json(self, path: str, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _init_accuracy(self) -> Dict:
        """初始化准确率统计结构"""
        return {
            "total_predictions": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "by_rule": {},
            "by_stock": {},
            "by_direction": {
                "up": {"total": 0, "correct": 0},
                "down": {"total": 0, "correct": 0},
                "neutral": {"total": 0, "correct": 0}
            },
            "by_date": {},
            "last_updated": None
        }
    
    def _get_current_price(self, code: str) -> Optional[float]:
        """获取当前价格"""
        try:
            stock_code = code.replace(".", "")
            if code.startswith("sh"):
                stock_code = "sh" + code.split(".")[1]
            else:
                stock_code = "sz" + code.split(".")[1]
            
            url = f"http://qt.gtimg.cn/q={stock_code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk")
            
            if "~" in text:
                parts = text.split("~")
                return float(parts[3])
        except Exception as e:
            print(f"  ⚠️ 获取 {code} 价格失败: {e}")
        
        return None
    
    def _extract_rules_from_prediction(self, pred: Dict) -> List[str]:
        """从预测中提取使用的规则（返回规则库中的规则ID列表）"""
        matched_rules = []
        
        signals = pred.get("signals", {})
        reasons = pred.get("reasons", [])
        
        # 1. 检测行业周期规则
        cycle = signals.get("industry_cycle", "medium")
        if cycle == "low":
            matched_rules.extend(self.RULE_MAPPING.get("industry_cycle_low", []))
        elif cycle == "high":
            matched_rules.extend(self.RULE_MAPPING.get("industry_cycle_high", []))
        
        # 2. 检测技术面规则
        if signals.get("positive", 0) > signals.get("negative", 0):
            matched_rules.extend(self.RULE_MAPPING.get("positive_signals", []))
        
        # 3. 检测情绪规则
        sentiment = signals.get("news_sentiment", "neutral")
        if sentiment == "positive":
            matched_rules.extend(self.RULE_MAPPING.get("news_positive", []))
        
        # 4. 从 reasons 检测
        for reason in reasons:
            if "央企" in reason or "实控人" in reason:
                matched_rules.extend(self.RULE_MAPPING.get("state_owned", []))
        
        # 5. 如果没有匹配到规则，使用默认
        if not matched_rules:
            matched_rules = ["low_pe", "high_roe"]  # 默认基本面规则
        
        return matched_rules
    
    def verify_all_predictions(self) -> Dict:
        """验证所有活跃预测并更新闭环"""
        print("=" * 70)
        print("📊 复盘闭环系统 v2.1 (修复版)")
        print("=" * 70)
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        active = self.predictions["active"]
        results = {
            "verified": 0,
            "pending": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0
        }
        
        # 需要验证的预测（创建超过1小时的）
        to_verify = []
        for pred_id, pred in active.items():
            created = datetime.fromisoformat(pred["created_at"])
            age_hours = (datetime.now() - created).total_seconds() / 3600
            if age_hours > 1:
                to_verify.append((pred_id, pred))
        
        print(f"📋 待验证预测: {len(to_verify)} 个")
        print()
        
        for pred_id, pred in to_verify:
            current_price = self._get_current_price(pred["code"])
            
            if current_price is None:
                print(f"  ⏭️ {pred['name']}: 价格获取失败，跳过")
                results["pending"] += 1
                continue
            
            # 计算结果
            direction = pred["direction"]
            start_price = pred["current_price"]
            target_price = pred["target_price"]
            price_change = (current_price / start_price - 1) * 100
            
            # 判断正确性
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
            else:  # neutral
                if abs(price_change) < 2:
                    correct = True
                elif abs(price_change) < 5:
                    partial = True
            
            # 更新预测状态
            pred["status"] = "verified"
            pred["result"] = {
                "verified_at": datetime.now().isoformat(),
                "final_price": current_price,
                "price_change_pct": round(price_change, 2),
                "correct": correct,
                "partial": partial
            }
            
            # 移动到历史
            self.predictions["history"].append(pred)
            del self.predictions["active"][pred_id]
            
            # 更新统计
            results["verified"] += 1
            if correct:
                results["correct"] += 1
                status = "✅"
            elif partial:
                results["partial"] += 1
                status = "🔶"
            else:
                results["wrong"] += 1
                status = "❌"
            
            print(f"  {status} {pred['name']:8s} {direction:7s} {price_change:+6.2f}% (目标: {target_price:.2f})")
            
            # 【闭环核心1】更新准确率统计
            self._update_accuracy(pred, correct, partial)
            
            # 【闭环核心2】更新规则权重（重点修复）
            self._update_rule_weights(pred, correct, partial)
        
        # 保存所有更新
        self._save_json(PREDICTIONS_FILE, self.predictions)
        self._save_json(ACCURACY_FILE, self.accuracy)
        self._save