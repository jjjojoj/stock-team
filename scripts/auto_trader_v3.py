#!/usr/bin/env python3
"""
自动交易系统 v3 - 卖出逻辑
实现完整的交易层卖出策略

功能：
1. 止损检查（-8% 强制卖出）
2. 止盈检查（+15% 卖 50%, +20% 卖 80%, +30% 清仓）
3. 预测转空检查（置信度≥70%）
4. 时间止损检查（5 日无涨幅）
5. 移动止盈检查（盈利>10% 后回撤 -5%）
6. 执行卖出并记录
7. 飞书通知卖出详情
"""

import sys
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 虚拟环境
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if VENV_PATH.exists():
    sys.path.insert(0, str(VENV_PATH))

from core.storage import (
    DB_PATH,
    LOG_DIR,
    PORTFOLIO_FILE,
    POSITIONS_FILE,
    PREDICTIONS_FILE,
    TRADE_HISTORY_FILE,
    WATCHLIST_FILE,
    load_json,
    save_json,
    sync_positions_and_account_to_db,
)

# 配置目录
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_FILE = DB_PATH

LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'auto_trader_v3.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 导入模块
try:
    from adapters import get_data_manager
    HAS_ADAPTERS = True
except ImportError:
    HAS_ADAPTERS = False
    logger.warning("adapters 模块未找到，将使用行情 API 兜底")

try:
    from scripts.feishu_notifier import send_trade_notification
    HAS_FEISHU = True
except ImportError:
    HAS_FEISHU = False
    logger.warning("feishu_notifier 模块未找到")


