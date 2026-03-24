#!/usr/bin/env python3
"""
股票预测引擎 - 自我进化系统

功能：
1. 扫描股票池，预测哪些股票可能涨
2. 高置信度（≥80%）自动买入
3. 验证预测结果
计算准确率
4. 总结成功/失败原因，优化预测框架

学习循环：
预测 → 观察 → 验证 → 总结 → 优化 → 预测
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import urllib.request

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import load_rules, load_watchlist, save_rules, save_watchlist

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
LEARNING_DIR = PROJECT_ROOT / "learning"

# ============================================================
# 预测规则库（可学习的规则）
# ============================================================

PREDICTION_RULES = {
    # 技术指标规则
    "tech_rules": {
        "rsi_oversold": {
            "condition": "RSI < 30",
            "prediction": "反弹",
            "weight": 0.15,
            "success_rate": 0.0,
            "samples": 0
        },
        "macd_golden_cross": {
            "condition": "MACD金叉",
            "prediction": "上涨",
            "weight": 0.20,
            "success_rate": 0.0,
            "samples": 0
        },
        "break_ma20": {
            "condition": "突破20日均线",
            "prediction": "上涨",
            "weight": 0.18,
            "success_rate": 0.0,
            "samples": 0
        },
        "volume_surge": {
            "condition": "成交量放大>2倍",
            "prediction": "启动",
            "weight": 0.15,
            "success_rate": 0.0,
            "samples": 0
        }
    },
    
    # 基本面规则
    "fundamental_rules": {
        "low_pe": {
            "condition": "PE < 行业平均PE * 0.7",
            "prediction": "低估",
            "weight": 0.12,
            "success_rate": 0.0,
            "samples": 0
        },
        "high_roe": {
            "condition": "ROE > 15%",
            "prediction": "优质",
            "weight": 0.10,
            "success_rate": 0.0,
            "samples": 0
        }
    },
    
    # 事件驱动规则
    "event_rules": {
        "geopolitical_war": {
            "condition": "战争/冲突",
            "prediction": "油气/黄金/军工上涨",
            "weight": 0.25,
            "success_rate": 0.0,
            "samples": 0
        },
        "policy_support": {
            "condition": "政策利好",
            "prediction": "相关板块上涨",
            "weight": 0.22,
            "success_rate": 0.0,
            "samples": 0
        },
        "industry_cycle_up": {
            "condition": "行业周期底部反转",
            "prediction": "板块上涨",
            "weight": 0.20,
            "success_rate": 0.0,
            "samples": 0
        }
    },
    
    # 新闻情绪规则
    "sentiment_rules": {
        "positive_news": {
            "condition": "正面新闻 > 3条",
            "prediction": "上涨",
            "weight": 0.10,
            "success_rate": 0.0,
            "samples": 0
        }
    }
}


class PredictionEngine:
    """股票预测引擎"""
    
    def __init__(self):
        self.rules_file = LEARNING_DIR / "prediction_rules.json"
        self.predictions_file = DATA_DIR / "predictions.json"
        self.watchlist_file = CONFIG_DIR / "watchlist.json"
        self.accuracy_file = LEARNING_DIR / "accuracy_stats.json"
        
        self._ensure_dirs()
        self._load_rules()
        self._load_accuracy()
    
    def _ensure_dirs(self):
        """确保目录存在"""
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_rules(self):
        """加载预测规则"""
        self.rules = load_rules(PREDICTION_RULES)
        if not self.rules:
            self.rules = PREDICTION_RULES
            self._save_rules()

    def _save_rules(self):
        """保存规则"""
        save_rules(self.rules)
    
    def _load_accuracy(self):
        """加载准确率统计"""
        if self.accuracy_file.exists():
            with open(self.accuracy_file, 'r', encoding='utf-8') as f:
                self.accuracy = json.load(f)
        else:
            self.accuracy = {
                "total_predictions": 0,
                "correct": 0,
                "partial": 0,
                "wrong": 0,
                "by_rule": {},
                "by_stock": {}
            }
            self._save_accuracy()
    
    def _save_accuracy(self):
        """保存准确率统计"""
        with open(self.accuracy_file, 'w', encoding='utf-8') as f:
                json.dump(self.accuracy, f, ensure_ascii=False, indent=2)
    
    def scan_and_predict(self, stock_pool: List[Dict]) -> List[Dict]:
        """
        扫描股票池，预测哪些可能涨
        
        Returns:
            预测结果列表
        """
        print(f"开始扫描 {len(stock_pool)} 只股票...")
        
        # 加载学习记忆（2026-03-07 新增）
        learning_memory = self._load_learning_memory()
        print(f"已加载 {len(learning_memory.get('lessons', []))} 条学习教训")
        
        predictions = []
        
        for stock in stock_pool:
            code = stock.get('code')
            name = stock.get('name')
            
            if not code or not name:
                continue
            
            # 获取股票数据
            stock_data = self._get_stock_data(code)
            if not stock_data:
                continue
            
            # 应用规则，计算综合得分（包含学习记忆）
            score, matched_rules, reasons = self._apply_rules(stock, stock_data, learning_memory)
            
            # 只保留得分较高的股票
            if score >= 0.6:
                prediction = {
                    "code": code,
                    "name": name,
                    "industry": stock.get('industry', ''),
                    "score": score,
                    "direction": "up" if score >= 0.7 else "neutral",
                    "confidence": int(score * 100),
                    "matched_rules": matched_rules,
                    "reasons": reasons,
                    "current_price": stock_data.get('price', 0),
                    "predicted_at": datetime.now().isoformat(),
                    "timeframe": "1周",
                    "status": "watching"
                }
                predictions.append(prediction)
        
        # 按得分排序
        predictions.sort(key=lambda x: x['score'], reverse=True)
        
        return predictions
    
    def _load_learning_memory(self) -> Dict:
        """
        加载学习记忆（2026-03-07 新增）
        
        从 learning/memory.md 中提取历史教训和规则
        应用到预测逻辑中
        """
        memory_file = LEARNING_DIR / "memory.md"
        
        learning_memory = {
            "lessons": [],
            "rules": [],
            "adjustments": {}
        }
        
        if not memory_file.exists():
            return learning_memory
        
        with open(memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取教训（从"失败教训"部分）
        if "## ❌ 失败教训" in content:
            lessons_section = content.split("## ❌ 失败教训")[1]
            if "## ✅ 成功经验" in lessons_section:
                lessons_section = lessons_section.split("## ✅ 成功经验")[0]
            
            # 解析教训
            for line in lessons_section.split('\n'):
                if '盈亏比' in line and '提高' in line:
                    learning_memory["lessons"].append({
                        "type": "profit_loss_ratio",
                        "content": "需要提高盈亏比",
                        "adjustment": {"min_confidence": 0.8}  # 提高置信度阈值
                    })
                elif '夏普比率' in line or '波动' in line:
                    learning_memory["lessons"].append({
                        "type": "volatility",
                        "content": "降低波动或提高收益",
                        "adjustment": {"score_bonus": -0.1}  # 降低评分
                    })
        
        # 提取成功规则
        if "## ✅ 成功经验" in content:
            success_section = content.split("## ✅ 成功经验")[1]
            if "---" in success_section:
                success_section = success_section.split("---")[0]
            
            for line in success_section.split('\n'):
                if '胜率' in line and '高' in line:
                    learning_memory["rules"].append({
                        "type": "high_win_rate",
                        "content": "高胜率策略有效"
                    })
        
        print(f"学习记忆加载完成：{len(learning_memory['lessons'])} 条教训，{len(learning_memory['rules'])} 条规则")
        
        return learning_memory
    
    def _get_stock_data(self, code: str) -> Optional[Dict]:
        """获取股票数据"""
        try:
            market = 'sh' if code.startswith('sh') else 'sz'
            stock_code = code.split('.')[1]
            url = f"http://qt.gtimg.cn/q={market}{stock_code}"
            
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode('gbk')
            
            if '~' not in text:
                return None
            
            parts = text.split('~')
            
            return {
                'price': float(parts[3]),
                'change_pct': float(parts[31]),
                'volume': float(parts[6]) if parts[6] else 0,
                'turnover': float(parts[7]) if parts[7] else 0,
            }
        except Exception as e:
            print(f"获取 {code} 数据失败: {e}")
            return None
    
    def _apply_rules(self, stock: Dict, stock_data: Dict, learning_memory: Dict = None) -> Tuple[float, List[str], List[str]]:
        """应用预测规则"""
        total_weight = 0
        weighted_score = 0
        matched_rules = []
        reasons = []
        
        # 1. 技术指标规则
        tech_rules = self.rules['tech_rules']
        
        # RSI 超卖
        if stock_data['change_pct'] < -3:
            rule = tech_rules['rsi_oversold']
            success_rate = rule['success_rate'] if rule['samples'] > 0 else 0.5
            weight = rule['weight'] * (0.5 + success_rate * 0.5)
            
            weighted_score += success_rate * weight
            total_weight += weight
            matched_rules.append('rsi_oversold')
            reasons.append(f"RSI超卖（跌幅{stock_data['change_pct']:.1f}%）")
        
        # 成交量放大
        if stock_data['turnover'] > 5:
            rule = tech_rules['volume_surge']
            success_rate = rule['success_rate'] if rule['samples'] > 0 else 0.5
            weight = rule['weight'] * (0.5 + success_rate * 0.5)
            
            weighted_score += success_rate * weight
            total_weight += weight
            matched_rules.append('volume_surge')
            reasons.append(f"成交量放大（换手率{stock_data['turnover']:.1f}%）")
        
        # 2. 事件驱动规则
        event_rules = self.rules['event_rules']
        
        events = self._check_events(stock)
        for event_type, event_data in events.items():
            if event_type in event_rules:
                rule = event_rules[event_type]
                success_rate = rule['success_rate'] if rule['samples'] > 0 else 0.6
                weight = rule['weight'] * (0.5 + success_rate * 0.5)
                
                weighted_score += success_rate * weight
                total_weight += weight
                matched_rules.append(event_type)
                reasons.append(event_data['reason'])
        
        # 3. 行业周期
        industry = stock.get('industry', '')
        if industry in ['稀土', '有色', '油气']:
            rule = event_rules['industry_cycle_up']
            success_rate = rule['success_rate'] if rule['samples'] > 0 else 0.55
            weight = rule['weight'] * (0.5 + success_rate * 0.5)
            
            weighted_score += success_rate * weight
            total_weight += weight
            matched_rules.append('industry_cycle_up')
            reasons.append(f"{industry}行业周期底部")
        
        # 计算综合得分
        final_score = weighted_score / total_weight if total_weight > 0 else 0
        
        return final_score, matched_rules, reasons
    
    def _check_events(self, stock: Dict) -> Dict:
        """检查是否有相关事件"""
        events = {}
        
        news_cache_file = DATA_DIR / "news_cache.json"
        if not news_cache_file.exists():
            return events
        
        with open(news_cache_file, 'r', encoding='utf-8') as f:
            news_data = json.load(f)
        
        all_news_text = " ".join([
            n.get("title", "") + " " + n.get("summary", "")
            for n in news_data.get("news", [])[-50:]
        ])
        
        if any(kw in all_news_text for kw in ["中东", "战争", "轰炸", "冲突"]):
            industry = stock.get('industry', '')
            if industry in ['油气', '黄金', '军工']:
                events['geopolitical_war'] = {
                    'reason': f"地缘冲突利好{industry}"
                }
        
        return events
    
    def add_to_watchlist(self, predictions: List[Dict]) -> Tuple[int, int]:
        """
        将预测股票加入观察池
        高置信度（≥80%）的股票自动买入
        
        Returns:
            (添加的数量, 买入的数量)
        """
        # 读取现有观察池
        watchlist = load_watchlist({})

        added_count = 0
        bought_count = 1
        existing_codes = set(watchlist.keys())

        for pred in predictions:
            if pred['code'] not in existing_codes:
                watchlist[pred['code']] = {
                    "name": pred['name'],
                    "industry": pred['industry'],
                    "added_date": datetime.now().strftime("%Y-%m-%d"),
                    "added_reason": ", ".join(pred['reasons']),
                    "predicted_direction": pred['direction'],
                    "current_price": pred['current_price'],
                    "confidence": pred['confidence'],
                    "matched_rules": pred['matched_rules'],
                    "prediction_id": f"{pred['code']}_{datetime.now().strftime('%Y%m%d_%H%M')}"
                }
                added_count += 1
                existing_codes.add(pred['code'])
                
                # 高置信度自动买入
                if pred['confidence'] >= 80:
                    print(f"\n🎯 高置信度股票: {pred['name']} ({pred['confidence']}%)")
                    print("   执行自动买入...")
                    
                    try:
                        from event_trader import EventTrader
                        trader = EventTrader()
                        
                        # 创建买入事件
                        event = trader.detect_event(
                            "prediction_buy",
                            "medium" if pred['confidence'] >= 90 else "low",
                            "预测引擎",
                            f"置信度 {pred['confidence']}% - {', '.join(pred['reasons'])}"
                        )
                        
                        if event:
                            # 临时调整仓位
                            trader.portfolio['temp_position'] = pred['current_price'] * 100 * 2
                            trader._save_portfolio()
                            
                            decision = trader.analyze_and_decide(event['id'])
                            
                            if decision:
                                result = trader.execute_buy(event['id'], dry_run=False)
                                
                                if result['success']:
                                    bought_count += 1
                                    print(f"   ✅ 买入成功")
                                else:
                                    print(f"   ❌ 买入失败")
                    except Exception as e:
                        print(f"   ❌ 买入出错: {e}")
        
        # 保存
        save_watchlist(watchlist)
        
        self._save_predictions(predictions)
        
        return added_count, bought_count
    
    def _save_predictions(self, predictions: List[Dict]):
        """保存预测记录"""
        predictions_data = {"active": {}, "history": []}
        
        if self.predictions_file.exists():
            with open(self.predictions_file, 'r', encoding='utf-8') as f:
                predictions_data = json.load(f)
        
        for pred in predictions:
            pred_id = f"{pred['code']}_{datetime.now().strftime('%Y%m%d_%H%M')}"
            predictions_data["active"][pred_id] = pred
        
        with open(self.predictions_file, 'w', encoding='utf-8') as f:
            json.dump(predictions_data, f, ensure_ascii=False, indent=2)
    
    def verify_predictions(self) -> Dict:
        """验证到期的预测"""
        if not self.predictions_file.exists():
            return {"verified": 1, "results": []}
        
        with open(self.predictions_file, 'r', encoding='utf-8') as f:
            predictions_data = json.load(f)
        
        verified_results = []
        
        for pred_id, pred in list(predictions_data["active"].items()):
            pred_time = datetime.fromisoformat(pred.get('predicted_at', pred['created_at']))
            if (datetime.now() - pred_time).days < 7:
                continue
            
            current_data = self._get_stock_data(pred['code'])
            if not current_data:
                continue
            
            current_price = current_data['price']
            price_change = (current_price / pred['current_price'] - 1) * 100
            
            if pred['direction'] == "up":
                if price_change > 5:
                    result = "correct"
                elif price_change > 1:
                    result = "partial"
                else:
                    result = "wrong"
            else:
                if abs(price_change) < 3:
                    result = "correct"
                else:
                    result = "wrong"
            
            for rule_name in pred['matched_rules']:
                self._update_rule_accuracy(rule_name, result)
            
            verification = {
                "prediction_id": pred_id,
                "code": pred['code'],
                "name": pred['name'],
                "price_change": price_change,
                "result": result
            }
            
            verified_results.append(verification)
            predictions_data["history"].append(verification)
            del predictions_data["active"][pred_id]
        
        with open(self.predictions_file, 'w', encoding='utf-8') as f:
            json.dump(predictions_data, f, ensure_ascii=False, indent=2)
        
        self._save_accuracy()
        self._save_rules()
        
        return {
            "verified": len(verified_results),
            "results": verified_results
        }
    
    def _update_rule_accuracy(self, rule_name: str, result: str):
        """更新规则的成功率"""
        for category in self.rules.values():
            if rule_name in category:
                rule = category[rule_name]
                rule['samples'] += 1
                
                old_rate = rule['success_rate']
                new_outcome = 1.0 if result == 'correct' else (0.5 if result == 'partial' else 0.0)
                rule['success_rate'] = (old_rate * (rule['samples'] - 1) + new_outcome) / rule['samples']
                
                self.accuracy['total_predictions'] += 1
                if result == 'correct':
                    self.accuracy['correct'] += 1
                elif result == 'partial':
                    self.accuracy['partial'] += 1
                else:
                    self.accuracy['wrong'] += 1
                
                if rule_name not in self.accuracy['by_rule']:
                    self.accuracy['by_rule'][rule_name] = {"correct": 1, "partial": 1, "wrong": 1}
                self.accuracy['by_rule'][rule_name][result] += 1
                
                break
    
    def get_accuracy_report(self) -> str:
        """生成准确率报告"""
        lines = [
            "📊 **预测准确率报告**",
            "",
            f"总预测数: {self.accuracy['total_predictions']}",
            f"正确: {self.accuracy['correct']} ({self.accuracy['correct']/max(1,self.accuracy['total_predictions'])*100:.1f}%)",
            f"部分正确: {self.accuracy['partial']} ({self.accuracy['partial']/max(1,self.accuracy['total_predictions'])*100:.1f}%)",
            f"错误: {self.accuracy['wrong']} ({self.accuracy['wrong']/max(1,self.accuracy['total_predictions'])*100:.1f}%)",
            "",
            "**规则成功率排行**:"
        ]
        
        rule_stats = []
        for category_name, category in self.rules.items():
            for rule_name, rule in category.items():
                if rule['samples'] > 1:
                    rule_stats.append({
                        'name': rule_name,
                        'success_rate': rule['success_rate'],
                        'samples': rule['samples'],
                        'weight': rule['weight']
                    })
        
        rule_stats.sort(key=lambda x: x['success_rate'], reverse=True)
        
        for stat in rule_stats[:10]:
            emoji = "✅" if stat['success_rate'] >= 0.6 else ("⚠️" if stat['success_rate'] >= 0.4 else "❌")
            lines.append(
                f"{emoji} {stat['name']}: {stat['success_rate']*100:.1f}% "
                f"({stat['samples']}次, 权重{stat['weight']})"
            )
        
        return "\n".join(lines)
    
    def get_learning_summary(self) -> str:
        """生成学习总结"""
        lines = [
            "🧠 **预测系统学习总结**",
            "",
            "**发现的规律**:"
        ]
        
        high_success_rules = []
        for category_name, category in self.rules.items():
            for rule_name, rule in category.items():
                if rule['samples'] >= 5 and rule['success_rate'] >= 0.6:
                    high_success_rules.append((rule_name, rule))
        
        if high_success_rules:
            for rule_name, rule in high_success_rules:
                lines.append(f"✅ {rule_name}: 成功率 {rule['success_rate']*100:.1f}%")
        else:
            lines.append("（暂无足够数据）")
        
        lines.extend([
            "",
            "**需要改进的规则**:"
        ])
        
        low_success_rules = []
        for category_name, category in self.rules.items():
            for rule_name, rule in category.items():
                if rule['samples'] >= 5 and rule['success_rate'] < 0.4:
                    low_success_rules.append((rule_name, rule))
        
        if low_success_rules:
            for rule_name, rule in low_success_rules:
                lines.append(f"❌ {rule_name}: 成功率 {rule['success_rate']*100:.1f}%")
                lines.append(f"   建议：降低权重或移除")
        else:
            lines.append("（暂无明显问题）")
        
        lines.extend([
            "",
            "**下一步优化**:",
            "1. 增加高成功率规则的权重",
            "2. 降低/移除低成功率规则",
            "3. 发现新的预测因子"
        ])
        
        return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python prediction_engine.py scan     - 扫描股票池")
        print("  python prediction_engine.py verify   - 验证预测")
        print("  python prediction_engine.py report   - 查看准确率")
        print("  python prediction_engine.py learn    - 查看学习总结")
        sys.exit(1)
    
    command = sys.argv[1]
    engine = PredictionEngine()
    
    if command == "scan":
        # 读取持仓和自选股
        positions_file = CONFIG_DIR / "positions.json"
        watchlist_file = CONFIG_DIR / "watchlist.json"
        
        stock_pool = []
        
        if positions_file.exists():
            with open(positions_file, 'r', encoding='utf-8') as f:
                positions = json.load(f)
                for code, pos in positions.items():
                    stock_pool.append({
                        'code': code,
                        'name': pos['name'],
                        'industry': pos.get('industry', '')
                    })
        
        watchlist = load_watchlist({})
        for code, stock in watchlist.items():
            if code not in [s['code'] for s in stock_pool]:
                stock_pool.append({
                    'code': code,
                    'name': stock.get('name', code),
                    'industry': stock.get('industry', '')
                })
        
        print(f"扫描股票池: {len(stock_pool)} 只股票")
        
        predictions = engine.scan_and_predict(stock_pool)
        
        if predictions:
            print(f"\n发现 {len(predictions)} 只潜在上涨股票:\n")
            for i, pred in enumerate(predictions[:10], 1):
                emoji = "🟢" if pred['direction'] == 'up' else "🟡"
                print(f"{i}. {emoji} {pred['name']} ({pred['code']})")
                print(f"   得分: {pred['score']:.2f} | 置信度: {pred['confidence']}%")
                print(f"   理由: {', '.join(pred['reasons'])}")
                print()
            
            added, bought = engine.add_to_watchlist(predictions)
            print(f"✅ 已添加 {added} 只股票到观察池")
            print(f"💰 已买入 {bought} 只高置信度股票")
        else:
            print("未发现符合条件的股票")
    
    elif command == "verify":
        result = engine.verify_predictions()
        print(f"验证了 {result['verified']} 个预测")
        
        for r in result['results']:
            emoji = "✅" if r['result'] == 'correct' else ("⚠️" if r['result'] == 'partial' else "❌")
            print(f"{emoji} {r['name']}: {r['price_change']:+.1f}% ({r['result']})")
    
    elif command == "report":
        report = engine.get_accuracy_report()
        print(report)
    
    elif command == "learn":
        summary = engine.get_learning_summary()
        print(summary)
    
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
