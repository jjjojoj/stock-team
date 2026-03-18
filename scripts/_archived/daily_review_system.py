from pathlib import Path
#!/usr/bin/env python3
"""
每日复盘系统
- 验证预测
- 分析失败原因
- 生成复盘报告
- 提取学习规则
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")
REVIEW_DIR = os.path.join(PROJECT_ROOT, "data", "reviews")
LEARNING_DIR = os.path.join(PROJECT_ROOT, "learning")


class DailyReview:
    """每日复盘"""
    
    def __init__(self):
        self._ensure_dirs()
        self.predictions = self._load_predictions()
    
    def _ensure_dirs(self):
        os.makedirs(REVIEW_DIR, exist_ok=True)
        os.makedirs(LEARNING_DIR, exist_ok=True)
    
    def _load_predictions(self) -> Dict:
        if os.path.exists(PREDICTIONS_FILE):
            with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"active": {}, "history": []}
    
    def _save_predictions(self):
        with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.predictions, f, ensure_ascii=False, indent=2)
    
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
    
    def check_predictions(self) -> Dict:
        """
        检查所有活跃预测的当前状态（不验证，只是检查）
        """
        active = self.predictions["active"]
        results = []
        
        for pred_id, pred in active.items():
            current_price = self._get_current_price(pred["code"])
            
            if current_price is None:
                continue
            
            # 计算距离目标还有多少
            if pred["direction"] == "up":
                progress = (current_price - pred["current_price"]) / (pred["target_price"] - pred["current_price"]) * 100
                price_change = (current_price / pred["current_price"] - 1) * 100
            elif pred["direction"] == "down":
                progress = (pred["current_price"] - current_price) / (pred["current_price"] - pred["target_price"]) * 100
                price_change = (current_price / pred["current_price"] - 1) * 100
            else:
                progress = 0
                price_change = 0
            
            # 判断当前状态
            if pred["direction"] == "up":
                if current_price >= pred["target_price"]:
                    status = "✅ 已达标"
                elif price_change > 0:
                    status = "📈 方向正确"
                else:
                    status = "📉 方向错误"
            elif pred["direction"] == "down":
                if current_price <= pred["target_price"]:
                    status = "✅ 已达标"
                elif price_change < 0:
                    status = "📈 方向正确"
                else:
                    status = "📉 方向错误"
            else:
                status = "→ 观望"
            
            results.append({
                "id": pred_id,
                "name": pred["name"],
                "direction": pred["direction"],
                "current_price": current_price,
                "target_price": pred["target_price"],
                "start_price": pred["current_price"],
                "price_change": round(price_change, 2),
                "progress": round(progress, 1),
                "confidence": pred["confidence"],
                "status": status,
                "updates_count": len(pred.get("updates", [])),
            })
        
        return {
            "time": datetime.now().isoformat(),
            "predictions": results,
        }
    
    def verify_expired_predictions(self) -> List[Dict]:
        """
        验证已到期的预测
        """
        verified = []
        
        for pred_id, pred in list(self.predictions["active"].items()):
            # 检查是否到期
            created = datetime.fromisoformat(pred["created_at"])
            timeframe_days = 7 if pred["timeframe"] == "1周" else 30
            expiry = created + timedelta(days=timeframe_days)
            
            if datetime.now() < expiry:
                continue  # 未到期
            
            # 获取最终价格
            final_price = self._get_current_price(pred["code"])
            if final_price is None:
                continue
            
            # 计算结果
            price_change_pct = (final_price / pred["current_price"] - 1) * 100
            
            # 判断预测是否正确
            if pred["direction"] == "up":
                correct = final_price >= pred["target_price"]
                partial = final_price > pred["current_price"] and not correct
            elif pred["direction"] == "down":
                correct = final_price <= pred["target_price"]
                partial = final_price < pred["current_price"] and not correct
            else:
                correct = abs(price_change_pct) < 5
                partial = False
            
            # 记录结果
            result = {
                "verified_at": datetime.now().isoformat(),
                "final_price": final_price,
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
                "id": pred_id,
                "name": pred["name"],
                "direction": pred["direction"],
                "target": pred["target_price"],
                "start": pred["current_price"],
                "final": final_price,
                "change": round(price_change_pct, 2),
                "correct": correct,
                "partial": partial,
                "reasons": pred.get("reasons", []),
                "updates": pred.get("updates", []),
            })
        
        self._save_predictions()
        
        # 记录验证结果到学习系统（2026-03-07 新增）
        self._record_verification_learning(verified)
        
        return verified
    
    def _record_verification_learning(self, verified: List[Dict]):
        """
        记录预测验证结果到学习系统（2026-03-07 新增）
        
        功能：
        1. 记录验证结果到 daily_learning_log.json
        2. 分析成功/失败模式
        3. 提取教训 → memory.md
        """
        import json
        from datetime import datetime
        
        learning_log_file = Path(LEARNING_DIR) / "daily_learning_log.json"
        
        # 准备验证记录
        verification_record = {
            "date": datetime.now().isoformat(),
            "type": "prediction_verification",
            "total_verified": len(verified),
            "correct": sum(1 for v in verified if v.get("correct")),
            "partial": sum(1 for v in verified if v.get("partial")),
            "incorrect": sum(1 for v in verified if not v.get("correct") and not v.get("partial")),
            "details": []
        }
        
        # 记录每个预测的详情
        for v in verified:
            verification_record["details"].append({
                "name": v.get("name"),
                "code": v.get("code", ""),
                "direction": v.get("direction"),
                "change": v.get("change"),
                "correct": v.get("correct"),
                "reasons": v.get("reasons", []),
                "updates_count": len(v.get("updates", []))
            })
        
        # 读取现有日志
        logs = []
        if os.path.exists(learning_log_file):
            with open(learning_log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(verification_record)
        
        # 只保留最近 50 条
        if len(logs) > 50:
            logs = logs[-50:]
        
        with open(learning_log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 预测验证记录已保存：{verification_record['correct']}/{verification_record['total_verified']} 正确")
    
    def generate_review_report(self) -> str:
        """
        生成每日复盘报告
        """
        # 检查当前预测状态
        status = self.check_predictions()
        
        # 验证到期预测
        verified = self.verify_expired_predictions()
        
        # 统计历史准确率
        history = self.predictions["history"]
        total = len(history)
        correct = sum(1 for p in history if p.get("result", {}).get("correct", False))
        partial = sum(1 for p in history if p.get("result", {}).get("partial", False))
        accuracy = round(correct / total * 100, 1) if total > 0 else 0
        
        # 生成报告
        report = f"# 每日复盘报告\n\n"
        report += f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        
        report += f"## 📊 预测准确率\n\n"
        report += f"- 总预测数: {total}\n"
        report += f"- 正确: {correct}\n"
        report += f"- 部分正确: {partial}\n"
        report += f"- 准确率: **{accuracy}%**\n\n"
        
        if verified:
            report += f"## ✅ 今日验证结果\n\n"
            for v in verified:
                icon = "✅" if v["correct"] else "🔶" if v["partial"] else "❌"
                direction = "↗" if v["direction"] == "up" else "↘" if v["direction"] == "down" else "→"
                report += f"### {icon} {v['name']}\n\n"
                report += f"- 预测方向: {direction} 目标 ¥{v['target']}\n"
                report += f"- 起始价格: ¥{v['start']}\n"
                report += f"- 最终价格: ¥{v['final']} ({v['change']:+.2f}%)\n"
                report += f"- 结果: {'正确' if v['correct'] else '部分正确' if v['partial'] else '错误'}\n"
                
                if v.get("reasons"):
                    report += f"\n**原始理由**:\n"
                    for r in v["reasons"]:
                        report += f"- {r}\n"
                
                if v.get("updates"):
                    report += f"\n**预测更新** ({len(v['updates'])}次):\n"
                    for u in v["updates"]:
                        report += f"- {u.get('content', '')} ({u.get('confidence_change', 0):+}%)\n"
                
                report += "\n---\n\n"
        
        if status["predictions"]:
            report += f"## 🎯 活跃预测状态\n\n"
            report += "| 股票 | 方向 | 现价 | 目标 | 涨跌 | 进度 | 状态 |\n"
            report += "|------|------|------|------|------|------|------|\n"
            
            for p in status["predictions"]:
                direction = "↗" if p["direction"] == "up" else "↘" if p["direction"] == "down" else "→"
                report += f"| {p['name']} | {direction} | ¥{p['current_price']:.2f} | ¥{p['target_price']:.2f} | {p['price_change']:+.2f}% | {p['progress']:.1f}% | {p['status']} |\n"
            
            report += "\n"
        
        # 保存报告
        report_file = os.path.join(REVIEW_DIR, f"review_{datetime.now().strftime('%Y%m%d')}.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        return report
    
    def analyze_failures(self):
        """
        分析失败预测（需要 AI 辅助）
        """
        failures = [
            p for p in self.predictions["history"]
            if p.get("result") and not p["result"].get("correct") and not p["result"].get("partial")
        ]
        
        if not failures:
            print("暂无失败预测需要分析")
            return
        
        print(f"发现 {len(failures)} 个失败预测需要分析:\n")
        
        for f in failures:
            if f.get("analysis"):
                continue  # 已分析过
            
            print(f"❌ {f['name']}")
            print(f"   预测: {f['direction']} → ¥{f['target_price']}")
            print(f"   实际: ¥{f['result']['final_price']} ({f['result']['price_change_pct']:+.2f}%)")
            print(f"   原始理由: {f.get('reasons', [])}")
            print(f"   更新记录: {len(f.get('updates', []))} 次")
            print()
        
        print("请使用 analyze_failure <prediction_id> 分析具体失败原因")


def main():
    if len(sys.argv) < 2:
        print("每日复盘系统")
        print("\n用法:")
        print("  python3 daily_review_system.py check      # 检查预测状态")
        print("  python3 daily_review_system.py verify     # 验证到期预测")
        print("  python3 daily_review_system.py report     # 生成复盘报告")
        print("  python3 daily_review_system.py failures   # 查看失败预测")
        sys.exit(1)
    
    command = sys.argv[1]
    review = DailyReview()
    
    if command == "check":
        status = review.check_predictions()
        print(f"活跃预测: {len(status['predictions'])}个\n")
        
        for p in status["predictions"]:
            direction = "↗" if p["direction"] == "up" else "↘"
            print(f"{p['name']}: ¥{p['current_price']:.2f} | 目标 ¥{p['target_price']:.2f} | {p['price_change']:+.2f}% | {p['status']}")
    
    elif command == "verify":
        verified = review.verify_expired_predictions()
        print(f"验证完成: {len(verified)}个预测\n")
        
        for v in verified:
            icon = "✅" if v["correct"] else "🔶" if v["partial"] else "❌"
            print(f"{icon} {v['name']}: {v['change']:+.2f}%")
    
    elif command == "report":
        report = review.generate_review_report()
        print(report)
        print(f"\n报告已保存到: {REVIEW_DIR}")
    
    elif command == "failures":
        review.analyze_failures()


if __name__ == "__main__":
    main()