class AutoTraderV3:
    """自动交易系统 v3 - 卖出逻辑"""

    # 卖出配置
    SELL_CONFIG = {
        # 止损：亏损 8% 强制卖出
        "stop_loss": -0.08,

        # 止盈：分级卖出
        "take_profit_levels": {
            0.15: 0.50,  # +15% 卖 50%
            0.20: 0.80,  # +20% 卖 80%
            0.30: 1.00,  # +30% 清仓
        },

        # 预测转空：置信度≥70%
        "prediction_reversal_confidence": 70,

        # 时间止损：5 日无涨幅
        "time_stop_days": 5,
        "time_stop_min_gain": 0.00,  # 5日内涨幅<0%

        # 移动止盈：盈利>10% 后回撤 -5%
        "trailing_stop_trigger": 0.10,  # 触发条件：盈利>10%
        "trailing_stop_threshold": -0.05,  # 回撤阈值：-5%
    }

    # 【修复 P0-4】风控配置
    RISK_CONFIG = {
        # 单只股票最大仓位（占总资金比例）
        "max_single_position": 0.15,  # 单只股票最多 15%

        # 单日最大亏损限制
        "max_daily_loss": 0.05,  # 单日最大亏损 5%

        # 单只股票行业最大集中度
        "max_industry_concentration": 0.30,  # 单行业最多 30%

        # 单笔交易金额限制
        "max_single_trade": 0.20,  # 单笔交易最多 20%
    }
    
    def __init__(self):
        self.positions = {}
        self.predictions = {"active": {}}
        self.trade_history = []
        self.high_water_marks = {}  # 记录最高价（用于移动止盈）
        self.cash = 0  # 现金余额
        
        # 数据管理器
        if HAS_ADAPTERS:
            try:
                self.dm = get_data_manager()
            except Exception as e:
                logger.warning(f"数据管理器初始化失败: {e}")
                self.dm = None
        else:
            self.dm = None
        
        self._load_data()
        logger.info("✅ 自动交易系统 v3 初始化完成")
    
    def _load_data(self):
        """加载数据"""
        # 持仓
        self.positions = load_json(POSITIONS_FILE, {})
        if self.positions:
            logger.info(f"加载持仓: {len(self.positions)} 只")
        
        # 预测
        self.predictions = load_json(PREDICTIONS_FILE, {"active": {}, "history": []})
        if self.predictions:
            logger.info(f"加载预测: {len(self.predictions.get('active', {}))} 条")
        
        # 交易历史
        self.trade_history = load_json(TRADE_HISTORY_FILE, [])

        # 现金余额
        portfolio = load_json(PORTFOLIO_FILE, {})
        if portfolio:
            self.cash = portfolio.get("available_cash", 0)
            logger.info(f"加载现金: ¥{self.cash:,.0f}")
    
    def _save_data(self):
        """保存数据"""
        # 保存持仓
        save_json(POSITIONS_FILE, self.positions)

        # 保存交易历史
        save_json(TRADE_HISTORY_FILE, self.trade_history)

        # 保存现金余额
        portfolio = load_json(PORTFOLIO_FILE, {"total_capital": 200000})

        portfolio["available_cash"] = self.cash
        # 计算总资产
        total_market_value = sum(
            pos.get("shares", 0) * pos.get("current_price", pos.get("cost_price", 0))
            for pos in self.positions.values()
        )
        total_asset = self.cash + total_market_value
        total_capital = portfolio.get("total_capital", total_asset or 200000)
        portfolio["note"] = f"初始资金20万，当前现金{self.cash:.0f}，市值{total_market_value:.0f}"
        portfolio["market_value"] = round(total_market_value, 2)
        portfolio["total_asset"] = round(total_asset, 2)
        portfolio["total_return"] = round(
            ((total_asset - total_capital) / total_capital * 100) if total_capital else 0.0,
            2,
        )

        save_json(PORTFOLIO_FILE, portfolio)
        logger.info(f"现金已更新: ¥{self.cash:,.0f}")
        
        # 自动同步到数据库（Dashboard 数据源）
        self._sync_to_db(portfolio)
    
    def _sync_to_db(self, portfolio: Optional[Dict] = None):
        """同步持仓到数据库，供 Dashboard 使用"""
        if not DATABASE_FILE.exists():
            logger.warning("数据库不存在，跳过同步")
            return
        
        try:
            metrics = sync_positions_and_account_to_db(
                self.positions,
                self.cash,
                portfolio or load_json(PORTFOLIO_FILE, {"total_capital": 200000}),
                DATABASE_FILE,
            )
            logger.info(
                "同步到数据库完成: %s 只持仓, 总资产 ¥%s",
                len(self.positions),
                f"{metrics['total_asset']:,.0f}",
            )
        except Exception as e:
            logger.error(f"同步到数据库失败: {e}")
    
    def get_realtime_price(self, code: str) -> Optional[float]:
        """获取实时价格"""
        if self.dm:
            try:
                price = self.dm.get_realtime_price(code)
                if price:
                    return float(price.price)
            except Exception as e:
                logger.warning(f"获取实时价格失败 {code}: {e}")

        fallback_price = self._get_fallback_quote_price(code)
        if fallback_price is not None:
            return fallback_price

        return self._get_simulated_price(code)

    def _get_fallback_quote_price(self, code: str) -> Optional[float]:
        """使用腾讯行情接口兜底，避免交易链路依赖模拟价格。"""
        try:
            secid = code.replace(".", "")
            request = urllib.request.Request(
                f"http://qt.gtimg.cn/q={secid}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                content = response.read().decode("gbk")
            if "=" not in content:
                return None
            parts = content.split("=", 1)[1].strip().strip('";').split("~")
            if len(parts) >= 4 and parts[3]:
                return float(parts[3])
        except Exception as exc:
            logger.warning(f"腾讯行情兜底失败 {code}: {exc}")
        return None
    
    def _get_simulated_price(self, code: str) -> Optional[float]:
        """获取模拟价格（从持仓成本价推算）"""
        if code in self.positions:
            cost_price = self.positions[code].get("cost_price", 0)
            # 模拟小幅波动（-3% ~ +5%）
            import random
            change = random.uniform(-0.03, 0.05)
            return cost_price * (1 + change)
        return None
    
    def check_stop_loss(self, code: str, position: Dict, current_price: float) -> Optional[Dict]:
        """
        检查止损（-8% 强制卖出）
        
        Returns:
            卖出信号（如果触发），否则 None
        """
        cost_price = position.get("cost_price", current_price)
        pnl_pct = (current_price - cost_price) / cost_price
        
        if pnl_pct <= self.SELL_CONFIG["stop_loss"]:
            return {
                "code": code,
                "name": position.get("name", code),
                "action": "sell",
                "reason": "止损",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "sell_ratio": 1.0,  # 清仓
                "priority": 1,  # 最高优先级
                "message": f"⚠️ 止损触发：{position.get('name', code)} 亏损 {pnl_pct*100:.2f}%"
            }
        
        return None
    
    def check_take_profit(self, code: str, position: Dict, current_price: float) -> Optional[Dict]:
        """
        检查止盈（分级卖出）
        
        +15% 卖 50%
        +20% 卖 80%
        +30% 清仓
        """
        cost_price = position.get("cost_price", current_price)
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 按止盈级别从高到低检查
        for threshold, sell_ratio in sorted(
            self.SELL_CONFIG["take_profit_levels"].items(),
            reverse=True
        ):
            if pnl_pct >= threshold:
                # 检查是否已经卖出过
                sell_record_key = f"{code}_tp_{threshold}"
                if hasattr(self, '_tp_sold') and sell_record_key in self._tp_sold:
                    continue
                
                return {
                    "code": code,
                    "name": position.get("name", code),
                    "action": "sell",
                    "reason": f"止盈 {threshold*100:.0f}%",
                    "price": current_price,
                    "pnl_pct": pnl_pct,
                    "sell_ratio": sell_ratio,
                    "priority": 2,
                    "message": f"🎯 止盈触发：{position.get('name', code)} 盈利 {pnl_pct*100:.2f}%，建议卖出 {sell_ratio*100:.0f}%"
                }
        
        return None
    
    def check_prediction_reversal(self, code: str, position: Dict, current_price: float) -> Optional[Dict]:
        """
        检查预测转空（置信度≥70%）
        """
        # 查找该股票的最新预测
        latest_prediction = None
        for pred_id, pred in self.predictions.get("active", {}).items():
            if pred.get("code") == code:
                if latest_prediction is None or pred.get("created_at", "") > latest_prediction.get("created_at", ""):
                    latest_prediction = pred
        
        if not latest_prediction:
            return None
        
        # 检查方向和置信度
        direction = latest_prediction.get("direction", "neutral")
        confidence = latest_prediction.get("confidence", 0)
        
        if direction == "down" and confidence >= self.SELL_CONFIG["prediction_reversal_confidence"]:
            cost_price = position.get("cost_price", current_price)
            pnl_pct = (current_price - cost_price) / cost_price
            
            return {
                "code": code,
                "name": position.get("name", code),
                "action": "sell",
                "reason": f"预测转空 (置信度 {confidence}%)",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "sell_ratio": 0.50,  # 卖出 50%
                "priority": 3,
                "message": f"📉 预测转空：{position.get('name', code)} 预测下跌，置信度 {confidence}%"
            }
        
        return None
    
    def check_time_stop(self, code: str, position: Dict, current_price: float) -> Optional[Dict]:
        """
        检查时间止损（5 日无涨幅）
        """
        buy_date_str = position.get("buy_date", "")
        if not buy_date_str:
            return None
        
        try:
            buy_date = datetime.strptime(buy_date_str, "%Y-%m-%d")
            days_held = (datetime.now() - buy_date).days
        except:
            return None
        
        # 持有超过 5 天
        if days_held < self.SELL_CONFIG["time_stop_days"]:
            return None
        
        cost_price = position.get("cost_price", current_price)
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 涨幅小于阈值
        if pnl_pct <= self.SELL_CONFIG["time_stop_min_gain"]:
            return {
                "code": code,
                "name": position.get("name", code),
                "action": "sell",
                "reason": f"时间止损 ({days_held}日无涨幅)",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "sell_ratio": 1.0,  # 清仓
                "priority": 4,
                "message": f"⏰ 时间止损：{position.get('name', code)} 持有 {days_held} 天，涨幅 {pnl_pct*100:.2f}%"
            }
        
        return None
    
    def check_trailing_stop(self, code: str, position: Dict, current_price: float) -> Optional[Dict]:
        """
        检查移动止盈（盈利>10% 后回撤 -5%）
        """
        cost_price = position.get("cost_price", current_price)
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 未达到触发条件（盈利>10%）
        if pnl_pct <= self.SELL_CONFIG["trailing_stop_trigger"]:
            return None
        
        # 更新最高价
        if code not in self.high_water_marks:
            self.high_water_marks[code] = current_price
        else:
            self.high_water_marks[code] = max(self.high_water_marks[code], current_price)
        
        # 计算从最高价的回撤
        high_price = self.high_water_marks[code]
        drawdown = (current_price - high_price) / high_price
        
        # 回撤超过阈值
        if drawdown <= self.SELL_CONFIG["trailing_stop_threshold"]:
            return {
                "code": code,
                "name": position.get("name", code),
                "action": "sell",
                "reason": f"移动止盈 (回撤 {drawdown*100:.2f}%)",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "sell_ratio": 1.0,  # 清仓
                "priority": 2,
                "message": f"🛡️ 移动止盈：{position.get('name', code)} 从高点回撤 {drawdown*100:.2f}%，当前盈利 {pnl_pct*100:.2f}%"
            }
        
        return None
    
    def _find_latest_prediction(self, code: str) -> Optional[str]:
        """
        查找与该股票相关的最新预测ID

        Returns:
            预测ID，如果没有找到则返回 None
        """
        # 查找该股票的最新预测
        latest_prediction = None
        latest_prediction_id = None

        for pred_id, pred in self.predictions.get("active", {}).items():
            if pred.get("code") == code:
                if latest_prediction is None or pred.get("created_at", "") > latest_prediction.get("created_at", ""):
                    latest_prediction = pred
                    latest_prediction_id = pred_id

        # 如果 active 中没有，检查 history
        if not latest_prediction_id:
            for pred in self.predictions.get("history", []):
                if pred.get("code") == code:
                    if latest_prediction is None or pred.get("created_at", "") > latest_prediction.get("created_at", ""):
                        latest_prediction = pred
                        latest_prediction_id = pred.get("id")

        return latest_prediction_id

    def check_risk_assessment(self, code: str, signal: Dict) -> Tuple[bool, str, Optional[str]]:
        """
        【修复 P0-4】风控检查

        Returns:
            (passed, message, risk_level) - 是否通过、消息、风险等级
        """
        # 1. 检查持仓集中度
        total_positions_value = sum(
            pos.get("shares", 0) * pos.get("cost_price", 0)
            for pos in self.positions.values()
        )
        total_capital = self.cash + total_positions_value

        if total_capital == 0:
            return False, "无法计算总资金", "high"

        # 计算当前行业分布
        industry_positions = {}
        for pos_code, pos in self.positions.items():
            stock_info = self._get_stock_info(pos_code)
            industry = stock_info.get("industry", "unknown")
            if industry not in industry_positions:
                industry_positions[industry] = 0
            industry_positions[industry] += pos.get("shares", 0) * pos.get("cost_price", 0)

        # 检查新股票的行业
        new_stock_info = self._get_stock_info(code)
        new_industry = new_stock_info.get("industry", "unknown")

        # 获取交易金额（修复 bug）
        price = signal.get("price") if isinstance(signal, dict) else 0
        shares = signal.get("shares") if isinstance(signal, dict) else 0
        new_trade_amount = price * shares

        if new_industry in industry_positions:
            industry_value = industry_positions[new_industry] + new_trade_amount
            industry_ratio = industry_value / total_capital
            if industry_ratio > self.RISK_CONFIG["max_industry_concentration"]:
                return False, f"行业集中度过高 ({new_industry}: {industry_ratio*100:.1f}%)", "high"

        # 2. 检查单笔交易金额
        trade_ratio = new_trade_amount / total_capital
        if trade_ratio > self.RISK_CONFIG["max_single_trade"]:
            return False, f"单笔交易金额过大 ({trade_ratio*100:.1f}%)", "medium"

        # 3. 检查单只股票仓位
        if code in self.positions:
            existing_value = self.positions[code].get("shares", 0) * self.positions[code].get("cost_price", 0)
            total_value = existing_value + new_trade_amount
            position_ratio = total_value / total_capital
            if position_ratio > self.RISK_CONFIG["max_single_position"]:
                return False, f"单只股票仓位过大 ({position_ratio*100:.1f}%)", "medium"

        # 4. 检查单日亏损（从交易历史统计）
        today = datetime.now().strftime("%Y-%m-%d")
        today_trades = [
            t for t in self.trade_history
            if t.get("timestamp", "").startswith(today) and t.get("type") == "sell"
        ]

        daily_loss = sum(
            t.get("sold_shares", 0) * t.get("price", 0) * min(t.get("pnl_pct", 0), 0)
            for t in today_trades
        )

        if daily_loss <= -self.RISK_CONFIG["max_daily_loss"] * total_capital:
            loss_pct = daily_loss / total_capital * 100
            return False, f"已达到单日亏损限制 ({loss_pct:.1f}%)", "very_high"

        # 5. 检查置信度（如果有预测）
        prediction_id = self._find_latest_prediction(code)
        if prediction_id:
            for pred in self.predictions.get("active", {}).values():
                if pred.get("id") == prediction_id:
                    confidence = pred.get("confidence", 50)
                    if confidence < 50:
                        return False, f"预测置信度过低 ({confidence}%)", "medium"
                    break

        # 通过风控检查
        return True, "风控检查通过", "low"

    def _get_stock_info(self, code: str) -> Dict:
        """获取股票信息"""
        # 先查持仓
        if code in self.positions:
            return {
                "industry": self.positions[code].get("industry", "unknown"),
            }

        # 再查自选股
        watchlist = load_json(WATCHLIST_FILE, {})
        if code in watchlist:
            stock_info = watchlist[code]
            return {
                "industry": stock_info.get("industry", "unknown"),
            }

        return {"industry": "unknown"}

    def save_risk_assessment(self, code: str, risk_level: str, notes: str):
        """保存风控评估到数据库"""
        try:
            conn = sqlite3.connect(str(DATABASE_FILE))
            cursor = conn.cursor()

            # 获取或创建 proposal
            cursor.execute("""
                INSERT OR IGNORE INTO proposals
                (symbol, name, direction, status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (code, "", "buy", "pending", datetime.now().isoformat()))

            proposal_id = cursor.lastrowid
            if proposal_id == 0:
                cursor.execute("""
                    SELECT id FROM proposals WHERE symbol = ? ORDER BY id DESC LIMIT 1
                """, (code,))
                proposal_id = cursor.fetchone()[0]

            # 保存风控评估
            cursor.execute("""
                INSERT INTO risk_assessment
                (proposal_id, symbol, risk_level, suggested_position, max_position,
                 var_95, volatility, industry_concentration, correlation_market, risk_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proposal_id,
                code,
                risk_level,
                0.15,  # 建议仓位
                self.RISK_CONFIG["max_single_position"],  # 最大仓位
                0.05,  # 95% VaR
                0.15,  # 波动率
                0.30,  # 行业集中度
                0.80,  # 与市场相关性
                notes
            ))

            conn.commit()
            conn.close()
            logger.info(f"💾 风控评估已保存: {code} - {risk_level}")

        except Exception as e:
            logger.error(f"保存风控评估失败: {e}")

    def execute_sell(self, signal: Dict) -> bool:
        """执行卖出"""
        code = signal["code"]

        if code not in self.positions:
            logger.warning(f"无持仓: {code}")
            return False

        position = self.positions[code]
        sell_ratio = signal["sell_ratio"]

        # 查找关联的预测ID
        prediction_id = self._find_latest_prediction(code)

        # 记录交易
        trade_record = {
            "type": "sell",
            "code": code,
            "name": signal["name"],
            "price": signal["price"],
            "pnl_pct": signal["pnl_pct"],
            "reason": signal["reason"],
            "sell_ratio": sell_ratio,
            "shares": position.get("shares", 0),
            "sold_shares": int(position.get("shares", 0) * sell_ratio),
            "prediction_id": prediction_id,  # 添加预测ID关联
            "timestamp": datetime.now().isoformat(),
        }
        
        self.trade_history.append(trade_record)
        
        # 更新持仓
        if sell_ratio >= 1.0:
            del self.positions[code]
            logger.info(f"清仓: {signal['name']} ({code})")
        else:
            self.positions[code]["shares"] = int(position.get("shares", 0) * (1 - sell_ratio))
            logger.info(f"减仓: {signal['name']} ({code})，卖出 {sell_ratio*100:.0f}%")

        # 更新现金
        sell_amount = trade_record["sold_shares"] * signal["price"]
        self.cash += sell_amount
        logger.info(f"卖出金额: ¥{sell_amount:,.0f}，现金余额: ¥{self.cash:,.0f}")
        
        # 保存数据
        self._save_data()
        
        # 发送飞书通知
        if HAS_FEISHU:
            try:
                profit = signal["pnl_pct"] * position.get("shares", 0) * signal["price"]
                send_trade_notification(
                    action="SELL",
                    code=code,
                    name=signal["name"],
                    shares=trade_record["sold_shares"],
                    price=signal["price"],
                    profit=profit
                )
            except Exception as e:
                logger.warning(f"飞书通知发送失败: {e}")
        
        return True
    
    def scan_sell_signals(self) -> List[Dict]:
        """扫描卖出信号"""
        logger.info("\n" + "="*60)
        logger.info("📊 扫描卖出信号...")
        logger.info("="*60)
        
        signals = []
        
        for code, position in self.positions.items():
            current_price = self.get_realtime_price(code)
            if not current_price:
                logger.warning(f"无法获取价格: {code}")
                continue
            
            # 1. 止损检查（最高优先级）
            signal = self.check_stop_loss(code, position, current_price)
            if signal:
                signals.append(signal)
                continue  # 触发止损后不再检查其他条件
            
            # 2. 止盈检查
            signal = self.check_take_profit(code, position, current_price)
            if signal:
                signals.append(signal)
                continue
            
            # 3. 移动止盈检查
            signal = self.check_trailing_stop(code, position, current_price)
            if signal:
                signals.append(signal)
                continue
            
            # 4. 预测转空检查
            signal = self.check_prediction_reversal(code, position, current_price)
            if signal:
                signals.append(signal)
                continue
            
            # 5. 时间止损检查
            signal = self.check_time_stop(code, position, current_price)
            if signal:
                signals.append(signal)
        
        # 按优先级排序
        signals.sort(key=lambda x: x["priority"])
        
        return signals
    
    def run(self, auto_execute: bool = False):
        """运行卖出检查"""
        logger.info("\n" + "="*60)
        logger.info("🤖 自动交易系统 v3 - 卖出逻辑")
        logger.info(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        # 扫描信号
        signals = self.scan_sell_signals()
        
        if not signals:
            logger.info("\n✅ 无卖出信号")
            return
        
        # 显示信号
        logger.info(f"\n发现 {len(signals)} 个卖出信号:")
        for i, signal in enumerate(signals, 1):
            logger.info(f"\n[{i}] {signal['message']}")
            logger.info(f"    代码: {signal['code']}")
            logger.info(f"    名称: {signal['name']}")
            logger.info(f"    价格: ¥{signal['price']:.2f}")
            logger.info(f"    盈亏: {signal['pnl_pct']*100:+.2f}%")
            logger.info(f"    原因: {signal['reason']}")
            logger.info(f"    卖出比例: {signal['sell_ratio']*100:.0f}%")
        
        # 执行卖出
        if auto_execute:
            logger.info("\n" + "="*60)
            logger.info("执行卖出...")
            for signal in signals:
                self.execute_sell(signal)
            logger.info("✅ 卖出执行完成")
        else:
            logger.info("\n💡 提示: 使用 --execute 参数自动执行卖出")
        
        logger.info("\n" + "="*60)
        
        return signals


def main():
    import argparse

    parser = argparse.ArgumentParser(description="自动交易系统 v3 - 卖出逻辑")
    parser.add_argument("--execute", action="store_true", help="自动执行卖出")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行（不实际卖出）")
    parser.add_argument("--buy", action="store_true", help="执行买入逻辑")
    parser.add_argument("--sell", action="store_true", help="执行卖出逻辑")

    args = parser.parse_args()

    trader = AutoTraderV3()

    # 处理买入逻辑
    if args.buy:
        logger.info("执行买入逻辑...")
        # 扫描观察池中的高置信度预测
        buy_signals = []
        watchlist = load_json(WATCHLIST_FILE, {})

        for code, stock in watchlist.items():
            # code 已经是股票代码，stock 是字典包含 name, industry 等信息

            # 查找该股票的预测
            for pred_id, pred in trader.predictions.get("active", {}).items():
                if pred.get("code") == code:
                    confidence = pred.get("confidence", 0)
                    # 置信度 ≥ 80 且不在持仓中
                    if confidence >= 80 and code not in trader.positions:
                        price = trader.get_realtime_price(code)
                        if price:
                            buy_signals.append({
                                "code": code,
                                "name": stock.get("name", code),
                                "price": price,
                                "confidence": confidence,
                                "reasons": stock.get("reason", stock.get("added_reason", "")),
                            })

        # 按置信度排序
        buy_signals.sort(key=lambda x: x["confidence"], reverse=True)

        if buy_signals:
            logger.info(f"\n发现 {len(buy_signals)} 个买入信号:")
            for i, signal in enumerate(buy_signals, 1):
                logger.info(f"\n[{i}] {signal['name']} ({signal['code']})")
                logger.info(f"    价格: ¥{signal['price']:.2f}")
                logger.info(f"    置信度: {signal['confidence']}%")
                logger.info(f"    理由: {signal['reasons']}")

            # 执行买入
            if args.execute and not args.dry_run:
                logger.info("\n执行买入...")
                for signal in buy_signals[:2]:  # 最多买入2只
                    # 【修复 P0-4】执行前进行风控检查
                    passed, risk_msg, risk_level = trader.check_risk_assessment(signal['code'], signal)

                    if not passed:
                        logger.warning(f"⚠️ {signal['name']}: {risk_msg}")
                        trader.save_risk_assessment(signal['code'], risk_level, risk_msg)
                        continue  # 跳过该交易

                    logger.info(f"✅ {signal['name']}: 风控检查通过 - {risk_level}")

                    # 计算买入数量（每只5万）
                    buy_amount = 50000
                    shares = int(buy_amount / signal['price'])
                    if shares > 0:
                        trader.positions[signal['code']] = {
                            "name": signal['name'],
                            "cost_price": signal['price'],
                            "shares": shares,
                            "buy_date": datetime.now().strftime("%Y-%m-%d"),
                            "buy_reason": signal['reasons'],
                        }
                        trader.cash -= shares * signal['price']

                        # 保存风控评估
                        trader.save_risk_assessment(signal['code'], risk_level, risk_msg)

                        # 查找关联的预测ID（修复 P0-3）
                        prediction_id = trader._find_latest_prediction(signal['code'])

                        # 记录交易
                        trader.trade_history.append({
                            "type": "buy",
                            "code": signal['code'],
                            "name": signal['name'],
                            "price": signal['price'],
                            "shares": shares,
                            "reason": signal['reasons'],
                            "prediction_id": prediction_id,  # 添加预测ID关联
                            "timestamp": datetime.now().isoformat(),
                        })

                        logger.info(f"买入: {signal['name']} {shares}股 @¥{signal['price']:.2f}")

                trader._save_data()
                logger.info("✅ 买入执行完成")
            else:
                logger.info("\n💡 提示: 使用 --execute 参数自动执行买入")
        else:
            logger.info("\n✅ 无买入信号")
        return

    # 处理卖出逻辑
    if args.sell or (not args.buy and not args.sell):
        # 运行卖出检查
        auto_execute = args.execute and not args.dry_run
        signals = trader.run(auto_execute=auto_execute)

        # 返回退出码
        if signals:
            return 0  # 有信号
        else:
            return 1  # 无信号


if __name__ == "__main__":
    sys.exit(main())
