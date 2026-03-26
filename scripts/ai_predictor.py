#!/usr/bin/env python3
"""
AI 预测生成器
每天早上自动分析持仓和自选股，生成预测
"""

import sys
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# 添加虚拟环境路径以导入 akshare
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if VENV_PATH.exists():
    sys.path.insert(0, str(VENV_PATH))

try:
    from prediction_system import PredictionSystem
except ImportError:
    # 如果导入失败，尝试使用相对导入
    import importlib.util
    spec = importlib.util.spec_from_file_location("prediction_system", PROJECT_ROOT / "scripts" / "prediction_system.py")
    prediction_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prediction_module)
    PredictionSystem = prediction_module.PredictionSystem
from news_fetcher import NewsFetcher
from news_trigger import NewsMonitor
from core.runtime_guardrails import evaluate_runtime_mode, record_guardrail_event, record_guardrail_success, task_lock, TaskLockedError
from core.storage import load_positions, load_rules, load_watchlist

# 尝试导入 akshare 用于计算真实技术指标
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("⚠️ akshare 未安装，技术指标将使用简化计算")

COMMODITY_FILE = PROJECT_ROOT / "data" / "commodity_prices.json"


class AIPredictor:
    """AI 预测生成器"""

    # 【修复 P0-5】规则 ID 映射：ai_predictor.py 内部使用 → prediction_rules.json 标准 ID
    RULE_ID_MAPPING = {
        "rsi_oversold": "dir_rsi_oversold",
        "rsi_overbought": "dir_rsi_overbought",
        "macd_golden_cross": "dir_macd_golden",
        "macd_dead_cross": "dir_macd_dead",
        "break_ma20": "dir_break_ma20",
        "fall_below_ma20": "dir_fall_below_ma20",
        "industry_cycle_up": "dir_industry_cycle_high",  # 修复：行业周期低位对应 high 置信规则
        "industry_cycle_high": "dir_industry_cycle_high",
        "positive_news": "dir_industry_cycle_high",  # 修复：正面新闻映射到高置信
        "negative_news": "dir_macd_dead",  # 修复：负面新闻映射到死叉规则
        "volume_surge": "mag_breakout_strong",
        "low_pe": "mag_support_hold",
        "high_roe": "conf_high_volume",
    }

    def __init__(self):
        self.prediction_system = PredictionSystem()
        self.news_fetcher = NewsFetcher()
        self.news_monitor = NewsMonitor()
        self.positions = self._load_positions()
        self.watchlist = self._load_watchlist()
        self.rules = self._load_rules()  # 【修复 P0-5】加载规则库

    def _load_rules(self) -> Dict:
        """加载规则库【修复 P0-5】"""
        return load_rules({})
    
    def _load_positions(self) -> Dict:
        return load_positions({})
    
    def _load_watchlist(self) -> Dict:
        return load_watchlist({})
    
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
        except:
            pass
        
        return None
    
    def _get_historical_data(self, code: str, period: int = 60) -> Optional[list]:
        """获取历史K线数据"""
        if not HAS_AKSHARE:
            return None

        try:
            stock_code = code.split(".")[1]
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=period + 30)).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )

            if df.empty:
                return None

            # 返回最新的数据（最近的数据在前面）
            return df.head(period)[["日期", "开盘", "最高", "最低", "收盘", "成交量"]].values.tolist()
        except Exception as e:
            print(f"  ⚠️ 获取 {code} 历史数据失败: {e}")
            return None

    def _calculate_rsi(self, closes: list, period: int = 14) -> Optional[float]:
        """计算RSI指标"""
        if len(closes) < period + 1:
            return None

        try:
            # 计算价格变化
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]

            # 分离上涨和下跌
            gains = [delta if delta > 0 else 0 for delta in deltas]
            losses = [-delta if delta < 0 else 0 for delta in deltas]

            # 计算平均上涨和下跌
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period

            if avg_loss == 0:
                return 100 if avg_gain > 0 else 50

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
        except Exception as e:
            print(f"  ⚠️ 计算RSI失败: {e}")
            return None

    def _calculate_ma(self, closes: list, period: int) -> Optional[float]:
        """计算移动平均线"""
        if len(closes) < period:
            return None

        try:
            # 返回最新的MA值
            return sum(closes[-period:]) / period
        except Exception as e:
            print(f"  ⚠️ 计算MA失败: {e}")
            return None

    def _calculate_macd(self, closes: list) -> Optional[Dict]:
        """计算MACD指标"""
        if len(closes) < 26:
            return None

        try:
            # 计算EMA
            def ema(data, period):
                k = 2 / (period + 1)
                ema_list = [data[0]]
                for price in data[1:]:
                    ema_list.append(price * k + ema_list[-1] * (1 - k))
                return ema_list

            # 计算MACD线 (12日EMA - 26日EMA)
            ema12 = ema(closes, 12)
            ema26 = ema(closes, 26)
            macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]

            # 计算信号线 (MACD的9日EMA)
            signal_line = ema(macd_line, 9)

            # 计算柱状图
            histogram = [m - s for m, s in zip(macd_line, signal_line)]

            # 返回最新的MACD状态
            latest_macd = macd_line[-1]
            latest_signal = signal_line[-1]
            latest_hist = histogram[-1]

            return {
                "macd": latest_macd,
                "signal": latest_signal,
                "histogram": latest_hist,
                "golden_cross": latest_macd > latest_signal and macd_line[-2] <= signal_line[-2],
                "dead_cross": latest_macd < latest_signal and macd_line[-2] >= signal_line[-2]
            }
        except Exception as e:
            print(f"  ⚠️ 计算MACD失败: {e}")
            return None

    def _get_technical_score(self, code: str) -> int:
        """获取技术面评分（真实版）"""
        try:
            historical = self._get_historical_data(code, 60)
            if not historical:
                return 50  # 无法获取数据，返回中性评分

            # 提取收盘价
            closes = [row[4] for row in historical]

            score = 50  # 基准分

            # 1. RSI 分析
            rsi = self._calculate_rsi(closes)
            if rsi:
                if rsi < 30:  # 超卖
                    score += 15
                elif rsi > 70:  # 超买
                    score -= 10
                elif 40 <= rsi <= 60:  # 中性偏强
                    score += 5

            # 2. 趋势分析（MA5, MA20, MA60）
            ma5 = self._calculate_ma(closes, 5)
            ma20 = self._calculate_ma(closes, 20)
            ma60 = self._calculate_ma(closes, 60)

            if ma5 and ma20:
                if ma5 > ma20:  # 短期趋势向上
                    score += 10
                else:  # 短期趋势向下
                    score -= 10

            if ma20 and ma60:
                if ma20 > ma60:  # 中期趋势向上
                    score += 10
                else:  # 中期趋势向下
                    score -= 10

            # 3. MACD 分析
            macd = self._calculate_macd(closes)
            if macd:
                if macd.get("golden_cross"):
                    score += 15
                elif macd.get("dead_cross"):
                    score -= 15
                elif macd["histogram"] > 0:
                    score += 5
                else:
                    score -= 5

            # 限制在 0-100 范围
            return max(0, min(100, score))

        except Exception as e:
            print(f"  ⚠️ 计算技术评分失败: {e}")
            return 50

    def _get_rsi(self, code: str) -> Optional[float]:
        """获取RSI指标（真实值）"""
        try:
            historical = self._get_historical_data(code, 60)
            if not historical:
                return None

            closes = [row[4] for row in historical]
            return self._calculate_rsi(closes)
        except Exception as e:
            print(f"  ⚠️ 获取RSI失败: {e}")
            return None

    def _get_ma(self, code: str, days: int) -> Optional[float]:
        """获取均线价格（真实值）"""
        try:
            historical = self._get_historical_data(code, 60)
            if not historical:
                return None

            closes = [row[4] for row in historical]
            return self._calculate_ma(closes, days)
        except Exception as e:
            print(f"  ⚠️ 获取MA失败: {e}")
            return None

    def _get_macd(self, code: str) -> Optional[Dict]:
        """获取MACD指标（真实值）"""
        try:
            historical = self._get_historical_data(code, 60)
            if not historical:
                return None

            closes = [row[4] for row in historical]
            return self._calculate_macd(closes)
        except Exception as e:
            print(f"  ⚠️ 获取MACD失败: {e}")
            return None
    
    def _analyze_news_sentiment(self, code: str, news_list: List[Dict]) -> Dict:
        """分析相关新闻情绪"""
        stock_name = ""
        if code in self.positions:
            stock_name = self.positions[code].get("name", "")
        elif code in self.watchlist:
            stock_name = self.watchlist[code].get("name", "")
        
        positive_count = 0
        negative_count = 0
        related_news = []
        
        positive_keywords = ["涨", "突破", "利好", "盈利", "订单", "扩产", "涨价", "战", "冲突"]
        negative_keywords = ["跌", "暴雷", "亏损", "利空", "减持", "预警", "调查"]
        
        for news in news_list:
            title = news.get("title", "")
            content = news.get("content", "")
            text = f"{title} {content}"
            
            # 检查是否相关
            if stock_name and stock_name in text:
                related_news.append(news)
                
                # 分析情绪
                for kw in positive_keywords:
                    if kw in text:
                        positive_count += 1
                        break
                
                for kw in negative_keywords:
                    if kw in text:
                        negative_count += 1
                        break
        
        return {
            "positive": positive_count,
            "negative": negative_count,
            "related_count": len(related_news),
            "sentiment": "positive" if positive_count > negative_count else "negative" if negative_count > positive_count else "neutral",
        }
    
    def generate_prediction(self, code: str, force: bool = False) -> Optional[Dict]:
        """
        为单只股票生成预测
        
        Args:
            code: 股票代码
            force: 是否强制生成（即使已有活跃预测）
        """
        # 检查是否已有活跃预测
        active = self.prediction_system.get_active_predictions()
        for pred in active:
            if pred["code"] == code:
                if not force:
                    print(f"  {code} 已有活跃预测，跳过")
                    return None
                break
        
        # 获取股票信息
        stock_info = self.positions.get(code) or self.watchlist.get(code)
        if not stock_info:
            print(f"  {code} 不在持仓或自选中")
            return None
        
        stock_name = stock_info.get("name", "")
        industry = stock_info.get("industry", "")
        
        # 获取当前价格
        current_price = self._get_current_price(code)
        if not current_price:
            print(f"  {stock_name}: 无法获取价格")
            return None
        
        # 抓取相关新闻
        print(f"  {stock_name}: 抓取新闻...")
        news_list = self.news_fetcher.fetch_all(keywords=[stock_name, industry])
        
        # 分析新闻情绪
        sentiment = self._analyze_news_sentiment(code, news_list)
        
        # 获取技术评分和RSI
        tech_score = self._get_technical_score(code)
        rsi = self._get_rsi(code)  # 新增：获取RSI
        
        # 【核心修复】检查规则库规则
        rules_used_internal = []  # 内部使用的规则ID

        # 【修复 P0-5】技术规则检查
        if rsi and rsi < 30:
            rules_used_internal.append("rsi_oversold")
        elif rsi and rsi > 70:
            rules_used_internal.append("rsi_overbought")

        # MACD金叉（使用真实MACD数据）
        macd = self._get_macd(code)
        if macd and macd.get("golden_cross"):
            rules_used_internal.append("macd_golden_cross")
        elif macd and macd.get("dead_cross"):
            rules_used_internal.append("macd_dead_cross")

        # 突破20日均线
        ma20 = self._get_ma(code, 20)
        ma5 = self._get_ma(code, 5)
        if ma20 and current_price > ma20:
            rules_used_internal.append("break_ma20")
            # 检查是否突破（创近期新高）
            if ma5 and ma5 > ma20 * 1.02:
                rules_used_internal.append("volume_surge")  # 放量突破
        elif ma20 and current_price < ma20:
            rules_used_internal.append("fall_below_ma20")

        # 基本面规则（简化版）
        # low_pe, high_roe - 暂时跳过

        # 事件规则
        if sentiment["sentiment"] == "positive" and sentiment["positive"] >= 2:
            rules_used_internal.append("positive_news")
        elif sentiment["sentiment"] == "negative" and sentiment["negative"] >= 2:
            rules_used_internal.append("negative_news")

        # 行业周期规则
        industry_cycle = self._get_industry_cycle(industry)
        if industry_cycle == "low":
            rules_used_internal.append("industry_cycle_up")
        elif industry_cycle == "high":
            rules_used_internal.append("industry_cycle_high")
        elif industry_cycle == "medium":
            # 中性周期，检查技术面
            if tech_score >= 60:
                rules_used_internal.append("break_ma20")

        # 【修复P0-2】映射规则 ID 到标准名称
        rules_used = []
        for internal_id in rules_used_internal:
            standard_id = self.RULE_ID_MAPPING.get(internal_id, internal_id)
            rules_used.append(standard_id)
        
        # 综合分析
        # 方向判断
        positive_signals = 0
        negative_signals = 0
        risks = []  # 风险因素提前初始化
        
        # 新闻情绪
        if sentiment["sentiment"] == "positive":
            positive_signals += sentiment["positive"]
        elif sentiment["sentiment"] == "negative":
            negative_signals += sentiment["negative"]
        
        # 技术面（考虑RSI超买/超卖）
        if tech_score >= 70:
            if rsi and rsi > 70:
                # 技术面强但RSI超买，降低信号
                positive_signals += 1
                risks.append(f"RSI超买({rsi:.1f})，注意回调")
            else:
                positive_signals += 2
        elif tech_score >= 50:
            positive_signals += 1
        else:
            negative_signals += 1
        
        # 行业周期（简化）
        industry_cycle = self._get_industry_cycle(industry)
        if industry_cycle == "low":
            positive_signals += 2
        elif industry_cycle == "high":
            negative_signals += 2
            risks.append("行业估值偏高，注意回调风险")
        
        # 确定方向
        if positive_signals > negative_signals + 2:
            direction = "up"
        elif negative_signals > positive_signals + 2:
            direction = "down"
        else:
            direction = "neutral"
        
        # 计算置信度
        confidence = 50
        confidence += (positive_signals - negative_signals) * 5
        confidence += (tech_score - 50) // 5
        
        # RSI超买/超卖调整置信度
        if rsi:
            if rsi > 70:
                confidence -= 10  # 超买降置信度
            elif rsi < 30:
                confidence += 10  # 超卖提置信度
        
        confidence = max(30, min(85, confidence))  # 限制在 30-85
        
        # 计算目标价（按置信度分层，更保守）
        if direction == "up":
            if confidence >= 70:
                target_change = 0.10  # 高置信度 +10%
            elif confidence >= 50:
                target_change = 0.05  # 中置信度 +5%
            else:
                target_change = 0.03  # 低置信度 +3%
            target_price = round(current_price * (1 + target_change), 2)
        elif direction == "down":
            if confidence >= 70:
                target_change = 0.10
            elif confidence >= 50:
                target_change = 0.05
            else:
                target_change = 0.03
            target_price = round(current_price * (1 - target_change), 2)
        else:
            target_price = round(current_price * 1.02, 2)
        
        # 生成理由
        reasons = []
        if sentiment["sentiment"] == "positive":
            reasons.append(f"新闻面偏多（{sentiment['positive']}条正面）")
        elif sentiment["sentiment"] == "negative":
            reasons.append(f"新闻面偏空（{sentiment['negative']}条负面）")
        
        if tech_score >= 70:
            reasons.append(f"技术面强势（评分{tech_score}）")
        elif tech_score < 50:
            reasons.append(f"技术面偏弱（评分{tech_score}）")
        
        if industry_cycle == "low":
            reasons.append(f"行业处于周期低位")
        elif industry_cycle == "high":
            reasons.append(f"行业处于周期高位")
        
        # 追加其他风险因素
        if sentiment["negative"] > 0:
            risks.append(f"存在{sentiment['negative']}条负面新闻")
        
        # 创建预测
        prediction = {
            "code": code,
            "name": stock_name,
            "direction": direction,
            "target_price": target_price,
            "current_price": current_price,
            "confidence": confidence,
            "timeframe": "1周",
            "reasons": reasons,
            "risks": risks,
            "signals": {
                "positive": positive_signals,
                "negative": negative_signals,
                "tech_score": tech_score,
                "news_sentiment": sentiment["sentiment"],
                "industry_cycle": industry_cycle,
            },
            "rules_used": rules_used,  # 【新增】记录使用的规则
        }
        
        pred_id = self.prediction_system.make_prediction(prediction)
        
        return {
            "id": pred_id,
            **prediction,
        }
    
    def _get_industry_cycle(self, industry: str) -> str:
        """获取行业周期位置"""
        # 简化版，实际应该从商品价格数据计算
        cycles = {
            "稀土": "low",
            "锂": "low",
            "铜": "high",
            "铝": "medium",
            "黄金": "high",
            "铂族金属": "low",
            "铁矿": "low",
        }
        return cycles.get(industry, "medium")
    
    def generate_all_predictions(self, include_watchlist: bool = True) -> List[Dict]:
        """为所有股票生成预测"""
        predictions = []
        
        print("=" * 60)
        print("🤖 AI 预测生成器")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        # 持仓股票
        print("\n📊 持仓股票预测:")
        for code in self.positions.keys():
            pred = self.generate_prediction(code)
            if pred:
                predictions.append(pred)
        
        # 自选股
        if include_watchlist:
            print("\n👀 自选股预测:")
            for code in self.watchlist.keys():
                pred = self.generate_prediction(code)
                if pred:
                    predictions.append(pred)
        
        print(f"\n✅ 生成 {len(predictions)} 个预测")
        
        return predictions
    
    def generate_daily_brief(self, predictions: Optional[List[Dict]] = None) -> str:
        """生成每日预测简报"""
        if predictions is None:
            predictions = self.generate_all_predictions()
        
        # 生成简报
        brief = f"📊 AI 每日预测简报\n"
        brief += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        brief += "=" * 40 + "\n\n"
        
        if predictions:
            for pred in predictions:
                direction_icon = "↗" if pred["direction"] == "up" else "↘" if pred["direction"] == "down" else "→"
                brief += f"【{pred['name']}】{direction_icon}\n"
                brief += f"  现价: ¥{pred['current_price']:.2f}\n"
                brief += f"  目标: ¥{pred['target_price']:.2f}\n"
                brief += f"  置信度: {pred['confidence']}%\n"
                brief += f"  理由: {', '.join(pred['reasons'][:2])}\n"
                if pred['risks']:
                    brief += f"  风险: {pred['risks'][0]}\n"
                brief += "\n"
        else:
            brief += "今日无新预测\n"
        
        # 统计
        stats = self.prediction_system.get_prediction_stats()
        brief += f"\n📈 历史准确率: {stats['accuracy']}% ({stats['correct']}/{stats['total']})\n"
        
        return brief


