#!/usr/bin/env python3
"""
回测系统 - 验证策略有效性

功能：
1. 历史数据加载（baostock，至少 3 年）
2. 策略回测引擎
3. 绩效指标计算（夏普比率、最大回撤等）
4. 回测报告生成
5. 样本外测试
"""

import sys
import os
import json
import math
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass, asdict

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, PROJECT_ROOT)

# 配置
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'backverifyer.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def _format_percent_points(value: float, digits: int = 1) -> str:
    return f"{float(value or 0.0):.{digits}f}%"


def _format_ratio(value: float) -> str:
    return "∞" if isinstance(value, float) and math.isinf(value) else f"{float(value or 0.0):.2f}"


@dataclass
class Trade:
    """交易记录"""
    date: str
    stock_code: str
    stock_name: str
    action: str  # buy/sell
    price: float
    shares: int
    value: float
    commission: float = 0.0003  # 万分之三手续费
    slippage: float = 0.001  # 0.1% 滑点
    cost_basis: float = 0.0
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0


@dataclass
class Position:
    """持仓记录"""
    stock_code: str
    stock_name: str
    shares: int
    avg_cost: float
    current_price: float
    market_value: float
    pnl: float
    pnl_pct: float


@dataclass
class BackverifyResult:
    """回测结果"""
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    trades: List[Trade]


