#!/usr/bin/env python3
"""
预测系统
- 记录预测（方向/目标价/置信度/理由/时间）
- 持续监控（新闻/政策触发重新评估）
- 验证复盘（收盘后验证，记录对错）
- 学习提升（从失败中提取规则）
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
NEWS_DIGEST_FILE = os.path.join(PROJECT_ROOT, "data", "news_digest.json")
LEARNING_DIR = os.path.join(PROJECT_ROOT, "learning")


class PredictionSystem:
    """预测系统"""
    
    def __init__(self):
        self._ensure_dirs()
        self.predictions = self._load_predictions()
    
    def _ensure_dirs(self):
        os.makedirs(os.path.dirname(PREDICTIONS_FILE), exist_ok=True)
        os.makedirs(LEARNING_DIR, exist_ok=True)
    
    def _load_predictions(self) -> Dict:
        """加载预测记录"""
        if os.path.exists(PREDICTIONS_FILE):
            with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"active": {}, "history": []}
    
    def _save_predictions(self):
        """保存预测记录"""
        with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.predictions, f, ensure_ascii=False, indent=2)
    
    def make_prediction(self, prediction: Dict) -> str:
        """
        创建预测
        
        Args:
            prediction: {
                "code": "sh.600459",
                "name": "贵研铂业",
                "direction": "up",  # up/down/neutral
                "target_price": 28.00,
                "current_price": 26.27,
                "confidence": 75,  # 0-100
                "timeframe": "1周",  # 1周/1月
                "reasons": [
                    "美伊冲突升级，战略金属涨价预期",
                    "技术面超跌反弹",
                ],
                "risks": [
                    "战争快速结束可能回调",
                ],
            }
        
        Returns:
            prediction_id
        """
        prediction_id = f"{prediction['code']}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        prediction_record = {
            "id": prediction_id,
            "created_at": datetime.now().isoformat(),
            **prediction,
            "status": "active",  # active/verified/expired
            "updates": [],  # 后续更新记录
            "result": None,  # 验证后填写
            "analysis": None,  # 复盘分析
        }
        
        self.predictions["active"][prediction_id] = prediction_record
        self._save_predictions()
        
        print(f"✅ 预测已记录: {prediction['name']}")
        print(f"   方向: {'↗ 看多' if prediction['direction'] == 'up' else '↘ 看空' if prediction['direction'] == 'down' else '→ 观望'}")
        print(f"   目标价: ¥{prediction['target_price']}")
        print(f"   置信度: {prediction['confidence']}%")
        print(f"   周期: {prediction['timeframe']}")
        
        return prediction_id
    
    def update_prediction(self, prediction_id: str, update: Dict):
        """
        更新预测（基于新信息）
        
        Args:
            prediction_id: 预测ID
            update: {
                "type": "news/policy/event",
                "content": "美伊战争升级",
                "impact": "positive/negative/neutral",
                "confidence_change": +10,  # 置信度变化
                "new_target": 29.00,  # 新目标价（可选）
                "reason": "战争推高金属价格",
            }
        """
        if prediction_id not in self.predictions["active"]:
            print(f"❌ 预测不存在: {prediction_id}")
            return
        
        pred = self.predictions["active"][prediction_id]
        
        # 记录更新
        update_record = {
            "time": datetime.now().isoformat(),
            **update,
        }
        pred["updates"].append(update_record)
        
        # 更新置信度
        if "confidence_change" in update:
            pred["confidence"] = max(0, min(100, pred["confidence"] + update["confidence_change"]))
        
        # 更新目标价
        if "new_target" in update:
            pred["target_price"] = update["new_target"]
        
        # 如果置信度变化超过20%，标记为需要关注
        if abs(update.get("confidence_change", 0)) >= 20:
            pred["needs_attention"] = True
        
        self._save_predictions()
        
        print(f"🔄 预测已更新: {pred['name']}")
        print(f"   新信息: {update['content']}")
        print(f"   影响: {update['impact']}")
        print(f"   新置信度: {pred['confidence']}%")
    
    def verify_predictions(self):
        """
        验证所有活跃预测（收盘后调用）
        """
        verified = []
        
        for pred_id, pred in list(self.predictions["active"].items()):
            # 检查是否到期
            created = datetime.fromisoformat(pred["created_at"])
            timeframe_days = 7 if pred["timeframe"] == "1周" else 30
            expiry = created + timedelta(days=timeframe_days)
            
            if datetime.now() < expiry:
                continue  # 未到期，跳过
            
            # 获取当前价格
            current_price = self._get_current_price(pred["code"])
            if current_price is None:
                continue
            
            # 计算结果
            price_change_pct = (current_price / pred["current_price"] - 1) * 100
            
            # 判断预测是否正确
            if pred["direction"] == "up":
                correct = current_price >= pred["target_price"]
                partial = current_price > pred["current_price"] and not correct
            elif pred["direction"] == "down":
                correct = current_price <= pred["target_price"]
                partial = current_price < pred["current_price"] and not correct
            else:  # neutral
                correct = abs(price_change_pct) < 5
                partial = False
            
            # 记录结果
            result = {
                "verified_at": datetime.now().isoformat(),
                "final_price": current_price,
                "price_change_pct": round(price_change_pct, 2),
                "correct": correct,
                "partial": partial,
            }
            
            pred["result"] = result
            pred["status"] = "verified"
            
            # 移动到历史
            self.predictions["history"].append(pred)
            del self.predictions["active"][pred_id]
            
            verified.append({
                "name": pred["name"],
                "direction": pred["direction"],
                "target": pred["target_price"],
                "final": current_price,
                "correct": correct,
                "partial": partial,
            })
            
            print(f"\n{'✅' if correct else '🔶' if partial else '❌'} {pred['name']}")
            print(f"   预测: {pred['direction']} → ¥{pred['target_price']}")
            print(f"   实际: ¥{current_price} ({price_change_pct:+.2f}%)")
            print(f"   结果: {'正确' if correct else '部分正确' if partial else '错误'}")
        
        self._save_predictions()
        
        return verified
    
    def analyze_failure(self, prediction_id: str, analysis: Dict):
        """
        分析失败原因（复盘）
        
        Args:
            prediction_id: 预测ID
            analysis: {
                "failure_reasons": [
                    "忽视了XX政策的影响",
                    "高估了XX事件的持续性",
                ],
                "lessons": [
                    "以后遇到XX情况要更加谨慎",
                ],
                "rule_suggestions": [
                    "政策落地前不押注",
                ],
            }
        """
        # 找到历史预测
        pred = None
        for p in self.predictions["history"]:
            if p["id"] == prediction_id:
                pred = p
                break
        
        if pred is None:
            print(f"❌ 找不到预测: {prediction_id}")
            return
        
        # 记录分析
        pred["analysis"] = {
            "analyzed_at": datetime.now().isoformat(),
            **analysis,
        }
        self._save_predictions()
        
        # 提取规则到学习引擎
        self._extract_rules(analysis)
        
        print(f"📝 复盘完成: {pred['name']}")
        print(f"   失败原因: {len(analysis.get('failure_reasons', []))}条")
        print(f"   提取规则: {len(analysis.get('rule_suggestions', []))}条")
    
    def _extract_rules(self, analysis: Dict):
        """提取规则到学习引擎"""
        rules_file = os.path.join(LEARNING_DIR, "extracted_rules.md")
        
        existing = ""
        if os.path.exists(rules_file):
            with open(rules_file, 'r', encoding='utf-8') as f:
                existing = f.read()
        
        new_rules = analysis.get("rule_suggestions", [])
        if not new_rules:
            return
        
        content = f"\n## [{datetime.now().strftime('%Y-%m-%d')}]\n"
        for rule in new_rules:
            content += f"- [ ] {rule}\n"
        
        content += "\n---\n"
        
        with open(rules_file, 'w', encoding='utf-8') as f:
            f.write(content + existing)
        
        print(f"   规则已保存到: {rules_file}")
    
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
            print(f"获取价格失败: {e}")
        
        return None
    
    def get_active_predictions(self) -> List[Dict]:
        """获取所有活跃预测"""
        return list(self.predictions["active"].values())
    
    def get_prediction_stats(self) -> Dict:
        """获取预测统计"""
        history = self.predictions["history"]
        
        if not history:
            return {"total": 0, "correct": 0, "partial": 0, "wrong": 0, "accuracy": 0}
        
        correct = sum(1 for p in history if p.get("result", {}).get("correct", False))
        partial = sum(1 for p in history if p.get("result", {}).get("partial", False))
        wrong = len(history) - correct - partial
        
        return {
            "total": len(history),
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "accuracy": round(correct / len(history) * 100, 1) if history else 0,
        }
    
    def daily_brief(self) -> str:
        """生成每日预测简报"""
        active = self.get_active_predictions()
        stats = self.get_prediction_stats()
        
        brief = f"📊 预测系统简报 ({datetime.now().strftime('%Y-%m-%d')})\n"
        brief += "=" * 40 + "\n\n"
        
        brief += f"📈 历史准确率: {stats['accuracy']}% ({stats['correct']}/{stats['total']})\n\n"
        
        if active:
            brief += f"🎯 活跃预测 ({len(active)}个):\n"
            for pred in active:
                direction_icon = "↗" if pred["direction"] == "up" else "↘" if pred["direction"] == "down" else "→"
                brief += f"\n【{pred['name']}】{direction_icon}\n"
                brief += f"  目标: ¥{pred['target_price']} | 置信度: {pred['confidence']}%\n"
                brief += f"  周期: {pred['timeframe']}\n"
                
                if pred.get("updates"):
                    brief += f"  更新次数: {len(pred['updates'])}\n"
        else:
            brief += "暂无活跃预测\n"
        
        return brief


def main():
    if len(sys.argv) < 2:
        print("预测系统")
        print("\n用法:")
        print("  python3 prediction_system.py brief          # 每日简报")
        print("  python3 prediction_system.py verify         # 验证到期预测")
        print("  python3 prediction_system.py stats          # 统计数据")
        print("  python3 prediction_system.py verify           # 测试创建预测")
        sys.exit(1)
    
    command = sys.argv[1]
    system = PredictionSystem()
    
    if command == "brief":
        print(system.daily_brief())
    
    elif command == "verify":
        verified = system.verify_predictions()
        print(f"\n验证完成: {len(verified)}个预测")
    
    elif command == "stats":
        stats = system.get_prediction_stats()
        print(f"预测统计:")
        print(f"  总数: {stats['total']}")
        print(f"  正确: {stats['correct']}")
        print(f"  部分正确: {stats['partial']}")
        print(f"  错误: {stats['wrong']}")
        print(f"  准确率: {stats['accuracy']}%")
    
    elif command == "verify":
        # 测试创建预测
        prediction = {
            "code": "sh.600459",
            "name": "贵研铂业",
            "direction": "up",
            "target_price": 28.00,
            "current_price": 26.27,
            "confidence": 70,
            "timeframe": "1周",
            "reasons": [
                "美伊冲突升级，战略金属涨价预期",
                "技术面超跌",
            ],
            "risks": [
                "战争快速结束可能回调",
            ],
        }
        system.make_prediction(prediction)


if __name__ == "__main__":
    main()