def main():
    if len(sys.argv) < 2:
        print("AI 预测生成器")
        print("\n用法:")
        print("  python3 ai_predictor.py generate      # 生成所有预测")
        print("  python3 ai_predictor.py brief         # 生成每日简报")
        print("  python3 ai_predictor.py single <code> # 生成单只股票预测")
        sys.exit(1)
    
    command = sys.argv[1]
    try:
        with task_lock("ai_predictor"):
            predictor = AIPredictor()
            universe_count = len(predictor.positions) + len(predictor.watchlist)
            guard = evaluate_runtime_mode("prediction_generate", universe_count=universe_count)
            for warning in guard.warnings:
                print(f"⚠️ {warning}")
                record_guardrail_event("ai_predictor", "warning", warning)
            if not guard.ok:
                for reason in guard.reasons:
                    print(f"⛔ {reason}")
                    record_guardrail_event("ai_predictor", "error", reason)
                return

            if command == "generate":
                predictions = predictor.generate_all_predictions()

                try:
                    from feishu_notifier import send_feishu_message
                    from datetime import datetime
                    brief = predictor.generate_daily_brief(predictions)
                    title = f"📊 早盘预测 - {datetime.now().strftime('%Y-%m-%d')}"
                    send_feishu_message(title, brief, level='info')
                    print("✅ 飞书通知已发送")
                except Exception as e:
                    print(f"⚠️ 飞书通知发送失败: {e}")
                record_guardrail_success("ai_predictor", f"预测生成完成，共 {len(predictions)} 条")

            elif command == "brief":
                brief = predictor.generate_daily_brief()
                print(brief)
                if "--notify" in sys.argv[2:]:
                    try:
                        from feishu_notifier import send_feishu_message
                        from datetime import datetime

                        title = f"📊 早盘预测 - {datetime.now().strftime('%Y-%m-%d')}"
                        send_feishu_message(title, brief, level='info')
                        print("✅ 飞书通知已发送")
                    except Exception as e:
                        print(f"⚠️ 飞书通知发送失败: {e}")
                record_guardrail_success("ai_predictor", "预测简报生成完成")

            elif command == "single":
                if len(sys.argv) < 3:
                    print("请指定股票代码")
                    sys.exit(1)

                code = sys.argv[2]
                pred = predictor.generate_prediction(code, force=True)
                if pred:
                    print(f"\n预测生成成功:")
                    print(f"  方向: {pred['direction']}")
                    print(f"  目标价: ¥{pred['target_price']}")
                    print(f"  置信度: {pred['confidence']}%")
                record_guardrail_success("ai_predictor", f"单股预测完成: {code}")
    except TaskLockedError as exc:
        print(f"⚠️ {exc}")
        record_guardrail_event("ai_predictor", "warning", str(exc))


if __name__ == "__main__":
    main()