class Backverifyer:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.portfolio_values: List[float] = []
        self.start_date = None
        self.end_date = None
    
    def get_historical_data(self, stock_code: str, start_date: str, end_date: str) -> List[Dict]:
        """
        获取历史数据 - 使用 baostock + 重试机制
        
        Args:
            stock_code: 股票代码 (格式：sh.600459 或 sz.000001)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        
        Returns:
            历史数据列表
        """
        import time
        
        # 重试机制：最多 3 次
        for attempt in range(3):
            try:
                import baostock as bs
                
                # 登录
                bs.login()
                
                # 获取历史数据
                rs = bs.query_history_k_data_plus(
                    stock_code,
                    'date,open,high,low,close,volume',
                    start_date=start_date,
                    end_date=end_date,
                    frequency='d',
                    adjustflag='3'  # 不复权
                )
                
                if rs.error_msg != 'success':
                    logger.warning(f"Baostock 查询失败：{rs.error_msg}")
                    bs.logout()
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    return []
                
                # 转换为标准格式
                history = []
                while rs.next():
                    row = rs.get_row_data()
                    history.append({
                        "date": row[0],  # date
                        "open": float(row[1]) if row[1] else 0,  # open
                        "high": float(row[2]) if row[2] else 0,  # high
                        "low": float(row[3]) if row[3] else 0,  # low
                        "close": float(row[4]) if row[4] else 0,  # close
                        "volume": float(row[5]) if row[5] else 0,  # volume
                    })
                
                bs.logout()
                return history
                
            except Exception as e:
                logger.warning(f"获取数据失败 (attempt {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    return []
        
        return []
    
    def get_stock_info(self, stock_code: str) -> Dict:
        """获取股票信息"""
        try:
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": stock_code.replace(".", ""),
                "fields": "f58"
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    return {"name": data["data"].get("f58", "")}
            return {"name": ""}
        except Exception as e:
            return {"name": ""}
    
    def buy(self, date: str, stock_code: str, price: float, shares: int):
        """
        买入操作
        
        Args:
            date: 交易日期
            stock_code: 股票代码
            price: 买入价格
            shares: 买入数量
        """
        if shares <= 0:
            return
        
        # 计算成本（含手续费和滑点）
        value = price * shares
        commission = value * 0.0003  # 万分之三
        slippage_cost = value * 0.001  # 0.1% 滑点
        total_cost = value + commission + slippage_cost
        
        # 检查资金是否足够
        if total_cost > self.capital:
            logger.warning(f"资金不足：需要{total_cost:.2f}, 可用{self.capital:.2f}")
            return
        
        # 更新资金
        self.capital -= total_cost
        
        # 更新持仓
        if stock_code in self.positions:
            pos = self.positions[stock_code]
            total_shares = pos.shares + shares
            total_cost = pos.avg_cost * pos.shares + price * shares
            pos.avg_cost = total_cost / total_shares
            pos.shares = total_shares
        else:
            stock_info = self.get_stock_info(stock_code)
            self.positions[stock_code] = Position(
                stock_code=stock_code,
                stock_name=stock_info["name"],
                shares=shares,
                avg_cost=price,
                current_price=price,
                market_value=value,
                pnl=0,
                pnl_pct=0
            )
        
        # 记录交易
        trade = Trade(
            date=date,
            stock_code=stock_code,
            stock_name=self.positions[stock_code].stock_name,
            action="buy",
            price=price,
            shares=shares,
            value=value,
            commission=commission + slippage_cost,
            cost_basis=value,
        )
        self.trades.append(trade)
        
        logger.info(f"买入：{stock_code} {shares}股 @ {price:.2f}")
    
    def sell(self, date: str, stock_code: str, price: float, shares: int = None):
        """
        卖出操作
        
        Args:
            date: 交易日期
            stock_code: 股票代码
            price: 卖出价格
            shares: 卖出数量（None 表示全部卖出）
        """
        if stock_code not in self.positions:
            logger.warning(f"无持仓：{stock_code}")
            return
        
        pos = self.positions[stock_code]
        
        if shares is None:
            shares = pos.shares
        
        if shares <= 0 or shares > pos.shares:
            logger.warning(f"卖出数量无效：{shares}, 持仓：{pos.shares}")
            return
        
        # 计算收入（扣除手续费和滑点）
        value = price * shares
        commission = value * 0.0003
        slippage_cost = value * 0.001
        net_income = value - commission - slippage_cost
        
        # 更新资金
        self.capital += net_income
        
        # 更新持仓
        pos.shares -= shares
        pnl = (price - pos.avg_cost) * shares - commission - slippage_cost
        cost_basis = pos.avg_cost * shares
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0
        if pos.shares == 0:
            # 记录交易
            trade = Trade(
                date=date,
                stock_code=stock_code,
                stock_name=pos.stock_name,
                action="sell",
                price=price,
                shares=shares,
                value=value,
                commission=commission + slippage_cost,
                cost_basis=cost_basis,
                realized_pnl=pnl,
                realized_pnl_pct=pnl_pct,
            )
            self.trades.append(trade)
            
            del self.positions[stock_code]
            logger.info(f"卖出：{stock_code} {shares}股 @ {price:.2f}, 盈亏：{pnl:.2f} ({pnl_pct:+.2f}%)")
        else:
            # 部分卖出，记录交易
            trade = Trade(
                date=date,
                stock_code=stock_code,
                stock_name=pos.stock_name,
                action="sell",
                price=price,
                shares=shares,
                value=value,
                commission=commission + slippage_cost,
                cost_basis=cost_basis,
                realized_pnl=pnl,
                realized_pnl_pct=pnl_pct,
            )
            self.trades.append(trade)
            logger.info(f"部分卖出：{stock_code} {shares}股 @ {price:.2f}")
    
    def update_portfolio_value(self, current_prices: Dict[str, float]):
        """更新组合市值"""
        total_value = self.capital
        
        for code, pos in self.positions.items():
            if code in current_prices:
                pos.current_price = current_prices[code]
                pos.market_value = pos.current_price * pos.shares
                pos.pnl = (pos.current_price - pos.avg_cost) * pos.shares
                pos.pnl_pct = (pos.current_price - pos.avg_cost) / pos.avg_cost * 100
                total_value += pos.market_value
        
        self.portfolio_values.append(total_value)
    
    def calculate_metrics(self) -> Dict:
        """计算绩效指标"""
        if not self.portfolio_values:
            return {}
        
        # 基础指标
        final_value = self.portfolio_values[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        # 年化收益
        days = len(self.portfolio_values)
        years = days / 252  # 交易日
        if years > 0:
            annual_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100
        else:
            annual_return = 0
        
        # 最大回撤
        peak = self.portfolio_values[0]
        max_drawdown = 0
        for value in self.portfolio_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 夏普比率（简化版，假设无风险利率 3%）
        if len(self.portfolio_values) > 1:
            daily_returns = []
            for i in range(1, len(self.portfolio_values)):
                ret = (self.portfolio_values[i] - self.portfolio_values[i-1]) / self.portfolio_values[i-1]
                daily_returns.append(ret)
            
            if daily_returns:
                import statistics
                avg_return = statistics.mean(daily_returns)
                std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 1
                sharpe_ratio = (avg_return * 252 - 0.03) / (std_return * (252 ** 0.5))
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        sell_trades = [t for t in self.trades if t.action == "sell"]
        winning_trades = [t for t in sell_trades if t.realized_pnl > 0]
        losing_trades = [t for t in sell_trades if t.realized_pnl < 0]
        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0
        
        # 盈亏比
        gross_profit = sum(t.realized_pnl for t in winning_trades)
        gross_loss = abs(sum(t.realized_pnl for t in losing_trades))
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
        
        return {
            "final_value": final_value,
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": len([t for t in self.trades if t.action == "sell"]),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        }
    
    def run_backverify(self, strategy_func, stock_list: List[str], 
                    start_date: str, end_date: str) -> BackverifyResult:
        """
        运行回测
        
        Args:
            strategy_func: 策略函数 (date, stock_data, portfolio) -> action
            stock_list: 股票列表
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            回测结果
        """
        logger.info(f"开始回测：{start_date} 至 {end_date}, 股票数={len(stock_list)}")
        
        self.start_date = start_date
        self.end_date = end_date
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.portfolio_values = []
        
        # 获取历史数据
        all_data = {}
        for stock_code in stock_list:
            history = self.get_historical_data(stock_code, start_date, end_date)
            if history:
                all_data[stock_code] = history
                logger.info(f"获取 {stock_code} 数据：{len(history)}天")
        
        if not all_data:
            logger.error("无历史数据")
            return None
        
        # 按日期遍历
        dates = sorted(set(d for data in all_data.values() for d in [dd["date"] for dd in data]))
        
        for date in dates:
            # 获取当日数据
            daily_data = {}
            for code, history in all_data.items():
                for d in history:
                    if d["date"] == date:
                        daily_data[code] = d
                        break
            
            if not daily_data:
                continue
            
            # 执行策略
            actions = strategy_func(date, daily_data, {
                "capital": self.capital,
                "positions": self.positions,
            })
            
            # 执行交易
            for action in actions:
                if action["type"] == "buy":
                    self.buy(date, action["code"], daily_data[action["code"]]["close"], action["shares"])
                elif action["type"] == "sell":
                    self.sell(date, action["code"], daily_data[action["code"]]["close"], action.get("shares"))
            
            # 更新组合市值
            current_prices = {code: data["close"] for code, data in daily_data.items()}
            self.update_portfolio_value(current_prices)
        
        # 计算指标
        metrics = self.calculate_metrics()
        
        result = BackverifyResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=metrics.get("final_value", 0),
            total_return=metrics.get("total_return", 0),
            annual_return=metrics.get("annual_return", 0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0),
            max_drawdown=metrics.get("max_drawdown", 0),
            win_rate=metrics.get("win_rate", 0),
            profit_factor=metrics.get("profit_factor", 0),
            total_trades=metrics.get("total_trades", 0),
            winning_trades=metrics.get("winning_trades", 0),
            losing_trades=metrics.get("losing_trades", 0),
            avg_win=metrics.get("avg_win", 0),
            avg_loss=metrics.get("avg_loss", 0),
            trades=self.trades
        )
        
        logger.info(f"回测完成：总收益={result.total_return:.2f}%, 年化={result.annual_return:.2f}%, "
                   f"夏普={result.sharpe_ratio:.2f}, 最大回撤={result.max_drawdown:.2f}%")
        
        return result
    
    def generate_report(self, result: BackverifyResult, output_file: str = None):
        """生成回测报告"""
        if not result:
            return
        
        report = f"""
# 📊 回测报告

**回测期间**：{result.start_date} 至 {result.end_date}
**初始资金**：¥{result.initial_capital:,.2f}
**最终资金**：¥{result.final_capital:,.2f}

---

## 📈 核心指标

| 指标 | 数值 | 评价 |
|------|------|------|
| 总收益率 | {result.total_return:+.2f}% | {"✅ 优秀" if result.total_return > 20 else "⚠️ 一般" if result.total_return > 0 else "❌ 亏损"} |
| 年化收益 | {result.annual_return:+.2f}% | {"✅ >20%" if result.annual_return > 20 else "⚠️ 10-20%" if result.annual_return > 10 else "❌ <10%"} |
| 夏普比率 | {result.sharpe_ratio:.2f} | {"✅ >1.5" if result.sharpe_ratio > 1.5 else "⚠️ 1.0-1.5" if result.sharpe_ratio > 1 else "❌ <1"} |
| 最大回撤 | {result.max_drawdown:.2f}% | {"✅ <15%" if result.max_drawdown < 15 else "⚠️ 15-25%" if result.max_drawdown < 25 else "❌ >25%"} |
| 胜率 | {result.win_rate:.1f}% | {"✅ >60%" if result.win_rate > 60 else "⚠️ 50-60%" if result.win_rate > 50 else "❌ <50%"} |
| 盈亏比 | {_format_ratio(result.profit_factor)} | {"✅ >2" if result.profit_factor > 2 else "⚠️ 1.5-2" if result.profit_factor > 1.5 else "❌ <1.5"} |

---

## 📊 交易统计

- 总交易次数：{result.total_trades}
- 盈利交易：{result.winning_trades}
- 亏损交易：{result.losing_trades}
- 平均盈利：¥{result.avg_win:,.2f}
- 平均亏损：¥{result.avg_loss:,.2f}

---

## 💡 评估结论

"""
        
        # 评估结论
        score = 0
        if result.total_return > 20: score += 2
        elif result.total_return > 0: score += 1
        
        if result.sharpe_ratio > 1.5: score += 2
        elif result.sharpe_ratio > 1: score += 1
        
        if result.max_drawdown < 15: score += 2
        elif result.max_drawdown < 25: score += 1
        
        if result.win_rate > 60: score += 2
        elif result.win_rate > 50: score += 1
        
        if score >= 7:
            conclusion = "✅ **策略优秀**：各项指标良好，可以考虑实盘"
        elif score >= 5:
            conclusion = "⚠️ **策略一般**：需要进一步优化"
        else:
            conclusion = "❌ **策略不佳**：建议重新设计"
        
        report += conclusion + "\n"
        
        # 保存报告
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存：{output_file}")
        
        print(report)
        
        return result
    
    def save_to_learning(self, result: BackverifyResult):
        """
        回测结果自动写入学习系统（2026-03-07 新增）
        
        功能：
        1. 写入 daily_learning_log.json
        2. 提取教训 → memory.md（如指标低于阈值）
        3. 建议策略调整
        """
        import json
        from datetime import datetime
        from pathlib import Path
        
        learning_dir = Path(PROJECT_ROOT) / "learning"
        learning_log = learning_dir / "daily_learning_log.json"
        memory_file = learning_dir / "memory.md"
        
        # 1. 写入学习日志
        log_entry = {
            "date": datetime.now().isoformat(),
            "type": "weekly_backtest",
            "period": f"{result.start_date} to {result.end_date}",
            "trading_days": result.total_trading_days if hasattr(result, 'total_trading_days') else 0,
            "stock": result.stock_code if hasattr(result, 'stock_code') else "unknown",
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
            "total_return": result.total_return,
            "annual_return": result.annual_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "profit_loss_ratio": result.profit_factor,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "avg_profit": result.avg_win,
            "avg_loss": result.avg_loss,
            "conclusion": "策略需要优化" if result.sharpe_ratio < 1 else "策略良好",
            "strengths": [],
            "weaknesses": [],
            "lessons": []
        }
        
        # 分析优缺点
        if result.win_rate > 60:
            log_entry["strengths"].append(f"胜率高 ({_format_percent_points(result.win_rate, 1)})")
        if result.max_drawdown < 15:
            log_entry["strengths"].append(f"回撤控制好 ({_format_percent_points(result.max_drawdown, 2)})")
        
        if result.annual_return < 10:
            log_entry["weaknesses"].append(f"收益率偏低 (年化 {_format_percent_points(result.annual_return, 2)})")
        if result.sharpe_ratio < 1:
            log_entry["weaknesses"].append(f"夏普比率低 ({result.sharpe_ratio:.2f})")
        if result.profit_factor < 1.5:
            log_entry["weaknesses"].append(f"盈亏比不足 ({_format_ratio(result.profit_factor)})")
        
        # 提取教训
        if result.profit_factor < 1.5:
            log_entry["lessons"].append(f"需要提高盈亏比：当前{_format_ratio(result.profit_factor)}，目标>1.5")
            log_entry["lessons"].append("建议：延长止盈区间，让利润奔跑")
        if result.sharpe_ratio < 1:
            log_entry["lessons"].append(f"夏普比率低说明风险调整后收益差")
            log_entry["lessons"].append("建议：降低仓位波动或提高收益")
        
        # 读取现有日志
        logs = []
        if learning_log.exists():
            with open(learning_log, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        # 只保留最近 30 条
        if len(logs) > 30:
            logs = logs[-30:]
        
        with open(learning_log, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 学习日志已更新：{learning_log}")
        
        # 2. 如指标低于阈值，更新 memory.md
        if result.sharpe_ratio < 0.5 or result.profit_factor < 1.3 or result.annual_return < 5:
            self._update_memory_with_lessons(log_entry, memory_file)
        
        # 3. 发送飞书通知
        self._notify_learning(log_entry)
    
    def _update_memory_with_lessons(self, log_entry: dict, memory_file):
        """更新记忆文件 with 教训"""
        if not memory_file.exists():
            return
        
        with open(memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否已存在相同教训
        date_str = datetime.now().strftime('%Y-%m-%d')
        marker = f"### [{date_str}] 周回测"
        
        if marker in content:
            print(f"⚠️ 今日教训已存在，跳过")
            return
        
        # 插入教训到"失败教训"部分
        insert_marker = "## ✅ 成功经验"
        if insert_marker not in content:
            print(f"⚠️ 未找到插入位置")
            return
        
        lessons_text = "\n---\n\n"
        lessons_text += f"### [{date_str}] 周回测：盈亏比不足\n\n"
        lessons_text += f"**问题**：盈亏比仅 {_format_ratio(log_entry['profit_loss_ratio'])}（目标>1.5）\n"
        if log_entry.get('win_rate', 0) > 60:
            lessons_text += f"- 胜率 {_format_percent_points(log_entry['win_rate'], 1)} 很高，但赚得少\n"
        lessons_text += f"- 平均盈利¥{log_entry['avg_profit']:,.0f}，平均亏损¥{log_entry['avg_loss']:,.0f}\n"
        lessons_text += f"- 赚小钱太多，单笔盈利不够\n\n"
        lessons_text += f"**教训**：高胜率≠高收益，需要提高盈亏比\n\n"
        lessons_text += f"**改进**：\n"
        lessons_text += f"1. 延长止盈区间：+15-25% → +20-30%\n"
        lessons_text += f"2. 让利润奔跑：盈利>10% 后移动止损\n"
        lessons_text += f"3. 减少频繁交易：只做高置信度机会\n"
        
        if log_entry['sharpe_ratio'] < 0.5:
            lessons_text += f"\n---\n\n"
            lessons_text += f"### [{date_str}] 周回测：夏普比率极低\n\n"
            lessons_text += f"**问题**：夏普比率 {log_entry['sharpe_ratio']:.2f}（目标>1）\n\n"
            lessons_text += f"**教训**：风险调整后收益差，收益波动大\n\n"
            lessons_text += f"**改进**：\n"
            lessons_text += f"1. 降低仓位波动\n"
            lessons_text += f"2. 提高单笔收益：抓大趋势\n"
            lessons_text += f"3. 优化持仓结构：降低相关性\n"
        
        lessons_text += "\n"
        
        content = content.replace(insert_marker, lessons_text + insert_marker)
        
        # 更新最后更新时间
        content = content.replace(
            '*最后更新：',
            f'*最后更新：{date_str} '
        )
        
        with open(memory_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 记忆已更新：{memory_file}")
    
    def _notify_learning(self, log_entry: dict):
        """发送飞书通知"""
        try:
            sys.path.insert(0, PROJECT_ROOT)
            from feishu_notifier import send_feishu_message
            
            title = "📊 回测学习完成"
            content = f"""
**回测期间**：{log_entry['period']}
**结论**：{log_entry['conclusion']}

**关键指标**：
- 胜率：{_format_percent_points(log_entry['win_rate'], 1)}
- 盈亏比：{_format_ratio(log_entry['profit_loss_ratio'])}
- 夏普比率：{log_entry['sharpe_ratio']:.2f}
- 年化收益：{_format_percent_points(log_entry['annual_return'], 2)}

**教训已写入学习系统**：
"""
            for lesson in log_entry.get('lessons', [])[:3]:
                content += f"- {lesson}\n"
            
            send_feishu_message(title=title, content=content, level='info')
            print("✅ 飞书通知已发送")
        except Exception as e:
            print(f"⚠️ 飞书通知失败：{e}")
    
    def stress_test(self):
        """压力测试 - 模拟极端市场场景"""
        print("\n🧪 压力测试")
        print("="*60)
        
        # 测试场景
        scenarios = [
            ("2015 年股灾", "2015-06-01", "2015-09-01", -0.30),
            ("2018 年贸易战", "2018-03-01", "2018-12-01", -0.25),
            ("2020 年疫情", "2020-01-01", "2020-03-01", -0.20),
        ]
        
        print("\n测试极端市场场景下的策略表现：\n")
        
        summary_lines = ["极端市场场景测试结果：", ""]

        for scenario_name, start, end, expected_drop in scenarios:
            print(f"场景：{scenario_name} ({start} 至 {end})")
            print(f"预期跌幅：{expected_drop:.0%}")
            
            # 获取历史数据
            data = self.get_historical_data("sh.600459", start, end)
            if not data:
                print(f"  ❌ 无法获取数据，跳过\n")
                continue
            
            # 简单回测：期初买入，期末卖出
            start_price = data[0]['close']
            end_price = data[-1]['close']
            actual_return = (end_price - start_price) / start_price
            
            print(f"  期初价格：¥{start_price:.2f}")
            print(f"  期末价格：¥{end_price:.2f}")
            print(f"  实际收益：{actual_return:.2%}")
            
            # 评估
            if actual_return > expected_drop:
                print(f"  ✅ 跑赢预期（跌幅小于{expected_drop:.0%}）")
                verdict = "跑赢预期"
            else:
                print(f"  ⚠️ 未跑赢预期")
                verdict = "未跑赢预期"
            print()
            summary_lines.append(
                f"- {scenario_name}: 实际收益 {actual_return:.2%} | 预期阈值 {expected_drop:.0%} | {verdict}"
            )
        
        print("="*60)
        print("✅ 压力测试完成")
        print("\n💡 建议：在极端市场下保持低仓位，严格执行止损")

        try:
            sys.path.insert(0, PROJECT_ROOT)
            from feishu_notifier import send_feishu_message

            summary_lines.append("")
            summary_lines.append("建议：在极端市场下保持低仓位，严格执行止损。")
            send_feishu_message(
                title=f"🧪 压力测试完成 - {datetime.now().strftime('%Y-%m-%d')}",
                content="\n".join(summary_lines),
                level="info",
            )
            print("✅ 飞书通知已发送")
        except Exception as exc:
            print(f"⚠️ 飞书通知失败：{exc}")


# 全局变量用于跟踪买入日期（简单策略示例）
_buy_dates = {}

def simple_strategy(date: str, daily_data: Dict, portfolio: Dict) -> List[Dict]:
    """
    简单策略示例：买入持有 10 天后卖出
    
    实际应用中应该替换为复杂的选股策略
    """
    global _buy_dates
    actions = []
    
    from datetime import datetime, timedelta
    
    # 如果没有持仓且资金充足，买入
    if len(portfolio["positions"]) == 0 and portfolio["capital"] > 10000:
        for code, data in daily_data.items():
            actions.append({
                "type": "buy",
                "code": code,
                "shares": 1000,
            })
            _buy_dates[code] = date
            break
    
    # 如果有持仓，检查是否持有超过 10 天
    for code, pos in list(portfolio["positions"].items()):
        if code in _buy_dates:
            buy_date = datetime.strptime(_buy_dates[code], "%Y-%m-%d")
            current_date = datetime.strptime(date, "%Y-%m-%d")
            if (current_date - buy_date).days >= 10:
                # 卖出
                actions.append({
                    "type": "sell",
                    "code": code,
                    "shares": pos.shares,
                })
                del _buy_dates[code]
    
    return actions


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="回测系统")
    parser.add_argument("action", choices=["run", "verify", "stress_test"], help="run=运行回测，verify=测试，stress_test=压力测试")
    parser.add_argument("--stocks", type=str, nargs="+", default=["sh.600459"], help="股票代码列表")
    parser.add_argument("--start", type=str, default="2023-01-01", help="开始日期")
    parser.add_argument("--end", type=str, default="2024-01-01", help="结束日期")
    parser.add_argument("--capital", type=float, default=100000, help="初始资金")
    parser.add_argument("--output", type=str, help="输出报告文件")
    
    args = parser.parse_args()
    
    backverifyer = Backverifyer(initial_capital=args.capital)
    
    if args.action == "run":
        # 运行回测
        result = backverifyer.run_backverify(
            strategy_func=simple_strategy,
            stock_list=args.stocks,
            start_date=args.start,
            end_date=args.end
        )
        
        if result:
            # 生成报告
            output_file = args.output or os.path.join(REPORTS_DIR, f"backverify_{datetime.now().strftime('%Y%m%d')}.md")
            backverifyer.generate_report(result, output_file)
            
            # 自动写入学习系统（2026-03-07 新增）
            print("\n📚 写入学习系统...")
            backverifyer.save_to_learning(result)
    
    elif args.action == "verify":
        print("\n🧪 回测系统测试")
        print("="*60)
        
        # 测试 1：获取历史数据
        print("\n1. 测试获取历史数据...")
        for code in args.stocks[:2]:
            data = backverifyer.get_historical_data(code, args.start, args.end)
            print(f"   {code}: {len(data)}条记录")
            if data:
                print(f"      最新：{data[0]['date']} ¥{data[0]['close']:.2f}")
        
        # 测试 2：实战交易
        print("\n2. 测试交易操作...")
        backverifyer.buy("2024-01-02", "sh.600459", 26.27, 1000)
        print(f"   买入后资金：¥{backverifyer.capital:,.2f}")
        print(f"   持仓：{list(backverifyer.positions.keys())}")
        
        backverifyer.sell("2024-01-15", "sh.600459", 28.50, 1000)
        print(f"   卖出后资金：¥{backverifyer.capital:,.2f}")
        print(f"   持仓：{list(backverifyer.positions.keys())}")
        
        # 测试 3：绩效计算
        print("\n3. 测试绩效计算...")
        backverifyer.portfolio_values = [100000, 102000, 98000, 105000, 110000]
        metrics = backverifyer.calculate_metrics()
        print(f"   总收益：{metrics.get('total_return', 0):.2f}%")
        print(f"   最大回撤：{metrics.get('max_drawdown', 0):.2f}%")
        
        print("\n" + "="*60)
        print("✅ 测试完成")
        print("="*60)
    
    elif args.action == "stress_test":
        # 运行压力测试
        backverifyer.stress_test()


if __name__ == "__main__":
    main()
