#!/usr/bin/env python3
"""
AI 股票团队专业监控面板 v2.0
端口: 8082
技术栈: Python HTTPServer + HTML + CSS + JavaScript (无外部依赖)

数据源:
- SQLite 数据库: ~/.openclaw/workspace/china-stock-team/database/stock_team.db
- JSON 文件: ~/.openclaw/workspace/china-stock-team/learning/
- 输出目录: ~/.openclaw/workspace/china-stock-team/outputs/

文件结构说明:
1. 配置部分 (行 27-51): 端口、路径、日志等配置
2. 安全工具 (行 54-100): 速率限制器实现
3. 数据库管理 (行 103-200): 数据库连接和查询辅助函数
4. 辅助函数 (行 203-300): 数据获取和处理函数
5. API 处理器 (行 704-1160): 各个 API 端点的处理函数
6. HTTP 请求处理器 (行 1166-1300): 请求路由和处理
7. HTML 内容 (行 1303-3980): 前端页面（内联）
8. 启动代码 (行 3986-4005): 服务器启动和主入口

API 端点列表:
- /api/overview: 系统概览
- /api/agents: AI Agents 状态
- /api/cron: Cron 任务调度
- /api/rules: 规则库
- /api/validation-pool: 规则验证池
- /api/knowledge: 知识库
- /api/learning-log: 学习日志
- /api/realtime-prices: 实时价格
- /api/trades: 交易历史
- /api/proposals: 交易提案
- /api/watchlist: 监控列表
- /api/agent-logs: Agent 日志
- /api/health: 系统健康检查
- /api/loop-status: 闭环状态 (P2-1 新增)
- /api/accuracy-trend: 准确率趋势 (P2-2 新增)

P0/P1/P2/P3 改进版本
"""

import http.server
import socketserver
import json
import sqlite3
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import subprocess
import threading
import logging
import time


# ==================== 配置 ====================
PORT = 8082
DB_PATH = "/Users/joe/.openclaw/workspace/china-stock-team/database/stock_team.db"
LEARNING_DIR = "/Users/joe/.openclaw/workspace/china-stock-team/learning"
BASE_DIR = "/Users/joe/.openclaw/workspace/china-stock-team"
DATA_DIR = "/Users/joe/.openclaw/workspace/china-stock-team/data"
LOG_DIR = "/Users/joe/.openclaw/workspace/china-stock-team/logs"
OUTPUTS_DIR = "/Users/joe/.openclaw/workspace/china-stock-team/outputs"

# 安全配置
AUTH_TOKEN = os.environ.get("DASHBOARD_AUTH_TOKEN", "china-stock-team-2024")
ENABLE_AUTH = os.environ.get("DASHBOARD_ENABLE_AUTH", "false").lower() == "true"
RATE_LIMIT_ENABLED = True
RATE_LIMIT_REQUESTS = 60  # 每分钟60次请求
RATE_LIMIT_WINDOW = 60  # 时间窗口60秒

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/joe/.openclaw/workspace/china-stock-team/web/dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== 安全工具 ====================

class RateLimiter:
    """简单的速率限制器"""

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self.requests = {}  # {ip: [(timestamp, count), ...]}

    def is_allowed(self, ip: str) -> tuple[bool, str]:
        """检查是否允许请求"""
        now = time.time()
        key = ip

        # 清理旧记录
        if key in self.requests:
            self.requests[key] = [
                (ts, count) for ts, count in self.requests[key]
                if now - ts < self.window
            ]

        # 计算当前窗口内的请求次数
        current_count = sum(count for _, count in self.requests.get(key, []))

        if current_count >= self.max_requests:
            logger.warning(f"Rate limit exceeded for IP: {ip}")
            return False, f"Rate limit exceeded (max {self.max_requests} requests per {self.window} seconds)"

        # 记录新请求
        if key not in self.requests:
            self.requests[key] = []
        self.requests[key].append((now, 1))

        return True, ""

    def get_remaining(self, ip: str) -> int:
        """获取剩余请求次数"""
        now = time.time()
        key = ip

        if key not in self.requests:
            return self.max_requests

        current_count = sum(count for ts, count in self.requests[key] if now - ts < self.window)
        return max(0, self.max_requests - current_count)


# 全局限流器
rate_limiter = RateLimiter()


def check_auth(headers: dict) -> bool:
    """检查认证令牌"""
    if not ENABLE_AUTH:
        return True

    # 从请求头或查询参数中获取令牌
    auth_header = headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    else:
        return False

    # 验证令牌
    return token == AUTH_TOKEN


# ==================== Agent 定义 ====================
AGENTS = [
    {
        "id": "cio",
        "name": "CIO - 首席投资官",
        "status": "active",
        "role": "最终决策、仓位控制、风险管理",
        "kpi": "月收益 ≥5% | 回撤 ≤15% | 夏普 ≥1.5",
        "today_work": {"proposals_approved": 0, "risk_warnings": 0},
        "color": "#0066FF"
    },
    {
        "id": "quant",
        "name": "Quant - 量化分析师",
        "status": "active",
        "role": "选股模型、因子监控、策略回测",
        "kpi": "胜率 ≥60% | 月收益 ≥8% | IC ≥0.05",
        "today_work": {"predictions_generated": 0, "backtests_run": 0},
        "color": "#00CC66"
    },
    {
        "id": "trader",
        "name": "Trader - 交易员",
        "status": "active",
        "role": "执行交易、择时优化、滑点控制",
        "kpi": "成交率 ≥95% | 滑点 ≤0.5%",
        "today_work": {"trades_executed": 0, "optimizations": 0},
        "color": "#FFCC00"
    },
    {
        "id": "risk",
        "name": "Risk - 风控官",
        "status": "active",
        "role": "风险监控、止损执行、合规审查",
        "kpi": "预警准确 ≥80% | 止损执行 100%",
        "today_work": {"alerts_generated": 0, "stop_loss_triggered": 0},
        "color": "#FF3333"
    },
    {
        "id": "researcher",
        "name": "Researcher - 研究员",
        "status": "active",
        "role": "行业研究、公司调研、信息收集",
        "kpi": "报告准确 ≥70% | 深度研究 ≥2篇/周",
        "today_work": {"reports_generated": 0, "companies_researched": 0},
        "color": "#00B3FF"
    },
    {
        "id": "learning",
        "name": "Learning - 学习系统",
        "status": "active",
        "role": "书籍学习、实战总结、规则提取",
        "kpi": "规则通过 ≥50% | 每日学习 ≥10条",
        "today_work": {"learned_items": 0, "rules_extracted": 0},
        "color": "#9900FF"
    }
]


# ==================== Cron 任务配置 ====================
def calculate_next_sunday_run(schedule: str, now: datetime) -> Optional[str]:
    """计算下周日的运行时间"""
    try:
        # 提取时间部分，例如 "Sunday 20:00" -> "20:00"
        time_part = schedule.split(" ")[1]
        hour, minute = map(int, time_part.split(":"))

        # 找到下一个周日
        days_until_sunday = (6 - now.weekday()) % 7  # 0=周一, 6=周日
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if days_until_sunday == 0 and now.hour < hour:
            # 今天是周日且还未到运行时间
            pass
        else:
            # 加上到下一个周日的天数
            next_run = next_run + timedelta(days=days_until_sunday)

        return next_run.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def calculate_next_daily_run(schedule: str, last_run_date: date, now: datetime) -> Optional[str]:
    """计算每日任务的下次运行时间"""
    try:
        hour, minute = map(int, schedule.split(":"))

        # 基于上次运行日期计算
        last_run_datetime = datetime.combine(last_run_date, datetime.min.time())
        next_run = last_run_datetime.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # 如果下次运行时间已经过去，就加一天
        if next_run <= now:
            next_run = next_run + timedelta(days=1)

        return next_run.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def get_cron_tasks() -> Dict[str, Any]:
    """从调度器读取真实的 Cron 任务状态"""
    state_file = os.path.join(BASE_DIR, ".scheduler.state")
    pid_file = os.path.join(BASE_DIR, ".scheduler.pid")

    # 检查调度器是否运行
    is_running = False
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
                # 检查进程是否存活
                try:
                    os.kill(pid, 0)
                    is_running = True
                except OSError:
                    pass
        except Exception as e:
            logger.warning(f"Failed to check scheduler PID: {e}")

    # 读取状态文件中的 last_runs 数据
    last_runs = {}
    started_at = None
    total_runs = 0

    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
                last_runs = state_data.get("last_runs", {})
                started_at = state_data.get("started_at")
                total_runs = state_data.get("total_runs", 0)
        except Exception as e:
            logger.warning(f"Failed to read scheduler state: {e}")

    # 创建任务 ID 与状态键的映射
    # 根据状态文件中的键名匹配任务
    task_key_map = {
        "morning_prediction": "morning_prediction",
        "midday_update": "noon_update",
        "evening_review": "afternoon_review",
        "rule_promotion": "rule_promotion",
        "daily_learning": "book_learning",
        "weekly_summary": None  # 每周总结在状态文件中没有对应的键
    }

    # 定义任务
    tasks = [
        {
            "id": "morning_prediction",
            "name": "早盘预测",
            "script": "ai_predictor.py",
            "schedule": "09:00",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "分析持仓和自选股，生成今日预测"
        },
        {
            "id": "midday_update",
            "name": "午盘更新",
            "script": "ai_predictor.py --update",
            "schedule": "13:00",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "根据午盘走势调整预测"
        },
        {
            "id": "evening_review",
            "name": "盘后复盘",
            "script": "daily_review_closed_loop.py",
            "schedule": "15:30",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "验证今日预测，记录对错"
        },
        {
            "id": "rule_promotion",
            "name": "规则晋升",
            "script": "rule_promotion.py",
            "schedule": "16:00",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "检查验证池，晋升成熟规则"
        },
        {
            "id": "daily_learning",
            "name": "深度学习",
            "script": "daily_book_learning.py",
            "schedule": "20:00",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "从投资书籍中提取规则"
        },
        {
            "id": "weekly_summary",
            "name": "每周总结",
            "script": "weekly_summary.py",
            "schedule": "Sunday 20:00",
            "last_status": "pending",
            "last_run": None,
            "last_duration": None,
            "next_run": None,
            "enabled": True,
            "description": "总结本周表现"
        }
    ]

    # 更新任务的最后运行时间和状态
    today = datetime.now().date()
    now = datetime.now()

    for task in tasks:
        task_id = task["id"]
        state_key = task_key_map.get(task_id)

        if state_key and state_key in last_runs:
            last_run_date = last_runs[state_key]
            task["last_run"] = last_run_date

            # 计算状态和下次运行时间
            try:
                run_date = datetime.strptime(last_run_date, "%Y-%m-%d").date()
                days_since = (today - run_date).days

                # 计算下次运行时间
                schedule = task["schedule"]
                next_run = None

                if schedule.startswith("Sunday"):
                    # 每周任务
                    next_run = calculate_next_sunday_run(schedule, now)
                else:
                    # 每日任务
                    next_run = calculate_next_daily_run(schedule, run_date, now)

                task["next_run"] = next_run

                # 计算状态 - 基于是否超过下次运行时间
                if next_run:
                    # 将字符串转换为datetime对象
                    try:
                        next_run_dt = datetime.strptime(next_run, "%Y-%m-%d %H:%M")
                        if now >= next_run_dt:
                            if days_since == 0:
                                task["last_status"] = "completed"
                            else:
                                task["last_status"] = "overdue"
                        else:
                            if days_since == 0:
                                task["last_status"] = "success"
                            elif days_since == 1:
                                task["last_status"] = "warning"
                            else:
                                task["last_status"] = "pending"
                    except ValueError:
                        task["last_status"] = "unknown"

            except ValueError:
                task["last_status"] = "unknown"

    return {
        "is_running": is_running,
        "started_at": started_at,
        "total_runs": total_runs,
        "tasks": tasks
    }


# ==================== 数据库工具 ====================

class DatabaseManager:
    """数据库管理器，提供连接和查询功能"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._validate_database()

    def _validate_database(self) -> bool:
        """验证数据库是否存在且可访问"""
        if not os.path.exists(self.db_path):
            logger.error(f"Database file not found: {self.db_path}")
            return False

        try:
            # 尝试连接并执行简单查询
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
            conn.close()
            logger.info("Database validated successfully")
            return True
        except Exception as e:
            logger.error(f"Database validation failed: {e}")
            return False

    def get_connection(self) -> Optional[sqlite3.Connection]:
        """获取数据库连接"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            return None

    def execute_query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """执行数据库查询"""
        conn = self.get_connection()
        if not conn:
            logger.warning("No database connection available")
            return []

        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.error(f"Query error: {e}")
            logger.error(f"Query: {query}")
            return []
        finally:
            conn.close()

    def execute_update(self, query: str, params: tuple = ()) -> bool:
        """执行数据库更新操作"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Update error: {e}")
            logger.error(f"Query: {query}")
            return False
        finally:
            conn.close()


# 创建全局数据库管理器
db_manager = DatabaseManager(DB_PATH)


# ==================== JSON 文件工具 ====================

def load_json_file(filename: str, default: Any = {}) -> Any:
    """安全加载 JSON 文件"""
    filepath = os.path.join(LEARNING_DIR, filename)
    if not os.path.exists(filepath):
        logger.warning(f"File not found: {filename}")
        return default

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.debug(f"Loaded {filename}: {type(data)}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in {filename}: {e}")
        return default
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default


def save_json_file(filename: str, data: Dict[str, Any]) -> bool:
    """保存 JSON 文件"""
    filepath = os.path.join(LEARNING_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {filename}")
        return True
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")
        return False


# ==================== 数据获取函数 ====================

def get_positions() -> List[Dict[str, Any]]:
    """获取持仓数据"""
    try:
        rows = db_manager.execute_query("""
            SELECT id, symbol, name, shares, cost_price, current_price,
                   market_value, profit_loss, profit_loss_pct, stop_loss, take_profit, status
            FROM positions
            WHERE status = 'holding'
            ORDER BY id
        """)

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "symbol": row["symbol"],
                "name": row["name"],
                "shares": row["shares"],
                "cost_price": row["cost_price"],
                "current_price": row["current_price"],
                "market_value": row["market_value"],
                "profit_loss": row["profit_loss"],
                "profit_loss_pct": row["profit_loss_pct"],
                "stop_loss": row["stop_loss"],
                "take_profit": row["take_profit"],
                "status": row["status"]
            })
        logger.info(f"Retrieved {len(result)} positions")
        return result
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return []


def get_account_info() -> Dict[str, Any]:
    """获取账户信息"""
    try:
        # 获取最新的账户信息来确定现金余额
        rows = db_manager.execute_query("""
            SELECT cash, total_profit 
            FROM account
            ORDER BY id DESC
            LIMIT 1
        """)
        
        # 获取持仓信息
        positions = get_positions()
        
        total_value = sum(pos.get('market_value', 0) for pos in positions)
        total_cost = sum(pos.get('shares', 0) * pos.get('cost_price', 0) for pos in positions)
        
        if rows:
            # 数据库中的cash字段实际是总资产，所以我们需要减去当前持仓市值来得到真实现金
            total_asset_from_db = float(rows[0]["cash"]) if rows[0]["cash"] else 0
            cash = max(0, total_asset_from_db - total_value)
            total_asset = total_asset_from_db
            total_profit = float(rows[0]["total_profit"]) if rows[0]["total_profit"] else 0
            total_profit_pct = (total_profit / (total_asset - total_profit) * 100) if (total_asset - total_profit) > 0 else 0
        else:
            cash = 0
            total_asset = total_value
            total_profit = 0
            total_profit_pct = 0
            
        result = {
            "total_asset": total_asset,
            "cash": cash,
            "market_value": total_value,
            "profit_loss": total_profit,
            "profit_loss_pct": total_profit_pct,
            "date": None
        }
        
        logger.info(f"Account data: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        return {
            "total_asset": 0,
            "cash": 0,
            "market_value": 0,
            "profit_loss": 0,
            "profit_loss_pct": 0,
            "date": None
        }


def get_realtime_price(symbol: str) -> Optional[Dict]:
    """获取实时价格（用于持仓显示）"""
    try:
        stock_code = symbol.replace('.', '')
        url = f"http://qt.gtimg.cn/q={stock_code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = response.read().decode('gbk')
            if '~' in data:
                parts = data.split('~')
                price = float(parts[3])
                prev_close = float(parts[4])
                # 计算涨跌幅
                change_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                return {
                    'name': parts[1],
                    'price': price,
                    'change_pct': change_pct,
                }
    except Exception as e:
        logger.warning(f"Failed to get real-time price for {symbol}: {e}")
    return None

# ==================== 事件分析相关函数 ====================
def get_event_analysis_data() -> Dict[str, Any]:
    """获取事件分析概览"""
    try:
        rows = db_manager.execute_query("""
            SELECT eka.*, nl.title, nl.sentiment, nl.event_types, nl.impact_score
            FROM event_kline_associations eka
            JOIN news_labels nl ON eka.news_id = nl.news_id
            WHERE eka.kline_start_date >= date('now', '-7 days')
            ORDER BY eka.kline_start_date DESC
            LIMIT 10
        """)
        
        recent_events = []
        for row in rows:
            event_dict = dict(row)
            # 解析 event_types JSON 字符串
            try:
                if event_dict.get('event_types'):
                    event_dict['event_types'] = json.loads(event_dict['event_types'])
            except (json.JSONDecodeError, TypeError):
                event_dict['event_types'] = []
            recent_events.append(event_dict)
        
        # 统计情绪分布
        sentiment_rows = db_manager.execute_query("""
            SELECT sentiment, COUNT(*) as count
            FROM news_labels
            WHERE news_time >= date('now', '-30 days')
            GROUP BY sentiment
        """)
        sentiment_dist = {row['sentiment']: row['count'] for row in sentiment_rows}
        
        # 事件影响排行
        impact_rows = db_manager.execute_query("""
            SELECT stock_code, stock_name,
                   AVG(kline_change_pct) as avg_change,
                   COUNT(*) as event_count
            FROM event_kline_associations
            WHERE kline_start_date >= date('now', '-30 days')
            GROUP BY stock_code
            ORDER BY avg_change DESC
            LIMIT 10
        """)
        impact_ranking = [dict(row) for row in impact_rows]
        
        return {
            'recent_events': recent_events,
            'sentiment_distribution': sentiment_dist,
            'impact_ranking': impact_ranking
        }
    except Exception as e:
        logger.error(f"Error getting event analysis data: {e}")
        return {
            'recent_events': [],
            'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0},
            'impact_ranking': []
        }

def get_news_labels() -> Dict[str, Any]:
    """获取新闻标签列表"""
    try:
        rows = db_manager.execute_query("""
            SELECT * FROM news_labels
            ORDER BY news_time DESC
            LIMIT 50
        """)
        news_list = [dict(row) for row in rows]
        return {'news': news_list}
    except Exception as e:
        logger.error(f"Error getting news labels: {e}")
        return {'news': []}

def get_range_analysis(stock_code: str = '', start_date: str = '', end_date: str = '') -> Dict[str, Any]:
    """获取区间分析"""
    try:
        query = """
            SELECT * FROM range_analysis
            WHERE (? = '' OR stock_code = ?)
              AND (? = '' OR start_date >= ?)
              AND (? = '' OR end_date <= ?)
            ORDER BY created_at DESC
            LIMIT 20
        """
        params = (stock_code, stock_code, start_date, start_date, end_date, end_date)
        rows = db_manager.execute_query(query, params)
        analysis_list = [dict(row) for row in rows]
        return {'analysis': analysis_list}
    except Exception as e:
        logger.error(f"Error getting range analysis: {e}")
        return {'analysis': []}

def get_event_impact_history() -> Dict[str, Any]:
    """获取事件影响历史"""
    try:
        rows = db_manager.execute_query("""
            SELECT * FROM event_impact_history
            ORDER BY verified_at DESC
            LIMIT 50
        """)
        history_list = [dict(row) for row in rows]
        return {'history': history_list}
    except Exception as e:
        logger.error(f"Error getting event impact history: {e}")
        return {'history': []}

def get_stock_kline_with_events(symbol: str) -> Dict[str, Any]:
    """获取带事件标记的K线数据"""
    try:
        # 获取K线数据（最近30天）
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # 这里需要从市场数据源获取K线数据
        # 由于当前系统没有存储历史K线，我们返回模拟数据
        # 在实际应用中，这里应该调用数据适配器获取真实K线
        
        kline_data = []
        for i in range(30):
            date_str = (datetime.now() - timedelta(days=29-i)).strftime('%Y-%m-%d')
            kline_data.append({
                'date': date_str,
                'open': 100.0 + i * 0.1,
                'high': 101.0 + i * 0.1,
                'low': 99.0 + i * 0.1,
                'close': 100.5 + i * 0.1,
                'volume': 1000000
            })
        
        # 获取相关事件
        events = []
        if symbol:
            event_rows = db_manager.execute_query("""
                SELECT eka.*, nl.title, nl.sentiment, nl.event_types, nl.impact_score
                FROM event_kline_associations eka
                JOIN news_labels nl ON eka.news_id = nl.news_id
                WHERE eka.stock_code = ?
                ORDER BY eka.kline_start_date DESC
                LIMIT 10
            """, (symbol,))
            
            for row in event_rows:
                event_dict = dict(row)
                try:
                    if event_dict.get('event_types'):
                        event_dict['event_types'] = json.loads(event_dict['event_types'])
                except (json.JSONDecodeError, TypeError):
                    event_dict['event_types'] = []
                events.append(event_dict)
        
        return {
            'symbol': symbol,
            'kline_data': kline_data,
            'events': events,
            'event_count': len(events)
        }
    except Exception as e:
        logger.error(f"Error getting stock kline with events: {e}")
        return {
            'symbol': symbol,
            'kline_data': [],
            'events': [],
            'event_count': 0
        }


def get_accuracy_stats() -> Dict[str, Any]:
    """获取预测准确率统计"""
    try:
        data = load_json_file("accuracy_stats.json", {
            "total_predictions": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "by_rule": {},
            "by_stock": {},
            "by_direction": {},
            "by_date": {},
            "last_updated": None
        })
        return data
    except Exception as e:
        logger.error(f"Error getting accuracy stats: {e}")
        return {"total_predictions": 0, "correct": 0, "partial": 0, "wrong": 0}


def get_prediction_rules() -> Dict[str, Any]:
    """获取预测规则"""
    try:
        data = load_json_file("prediction_rules.json", {
            "direction_rules": {},
            "magnitude_rules": {},
            "timing_rules": {},
            "confidence_rules": {}
        })
        return data
    except Exception as e:
        logger.error(f"Error getting prediction rules: {e}")
        return {"direction_rules": {}, "magnitude_rules": {}, "timing_rules": {}, "confidence_rules": {}}


def get_rule_validation_pool() -> Dict[str, Any]:
    """获取规则验证池"""
    try:
        data = load_json_file("rule_validation_pool.json", {})
        return data
    except Exception as e:
        logger.error(f"Error getting rule validation pool: {e}")
        return {}


def get_knowledge_base() -> Dict[str, Any]:
    """获取知识库"""
    try:
        data = load_json_file("knowledge_base.json", {"items": []})
        return data
    except Exception as e:
        logger.error(f"Error getting knowledge base: {e}")
        return {"items": []}


def get_book_knowledge() -> Dict[str, Any]:
    """获取书籍知识"""
    try:
        data = load_json_file("book_knowledge.json", {})
        return data
    except Exception as e:
        logger.error(f"Error getting book knowledge: {e}")
        return {}


def get_daily_learning_log() -> List[Dict[str, Any]]:
    """获取每日学习日志"""
    try:
        data = load_json_file("daily_learning_log.json", [])
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error(f"Error getting daily learning log: {e}")
        return []


def get_team_health() -> Dict[str, Any]:
    """获取团队健康状态"""
    try:
        data = load_json_file("team_health.json", {
            "weekly_reports": [],
            "issues": [],
            "improvements": []
        })
        return data
    except Exception as e:
        logger.error(f"Error getting team health: {e}")
        return {"weekly_reports": [], "issues": [], "improvements": []}


def get_rule_stats() -> Dict[str, Any]:
    """获取规则统计"""
    try:
        data = load_json_file("rule_stats.json", {})
        return data
    except Exception as e:
        logger.error(f"Error getting rule stats: {e}")
        return {}


def get_proposals(limit: int = 20) -> List[Dict[str, Any]]:
    """获取提案列表"""
    try:
        rows = db_manager.execute_query("""
            SELECT p.*, q.technical_score, r.risk_level
            FROM proposals p
            LEFT JOIN quant_analysis q ON p.id = q.proposal_id
            LEFT JOIN risk_assessment r ON p.id = r.proposal_id
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (limit,))

        result = []
        for row in rows:
            result.append(dict(row))
        return result
    except Exception as e:
        logger.error(f"Error getting proposals: {e}")
        return []


def get_trades(limit: int = 50) -> List[Dict[str, Any]]:
    """获取交易记录"""
    try:
        rows = db_manager.execute_query("""
            SELECT * FROM trades
            ORDER BY executed_at DESC
            LIMIT ?
        """, (limit,))

        result = []
        for row in rows:
            result.append(dict(row))
        return result
    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        return []


def get_watchlist() -> List[Dict[str, Any]]:
    """获取监控列表"""
    try:
        rows = db_manager.execute_query("""
            SELECT * FROM watchlist
            ORDER BY added_at DESC
        """)

        result = []
        for row in rows:
            result.append(dict(row))
        return result
    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        return []


def get_market_cache(symbol: str) -> Optional[Dict[str, Any]]:
    """从缓存获取市场数据"""
    try:
        rows = db_manager.execute_query("""
            SELECT * FROM market_cache
            WHERE symbol = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (symbol,))

        if rows:
            return dict(rows[0])
        return None
    except Exception as e:
        logger.error(f"Error getting market cache: {e}")
        return None


def get_agent_logs(agent: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """获取 Agent 日志"""
    try:
        query = "SELECT * FROM agent_logs"
        params = []

        if agent:
            query += " WHERE agent = ?"
            params.append(agent)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = db_manager.execute_query(query, tuple(params))

        result = []
        for row in rows:
            result.append(dict(row))
        return result
    except Exception as e:
        logger.error(f"Error getting agent logs: {e}")
        return []


# ==================== API 处理器 ====================

def handle_api_overview() -> Dict[str, Any]:
    """处理概览数据 API"""
    try:
        account = get_account_info()
        positions = get_positions()
        accuracy = get_accuracy_stats()
        team_health = get_team_health()

        # 计算系统健康度
        health_score = 100.0
        if team_health.get("weekly_reports"):
            latest = team_health["weekly_reports"][0]
            if latest.get("issues"):
                health_score = max(70.0, 100.0 - len(latest["issues"]) * 5)

        # 检查数据库连接
        if not db_manager._validate_database():
            health_score = min(health_score, 50.0)

        # 计算准确率
        total = accuracy.get("total_predictions", 0)
        correct = accuracy.get("correct", 0)
        accuracy_rate = (correct / total * 100) if total > 0 else 0

        return {
            "account": account,
            "positions": positions,
            "accuracy": {
                "total": total,
                "correct": correct,
                "partial": accuracy.get("partial", 0),
                "wrong": accuracy.get("wrong", 0),
                "accuracy_rate": round(accuracy_rate, 1)
            },
            "by_rule": accuracy.get("by_rule", {}),
            "system_health": round(health_score, 1),
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_overview: {e}")
        return {"error": str(e)}


def handle_api_agents() -> Dict[str, Any]:
    """处理 Agents 数据 API"""
    try:
        learning_log = get_daily_learning_log()

        # 更新学习系统的工作数据
        today_date = datetime.now().strftime("%Y-%m-%d")
        today_learning = [log for log in learning_log
                         if log.get("date", "").startswith(today_date)]

        for agent in AGENTS:
            if agent["id"] == "learning":
                agent["today_work"]["learned_items"] = len(today_learning)

            # 从数据库获取实际工作数据
            agent_logs = get_agent_logs(agent["id"], limit=10)
            if agent["id"] == "cio":
                agent["today_work"]["proposals_approved"] = len([l for l in agent_logs if l.get("event_type") == "approval"])
            elif agent["id"] == "risk":
                agent["today_work"]["alerts_generated"] = len([l for l in agent_logs if l.get("event_type") == "alert"])

        return {
            "agents": AGENTS,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_agents: {e}")
        return {"error": str(e), "agents": AGENTS}


def handle_api_cron() -> Dict[str, Any]:
    """处理 Cron 任务数据 API"""
    try:
        cron_data = get_cron_tasks()

        return {
            **cron_data,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_cron: {e}")
        return {"error": str(e), "is_running": False, "tasks": []}


def handle_api_rules() -> Dict[str, Any]:
    """处理规则库数据 API"""
    try:
        rules = get_prediction_rules()
        accuracy = get_accuracy_stats()

        # 合并准确率数据
        for category in ["direction_rules", "magnitude_rules", "timing_rules", "confidence_rules"]:
            if category in rules:
                for rule_id, rule in rules[category].items():
                    if rule_id in accuracy.get("by_rule", {}):
                        rule_data = accuracy["by_rule"][rule_id]
                        rule["samples"] = rule_data.get("total", 0)
                        rule["success_rate"] = round(
                            (rule_data.get("correct", 0) / rule_data.get("total", 1) * 100),
                            1
                        ) if rule_data.get("total", 0) > 0 else 0

        return {
            "rules": rules,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_rules: {e}")
        return {"error": str(e)}


def handle_api_validation_pool() -> Dict[str, Any]:
    """处理验证池数据 API"""
    try:
        pool = get_rule_validation_pool()

        # 分类统计
        by_status = {}
        by_category = {}

        for rule_id, rule in pool.items():
            status = rule.get("status", "validating")
            by_status[status] = by_status.get(status, 0) + 1

            category = rule.get("category", "unknown")
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "pool": pool,
            "stats": {
                "total": len(pool),
                "by_status": by_status,
                "by_category": by_category
            },
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_validation_pool: {e}")
        return {"error": str(e), "pool": {}, "stats": {}}


def handle_api_knowledge() -> Dict[str, Any]:
    """处理知识库数据 API"""
    try:
        knowledge = get_knowledge_base()
        book_knowledge = get_book_knowledge()

        return {
            "knowledge_base": knowledge,
            "book_knowledge": book_knowledge,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_knowledge: {e}")
        return {"error": str(e)}


def handle_api_learning_log() -> Dict[str, Any]:
    """处理学习日志数据 API"""
    try:
        log = get_daily_learning_log()

        # 分类统计
        by_type = {}
        by_date = {}

        for entry in log:
            entry_type = entry.get("type", "unknown")
            by_type[entry_type] = by_type.get(entry_type, 0) + 1

            date = entry.get("date", "")[:10] if entry.get("date") else "unknown"
            by_date[date] = by_date.get(date, 0) + 1

        return {
            "log": log,
            "stats": {
                "total": len(log),
                "by_type": by_type,
                "by_date": by_date
            },
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_learning_log: {e}")
        return {"error": str(e), "log": [], "stats": {}}


def handle_api_realtime_prices() -> Dict[str, Any]:
    """处理实时价格 API"""
    try:
        positions = get_positions()
        prices = {}

        for pos in positions:
            symbol = pos["symbol"]
            realtime_price = get_realtime_price(symbol)
            if realtime_price:
                prices[symbol] = {
                    "price": realtime_price,
                    "change_pct": round((realtime_price - pos["cost_price"]) / pos["cost_price"] * 100, 2) if pos["cost_price"] else 0
                }

        return {
            "prices": prices,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_realtime_prices: {e}")
        return {"error": str(e), "prices": {}}


def handle_api_trades() -> Dict[str, Any]:
    """处理交易记录 API"""
    try:
        trades = get_trades(limit=100)

        return {
            "trades": trades,
            "total": len(trades),
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_trades: {e}")
        return {"error": str(e), "trades": [], "total": 0}


def handle_api_proposals() -> Dict[str, Any]:
    """处理提案列表 API"""
    try:
        proposals = get_proposals(limit=100)

        return {
            "proposals": proposals,
            "total": len(proposals),
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_proposals: {e}")
        return {"error": str(e), "proposals": [], "total": 0}


def handle_api_watchlist() -> Dict[str, Any]:
    """处理监控列表 API"""
    try:
        watchlist = get_watchlist()

        return {
            "watchlist": watchlist,
            "total": len(watchlist),
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_watchlist: {e}")
        return {"error": str(e), "watchlist": [], "total": 0}


def handle_api_agent_logs(agent: Optional[str] = None) -> Dict[str, Any]:
    """处理 Agent 日志 API"""
    try:
        logs = get_agent_logs(agent=agent, limit=100)

        return {
            "logs": logs,
            "total": len(logs),
            "agent": agent,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in handle_api_agent_logs: {e}")
        return {"error": str(e), "logs": [], "total": 0}


def handle_api_health() -> Dict[str, Any]:
    """处理系统健康检查 API"""
    try:
        # 1. 检查数据库
        database_ok = db_manager._validate_database()

        # 2. 检查数据文件更新时间
        data_quality = check_data_quality()

        # 3. 检查任务执行状态
        task_status = check_task_status()

        # 4. 检查闭环健康度
        closed_loop_health = check_closed_loop_health()

        # 5. 计算总体健康度
        health_scores = [
            100 if database_ok else 0,
            data_quality["score"],
            task_status["score"],
            closed_loop_health["score"]
        ]
        overall_health = round(sum(health_scores) / len(health_scores), 1)

        # 6. 确定总体状态
        if overall_health >= 80:
            overall_status = "healthy"
        elif overall_health >= 60:
            overall_status = "warning"
        else:
            overall_status = "error"

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "overall_health": overall_health,
            "checks": {
                "database": {
                    "status": "ok" if database_ok else "error",
                    "message": "数据库连接正常" if database_ok else "数据库连接失败"
                },
                "data_quality": data_quality,
                "task_status": task_status,
                "closed_loop": closed_loop_health
            },
            "recommendations": get_health_recommendations(overall_status, data_quality, task_status, closed_loop_health)
        }
    except Exception as e:
        logger.error(f"Error in handle_api_health: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "overall_health": 0
        }


def handle_api_loop_status() -> Dict[str, Any]:
    """处理闭环状态 API"""
    try:
        # 读取闭环健康报告
        health_report_path = os.path.join(OUTPUTS_DIR, "closed_loop_health.json")

        if not os.path.exists(health_report_path):
            return {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "unknown",
                "health_score": 0,
                "loops": {},
                "message": "闭环健康报告不存在"
            }

        with open(health_report_path, 'r', encoding='utf-8') as f:
            health_report = json.load(f)

        # 提取四个闭环的状态
        loops = {
            "data": {
                "name": "数据闭环",
                "score": health_report.get("checks", {}).get("data_collection", {}).get("score", 0),
                "status": health_report.get("checks", {}).get("data_collection", {}).get("status", "unknown"),
                "issues": health_report.get("checks", {}).get("data_collection", {}).get("issues", []),
                "warnings": health_report.get("checks", {}).get("data_collection", {}).get("warnings", []),
                "breakpoints": []
            },
            "rules": {
                "name": "规则闭环",
                "score": health_report.get("checks", {}).get("rule_generation", {}).get("score", 0),
                "status": health_report.get("checks", {}).get("rule_generation", {}).get("status", "unknown"),
                "issues": health_report.get("checks", {}).get("rule_generation", {}).get("issues", []),
                "warnings": health_report.get("checks", {}).get("rule_generation", {}).get("warnings", []),
                "breakpoints": []
            },
            "validation": {
                "name": "验证闭环",
                "score": health_report.get("checks", {}).get("rule_validation", {}).get("score", 0),
                "status": health_report.get("checks", {}).get("rule_validation", {}).get("status", "unknown"),
                "issues": health_report.get("checks", {}).get("rule_validation", {}).get("issues", []),
                "warnings": health_report.get("checks", {}).get("rule_validation", {}).get("warnings", []),
                "breakpoints": []
            },
            "learning": {
                "name": "学习闭环",
                "score": health_report.get("checks", {}).get("learning_cycle", {}).get("score", 0),
                "status": health_report.get("checks", {}).get("learning_cycle", {}).get("status", "unknown"),
                "issues": health_report.get("checks", {}).get("learning_cycle", {}).get("issues", []),
                "warnings": health_report.get("checks", {}).get("learning_cycle", {}).get("warnings", []),
                "breakpoints": []
            }
        }

        # 识别断点（分数低于 60 的环节）
        for loop_key, loop_data in loops.items():
            if loop_data["score"] < 60:
                if loop_data["issues"]:
                    loops[loop_key]["breakpoints"].append({
                        "type": "error",
                        "message": loop_data["issues"][0]
                    })
                else:
                    loops[loop_key]["breakpoints"].append({
                        "type": "warning",
                        "message": f"{loop_data['name']}需要关注"
                    })

        # 生成改进建议
        recommendations = []
        weak_loops = [(k, v) for k, v in loops.items() if v["score"] < 60]
        weak_loops.sort(key=lambda x: x[1]["score"])  # 按分数升序排序

        if weak_loops:
            worst_loop = weak_loops[0][1]
            recommendations.append(f"优先处理 {worst_loop['name']}（当前分数: {worst_loop['score']}）")

        if loops["data"]["score"] < 60:
            recommendations.append("检查数据收集脚本运行状态")
        if loops["rules"]["score"] < 60:
            recommendations.append("增加规则样本数据，重新训练")
        if loops["validation"]["score"] < 60:
            recommendations.append("运行规则验证脚本")
        if loops["learning"]["score"] < 60:
            recommendations.append("检查学习脚本运行状态")

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": health_report.get("overall_status", "unknown"),
            "health_score": health_report.get("health_score", 0),
            "loops": loops,
            "recommendations": recommendations,
            "last_check": health_report.get("timestamp", "未知")
        }
    except Exception as e:
        logger.error(f"Error in handle_api_loop_status: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "error",
            "health_score": 0,
            "loops": {},
            "error": str(e)
        }


def handle_api_accuracy_trend() -> Dict[str, Any]:
    """处理准确率趋势 API - 从真实数据读取"""
    try:
        # 从 predictions.json 读取真实准确率数据
        predictions_path = os.path.join(DATA_DIR, "predictions.json")

        trend_data = []

        if os.path.exists(predictions_path):
            with open(predictions_path, 'r', encoding='utf-8') as f:
                predictions_data = json.load(f)

            # 统计按日期的准确率
            by_date = defaultdict(lambda: {'total': 0, 'correct': 0, 'partial': 0})

            for pred in predictions_data.get('history', []):
                created_at = pred.get('created_at', '')
                if created_at:
                    date = created_at.split('T')[0]
                    result = pred.get('result', {})
                    if result:
                        by_date[date]['total'] += 1
                        if result.get('correct'):
                            by_date[date]['correct'] += 1
                        if result.get('partial'):
                            by_date[date]['partial'] += 1

            # 按日期排序并生成趋势数据
            for date in sorted(by_date.keys()):
                stats = by_date[date]
                total = stats['total']
                correct = stats['correct']
                partial = stats['partial']
                # 准确率 = (正确 + 部分正确) / 总数
                accuracy = ((correct + partial) / total * 100) if total > 0 else 0

                trend_data.append({
                    "date": date,
                    "accuracy": round(accuracy, 1),
                    "total_predictions": total,
                    "correct_predictions": correct,
                    "partial_predictions": partial
                })

        # 计算趋势分析
        if len(trend_data) >= 2:
            current_accuracy = trend_data[-1]["accuracy"] if trend_data else 0
            previous_accuracy = trend_data[-2]["accuracy"] if len(trend_data) >= 2 else current_accuracy

            # 计算平均准确率
            avg_accuracy = round(sum(d["accuracy"] for d in trend_data) / len(trend_data), 1) if trend_data else 0

            # 趋势方向
            trend_direction = "improving" if current_accuracy > previous_accuracy else "declining" if current_accuracy < previous_accuracy else "stable"
            trend_change = round(current_accuracy - previous_accuracy, 1)

            # 7天平均（如果数据足够）
            recent_7d = trend_data[-7:] if len(trend_data) >= 7 else trend_data
            avg_7d = round(sum(d["accuracy"] for d in recent_7d) / len(recent_7d), 1) if recent_7d else 0
        else:
            current_accuracy = 0
            previous_accuracy = 0
            avg_accuracy = 0
            trend_direction = "insufficient_data"
            trend_change = 0
            avg_7d = 0

        return {
            "timestamp": datetime.now().isoformat(),
            "trend_data": trend_data,
            "data_source": "predictions.json",
            "data_days": len(trend_data),
            "trend_analysis": {
                "direction": trend_direction,
                "change": trend_change,
                "current_accuracy": current_accuracy,
                "previous_accuracy": previous_accuracy,
                "average": avg_accuracy,
                "average_7d": avg_7d
            },
            "recommendations": get_accuracy_trend_recommendations(trend_direction, trend_change, trend_data)
        }
    except Exception as e:
        logger.error(f"Error in handle_api_accuracy_trend: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "trend_data": [],
            "trend_analysis": {}
        }


def get_accuracy_trend_recommendations(trend_direction: str, trend_change: float, trend_data: List[Dict]) -> List[str]:
    """获取准确率趋势建议"""
    recommendations = []

    if trend_direction == "declining" and trend_change < -5:
        recommendations.append("准确率快速下降，建议检查数据质量和规则有效性")
    elif trend_direction == "declining" and trend_change < -2:
        recommendations.append("准确率有所下降，建议复盘最近的预测错误案例")

    if trend_direction == "improving":
        if trend_change > 5:
            recommendations.append("准确率显著提升，保持当前策略")
        else:
            recommendations.append("准确率稳步提升，继续优化规则细节")

    if trend_data and trend_data[-1]["accuracy"] < 50:
        recommendations.append("当前准确率较低，建议增加规则样本或调整规则权重")
    elif trend_data and trend_data[-1]["accuracy"] > 80:
        recommendations.append("准确率表现良好，可以尝试扩展交易范围")

    return recommendations


def check_data_quality() -> Dict[str, Any]:
    """检查数据质量"""
    score = 100
    issues = []

    # 检查学习文件
    memory_path = os.path.join(LEARNING_DIR, "memory.md")
    if os.path.exists(memory_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(memory_path))
        age = datetime.now() - mtime
        if age.total_seconds() > 48 * 3600:  # 超过48小时
            score -= 20
            issues.append(f"学习记忆文件超过48小时未更新")
    else:
        score -= 30
        issues.append("学习记忆文件不存在")

    # 检查规则文件
    rules_path = os.path.join(LEARNING_DIR, "prediction_rules.json")
    if os.path.exists(rules_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(rules_path))
        age = datetime.now() - mtime
        if age.total_seconds() > 72 * 3600:  # 超过72小时
            score -= 15
            issues.append(f"规则文件超过72小时未更新")
    else:
        score -= 25
        issues.append("规则文件不存在")

    # 检查日志文件
    log_files = list(os.path.join(LOG_DIR, "*.log"))
    if log_files:
        latest_log = max(log_files, key=lambda f: os.path.getmtime(f))
        mtime = datetime.fromtimestamp(os.path.getmtime(latest_log))
        age = datetime.now() - mtime
        if age.total_seconds() > 6 * 3600:  # 超过6小时
            score -= 10
            issues.append(f"日志文件超过6小时未更新")
    else:
        score -= 15
        issues.append("没有找到日志文件")

    status = "good" if score >= 80 else "warning" if score >= 60 else "error"

    return {
        "status": status,
        "score": score,
        "issues": issues
    }


def check_task_status() -> Dict[str, Any]:
    """检查任务执行状态"""
    score = 100
    issues = []
    tasks_running = []

    # 检查调度器状态
    pid_file = os.path.join(BASE_DIR, ".scheduler.pid")
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            pid = f.read().strip()
        # 检查进程是否真的在运行
        try:
            pid_int = int(pid)
            os.kill(pid_int, 0)  # 检查进程是否存在
            tasks_running.append({"name": "调度器", "pid": pid, "status": "running"})
        except (OSError, ValueError):
            # 进程不存在，更新状态
            score -= 20
            issues.append("调度器进程已停止")
            tasks_running.append({"name": "调度器", "status": "stopped"})
    else:
        score -= 20
        issues.append("调度器未运行")
        tasks_running.append({"name": "调度器", "status": "stopped"})

    # 检查仪表盘状态
    tasks_running.append({"name": "仪表盘", "status": "running", "pid": os.getpid()})

    status = "good" if score >= 80 else "warning" if score >= 60 else "error"

    return {
        "status": status,
        "score": score,
        "issues": issues,
        "tasks": tasks_running
    }


def check_closed_loop_health() -> Dict[str, Any]:
    """检查闭环健康度"""
    # 尝试加载健康报告
    health_report_path = os.path.join(OUTPUTS_DIR, "closed_loop_health.json")
    if os.path.exists(health_report_path):
        try:
            with open(health_report_path, 'r', encoding='utf-8') as f:
                health_report = json.load(f)
            return {
                "status": health_report.get("overall_status", "unknown"),
                "score": health_report.get("health_score", 0),
                "last_check": health_report.get("timestamp", "未知")
            }
        except Exception:
            pass

    # 如果没有健康报告，返回默认值
    return {
        "status": "unknown",
        "score": 0,
        "last_check": "未运行"
    }


def get_health_recommendations(overall_status: str, data_quality: Dict, task_status: Dict, closed_loop: Dict) -> List[str]:
    """获取健康检查建议"""
    recommendations = []

    if overall_status == "error":
        recommendations.append("系统存在严重问题，建议立即检查")

    if data_quality["score"] < 60:
        recommendations.append("数据质量较低，建议检查数据收集和学习脚本运行状态")

    if task_status["score"] < 60:
        recommendations.append("任务执行异常，建议检查调度器状态")

    if closed_loop["score"] < 60:
        recommendations.append("闭环健康度较低，建议运行闭环健康检查脚本")

    if overall_status == "healthy":
        recommendations.append("系统运行正常，继续保持")

    return recommendations


# ==================== HTTP 请求处理器 ====================

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """自定义 HTTP 请求处理器"""

    def send_json_response(self, data: Dict[str, Any], status: int = 200):
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        response = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(response.encode('utf-8'))

    def send_html_response(self, content: str, status: int = 200):
        """发送 HTML 响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def send_csv_response(self, filename: str, content: str, status: int = 200):
        """发送 CSV 文件响应"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8-sig'))

    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # 获取客户端 IP
        client_ip = self.client_address[0]

        # 速率限制检查
        if RATE_LIMIT_ENABLED:
            allowed, message = rate_limiter.is_allowed(client_ip)
            if not allowed:
                self.send_json_response({"error": message}, 429)
                logger.warning(f"Rate limit blocked request from {client_ip}")
                return

        # 认证检查（仅对 API 端点）
        if path.startswith('/api/'):
            if not check_auth(dict(self.headers)):
                self.send_json_response({"error": "Unauthorized"}, 401)
                logger.warning(f"Unauthorized access attempt from {client_ip}")
                return

        # API 路由
        if path.startswith('/api/'):
            try:
                if path == '/api/overview':
                    data = handle_api_overview()
                elif path == '/api/agents':
                    data = handle_api_agents()
                elif path == '/api/cron':
                    data = handle_api_cron()
                elif path == '/api/rules':
                    data = handle_api_rules()
                elif path == '/api/validation-pool':
                    data = handle_api_validation_pool()
                elif path == '/api/knowledge':
                    data = handle_api_knowledge()
                elif path == '/api/learning-log':
                    data = handle_api_learning_log()
                elif path == '/api/realtime-prices':
                    data = handle_api_realtime_prices()
                elif path == '/api/trades':
                    data = handle_api_trades()
                elif path == '/api/proposals':
                    data = handle_api_proposals()
                elif path == '/api/watchlist':
                    data = handle_api_watchlist()
                elif path == '/api/agent-logs':
                    agent = query_params.get('agent', [None])[0]
                    if agent is None:
                        data = handle_api_agent_logs()
                    else:
                        data = handle_api_agent_logs(agent)
                elif path == '/api/health':
                    data = handle_api_health()
                elif path == '/api/loop-status':
                    data = handle_api_loop_status()
                elif path == '/api/accuracy-trend':
                    data = handle_api_accuracy_trend()
                elif path == '/api/account':  # 兼容旧版本前端
                    account_data = get_account_info()
                    data = {
                        'total_asset': account_data['total_asset'],
                        'cash': account_data['cash'], 
                        'market_value': account_data['market_value'],
                        'total_profit': account_data['profit_loss'],
                        'total_profit_pct': account_data['profit_loss_pct'],
                        'position_count': len(get_positions()),
                        'positions': get_positions()
                    }
                elif path == '/api/accuracy':  # 兼容旧版本前端
                    accuracy_data = get_accuracy_stats()
                    data = {
                        'total': accuracy_data.get('total_predictions', 0),
                        'correct': accuracy_data.get('correct', 0),
                        'partial': accuracy_data.get('partial', 0),
                        'wrong': accuracy_data.get('wrong', 0),
                        'accuracy_rate': accuracy_data.get('accuracy_rate', 0),
                        'by_rule': accuracy_data.get('by_rule', {}),
                        'by_direction': accuracy_data.get('by_direction', {})
                    }
                elif path == '/api/knowledge-base':  # 兼容旧版本前端
                    data = handle_api_knowledge()
                elif path == '/api/event-analysis':
                    data = get_event_analysis_data()
                elif path == '/api/event-analysis/news':
                    data = get_news_labels()
                elif path.startswith('/api/event-analysis/range'):
                    # 处理区间分析查询
                    stock_code = query_params.get('stock_code', [''])[0]
                    start_date = query_params.get('start_date', [''])[0]
                    end_date = query_params.get('end_date', [''])[0]
                    data = get_range_analysis(stock_code, start_date, end_date)
                elif path == '/api/event-analysis/history':
                    data = get_event_impact_history()
                elif path.startswith('/api/stocks/'):
                    # 处理股票相关的API
                    if '/kline-with-events' in path:
                        # 提取股票代码
                        symbol = path.split('/')[3]
                        data = get_stock_kline_with_events(symbol)
                    else:
                        data = {"error": "Not found"}
                        self.send_json_response(data, 404)
                        return
                else:
                    data = {"error": "Not found"}
                    self.send_json_response(data, 404)
                    return

                self.send_json_response(data)
            except Exception as e:
                logger.error(f"API Error: {e}")
                self.send_json_response({"error": str(e)}, 500)

        # CSV 导出路由
        elif path.startswith('/export/'):
            try:
                export_type = path[8:]  # 移除 '/export/'
                filename = f"{export_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

                if export_type == 'trades':
                    trades = get_trades(limit=1000)
                    csv_content = "时间,股票,方向,数量,价格,金额,手续费,原因\n"
                    for t in trades:
                        csv_content += f"{t.get('executed_at', '')},{t.get('symbol', '')},{t.get('direction', '')},{t.get('shares', '')},{t.get('price', '')},{t.get('amount', '')},{t.get('commission', '')},{t.get('reason', '')}\n"
                    self.send_csv_response(filename, csv_content)
                elif export_type == 'positions':
                    positions = get_positions()
                    csv_content = "股票代码,股票名称,持仓数,成本价,当前价,盈亏,盈亏%,止损价,止盈价\n"
                    for p in positions:
                        csv_content += f"{p.get('symbol', '')},{p.get('name', '')},{p.get('shares', '')},{p.get('cost_price', '')},{p.get('current_price', '')},{p.get('profit_loss', '')},{p.get('profit_loss_pct', '')},{p.get('stop_loss', '')},{p.get('take_profit', '')}\n"
                    self.send_csv_response(filename, csv_content)
                elif export_type == 'proposals':
                    proposals = get_proposals(limit=1000)
                    csv_content = "时间,股票,方向,状态,来源,投资逻辑\n"
                    for p in proposals:
                        csv_content += f"{p.get('created_at', '')},{p.get('symbol', '')},{p.get('direction', '')},{p.get('status', '')},{p.get('source_agent', '')},{p.get('thesis', '')}\n"
                    self.send_csv_response(filename, csv_content)
                else:
                    self.send_json_response({"error": "Invalid export type"}, 400)
            except Exception as e:
                logger.error(f"Export Error: {e}")
                self.send_json_response({"error": str(e)}, 500)

        # 主页路由
        elif path == '/' or path == '/index.html':
            self.send_html_response(HTML_CONTENT)

        # 静态文件（简化处理）
        else:
            self.send_json_response({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        """重写日志方法"""
        logger.info(f"{self.address_string()} - {format % args}")


# ==================== HTML 内容（前端） ====================

HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>AI 股票团队监控面板 v2.0</title>
    <!-- ECharts CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        /* CSS Version: 2026-03-17-02 - Fixed grid layout */
        :root {
            --bg-primary: #0A0A0A;
            --bg-secondary: #1A1A1A;
            --bg-card: #0F0F0F;
            --bg-hover: #1F1F1F;
            --text-primary: #FFFFFF;
            --text-secondary: #A0A0A0;
            --text-muted: #666666;
            --accent: #0066FF;
            --accent-hover: #0052CC;
            --success: #00CC66;
            --warning: #FFCC00;
            --error: #FF3333;
            --info: #00B3FF;
            --purple: #9900FF;
            --border: #2A2A2A;
            --border-hover: #3A3A3A;
            --glass: rgba(255, 255, 255, 0.05);
            --glass-border: rgba(255, 255, 255, 0.1);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-size: 14px;
            line-height: 1.6;
            min-height: 100vh;
            margin: 0;
            padding: 0;
            overflow-x: hidden;
            width: 100%;
        }

        html {
            width: 100%;
            height: 100%;
            overflow-y: auto;
            overflow-x: hidden;
        }

        /* 顶部导航栏 */
        .header {
            background: rgba(26, 26, 26, 0.8);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--border);
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 100;
            width: 100%;
            box-sizing: border-box;
        }

        .logo {
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--accent), #00AAFF);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }

        .system-status {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--text-secondary);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .clock {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 16px;
            color: var(--text-primary);
        }

        /* 主布局 */
        .main-layout {
            display: grid;
            grid-template-columns: 240px 1fr 300px;
            min-height: calc(100vh - 64px);
            width: 100%;
            padding-top: 64px;
            position: relative;
            z-index: 1;
        }

        /* 左侧导航栏 */
        .sidebar {
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            height: calc(100vh - 64px);
            position: sticky;
            top: 64px;
            grid-column: 1 / span 1;
        }

        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .nav-item:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }

        .nav-item.active {
            background: var(--accent);
            color: var(--text-primary);
        }

        .nav-icon {
            font-size: 18px;
            width: 24px;
            text-align: center;
        }

        /* 主内容区 */
        .main-content {
            background: var(--bg-primary);
            padding: 24px;
            overflow-y: auto;
            overflow-x: hidden;
            min-height: calc(100vh - 64px);
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
            position: relative;
            z-index: 10;
            grid-column: 2 / span 1;
        }

        /* 主内容区内的页面容器 */
        .main-content > .page {
            width: 100%;
            max-width: 100%;
        }

        .page {
            display: none;
            animation: fadeIn 0.3s ease;
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
        }

        .page.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .page-header {
            margin-bottom: 24px;
        }

        .page-title {
            font-size: 28px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 4px;
        }

        .page-subtitle {
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* 右侧详情面板 */
        .detail-panel {
            background: var(--bg-secondary);
            border-left: 1px solid var(--border);
            padding: 20px;
            overflow-y: auto;
            height: calc(100vh - 64px);
            position: sticky;
            top: 64px;
            grid-column: 3 / span 1;
        }

        /* 卡片 */
        .card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* 事件时间线样式 */
        .event-timeline {
            margin-top: 16px;
        }

        .event-card {
            background: rgba(25, 25, 25, 0.8);
            border: 1px solid var(--glass-border);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
            transition: all 0.2s ease;
        }

        .event-card:hover {
            background: rgba(35, 35, 35, 0.8);
            transform: translateY(-2px);
        }

        .section-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 24px 0 16px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* 统计卡片网格 */
        .search-container {
            padding: 16px 20px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
        }

        .search-input {
            width: 100%;
            padding: 12px 16px 12px 40px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-input:focus {
            border-color: var(--accent);
        }

        .search-button {
            position: absolute;
            left: 36px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
        }

        /* 关键指标卡片 */
        .key-metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .metric-card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }

        .metric-card.primary {
            border-top: 4px solid var(--accent);
        }

        .metric-card.success {
            border-top: 4px solid var(--success);
        }

        .metric-card.info {
            border-top: 4px solid var(--info);
        }

        .metric-card.warning {
            border-top: 4px solid var(--warning);
        }

        .metric-icon {
            font-size: 24px;
            margin-bottom: 12px;
            opacity: 0.8;
        }

        .metric-value {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        .metric-label {
            font-size: 14px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .metric-change {
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .metric-change.positive {
            color: var(--success);
        }

        .metric-change.negative {
            color: var(--error);
        }

        /* 主要内容网格布局 */
        .main-content-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        .main-section {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 24px;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .sidebar-card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 24px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }

        .section-title {
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
        }

        .section-actions {
            display: flex;
            gap: 8px;
        }

        .system-status {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
            color: var(--text-secondary);
        }

        .event-list {
            max-height: 300px;
            overflow-y: auto;
        }

        .event-item {
            padding: 12px;
            margin-bottom: 8px;
            background: rgba(25, 25, 25, 0.8);
            border-radius: 8px;
            border-left: 3px solid var(--accent);
        }

        .event-item:last-child {
            margin-bottom: 0;
        }

        .page-title {
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0 0 8px 0;
        }

        .page-subtitle {
            font-size: 16px;
            color: var(--text-muted);
            margin: 0;
        }

        .stat-card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 20px;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        .stat-value.positive {
            color: var(--success);
        }

        .stat-value.negative {
            color: var(--error);
        }

        .stat-label {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* 闭环状态卡片样式 */
        .loop-card {
            transition: all 0.2s ease;
            cursor: default;
        }

        .loop-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }

        .loop-status {
            margin-top: 8px;
        }

        .loop-breakpoints {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--border);
        }

        .breakpoint-item {
            color: var(--warning);
            font-size: 11px;
            line-height: 1.4;
        }

        /* 表格样式 */
        .table-container {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            text-align: left;
            padding: 12px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-weight: 600;
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 12px;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }

        tr:hover td {
            background: var(--bg-hover);
        }

        /* 状态标签 */
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }

        .badge.active {
            background: rgba(0, 204, 102, 0.2);
            color: var(--success);
        }

        .badge.pending {
            background: rgba(255, 204, 0, 0.2);
            color: var(--warning);
        }

        .badge.error {
            background: rgba(255, 51, 51, 0.2);
            color: var(--error);
        }

        .badge.success {
            background: rgba(0, 204, 102, 0.2);
            color: var(--success);
        }

        /* Agent 卡片 */
        .agent-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }

        .agent-card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 20px;
            border-left: 4px solid var(--accent);
        }

        .agent-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .agent-name {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .agent-role {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }

        .agent-kpi {
            font-size: 11px;
            color: var(--text-muted);
            background: var(--bg-secondary);
            padding: 8px 12px;
            border-radius: 6px;
        }

        /* Cron 任务列表 */
        .cron-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border-radius: 8px;
            margin-bottom: 8px;
        }

        .cron-info {
            flex: 1;
        }

        .cron-name {
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 4px;
        }

        .cron-schedule {
            font-size: 12px;
            color: var(--text-secondary);
        }

        .cron-status {
            font-size: 12px;
            padding: 4px 8px;
            border-radius: 4px;
        }

        .cron-status.success {
            background: rgba(0, 204, 102, 0.2);
            color: var(--success);
        }

        .cron-status.pending {
            background: rgba(255, 204, 0, 0.2);
            color: var(--warning);
        }

        .cron-status.error {
            background: rgba(255, 51, 51, 0.2);
            color: var(--error);
        }

        /* 规则卡片 */
        .rule-item {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
            transition: all 0.2s ease;
        }

        .rule-item.clickable:hover {
            background: var(--bg-hover);
            transform: translateX(4px);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }

        .position-row.clickable:hover {
            background: var(--bg-hover);
        }

        .clickable {
            cursor: pointer;
        }

        .rule-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        .rule-condition {
            font-size: 13px;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        .rule-prediction {
            font-size: 12px;
            color: var(--text-secondary);
        }

        .rule-stats {
            display: flex;
            gap: 12px;
            margin-top: 12px;
        }

        .rule-stat {
            font-size: 12px;
            color: var(--text-muted);
        }

        .rule-stat span {
            color: var(--text-primary);
            font-weight: 600;
        }

        /* 图表容器 */
        .chart-container {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .chart {
            height: 300px;
        }

        /* 响应式设计 */
        @media (max-width: 1200px) {
            .main-layout {
                grid-template-columns: 200px 1fr;
            }
            .detail-panel {
                display: none;
            }
        }

        @media (max-width: 768px) {
            .main-layout {
                grid-template-columns: 1fr;
            }
            .sidebar {
                display: none;
            }
        .stat-card.primary {
            border-top: 4px solid var(--accent);
        }

        .stat-card.success {
            border-top: 4px solid var(--success);
        }

        .stat-card.info {
            border-top: 4px solid var(--info);
        }

        .stat-card.warning {
            border-top: 4px solid var(--warning);
        }

        .stat-icon {
            font-size: 24px;
            margin-bottom: 12px;
            opacity: 0.8;
        }

        /* 仪表盘网格布局 */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-top: 24px;
        }

        .dashboard-main {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .dashboard-sidebar {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .card-actions {
            display: flex;
            gap: 8px;
        }

        .event-list {
            max-height: 300px;
            overflow-y: auto;
        }

        .loop-status-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }

        .system-status {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
            color: var(--text-secondary);
        }

        @media (max-width: 1200px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }
            .stat-value {
                font-size: 24px;
            }
        }

        /* 加载动画 */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* 搜索框 */
        .search-box {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 16px;
            color: var(--text-primary);
            font-size: 14px;
            width: 100%;
            margin-bottom: 16px;
        }

        .search-box:focus {
            outline: none;
            border-color: var(--accent);
        }

        /* 按钮 */
        .btn {
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            border: none;
        }

        .btn-primary {
            background: var(--accent);
            color: var(--text-primary);
        }

        .btn-primary:hover {
            background: var(--accent-hover);
        }

        .btn-secondary {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            background: var(--bg-hover);
        }
    </style>
</head>
<body>
    <!-- 顶部导航栏 -->
    <div class="header">
        <div class="logo">
            <div class="logo-icon">📊</div>
            <span>AI 股票团队监控面板</span>
        </div>
        <div style="flex: 1; max-width: 400px; margin: 0 24px;">
            <input type="text" class="search-box" id="global-search" placeholder="🔍 全局搜索股票、规则、日志..." style="margin: 0;">
        </div>
        <div class="system-status">
            <div class="status-indicator">
                <div class="status-dot"></div>
                <span>系统运行中</span>
            </div>
            <div class="clock" id="clock">00:00:00</div>
        </div>
    </div>

    <!-- 主布局 -->
    <div class="main-layout">
        <!-- 左侧导航栏 -->
        <div class="sidebar">
            <div class="nav-item active" data-page="overview">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                    </svg>
                </span>
                <span>概览</span>
            </div>
            <div class="nav-item" data-page="agents">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                </span>
                <span>Agents</span>
            </div>
            <div class="nav-item" data-page="cron">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </span>
                <span>Cron 任务</span>
            </div>
            <div class="nav-item" data-page="rules">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </span>
                <span>规则库</span>
            </div>
            <div class="nav-item" data-page="validation">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                    </svg>
                </span>
                <span>验证池</span>
            </div>
            <div class="nav-item" data-page="knowledge">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                    </svg>
                </span>
                <span>知识库</span>
            </div>
            <div class="nav-item" data-page="learning">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                    </svg>
                </span>
                <span>学习日志</span>
            </div>
            <div class="nav-item" data-page="trades">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                </span>
                <span>交易历史</span>
            </div>
            <div class="nav-item" data-page="proposals">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                </span>
                <span>提案审批</span>
            </div>
            <div class="nav-item" data-page="watchlist">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                </span>
                <span>监控列表</span>
            </div>
            <div class="nav-item" data-page="risk">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </span>
                <span>风险预警</span>
            </div>
            <div class="nav-item" data-page="kline">
                <span class="nav-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                </span>
                <span>K线分析</span>
            </div>
        </div>

        <!-- 搜索栏 -->
        <div class="search-container">
            <input type="text" id="dashboard-search" placeholder="搜索股票代码或名称..." class="search-input">
            <button class="search-button" onclick="performSearch()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="m21 21-4.35-4.35"/>
                </svg>
            </button>
        </div>
    </nav>
        <div class="main-content">
            <!-- 概览页面 -->
            <div class="page active" id="page-overview">
                <div class="page-header">
                    <h1 class="page-title">📊 投资仪表盘</h1>
                    <p class="page-subtitle">AI股票团队实时监控与分析</p>
                </div>

                <!-- 关键指标卡片 -->
                <div class="stats-grid" id="overview-stats">
                    <div class="stat-card primary">
                        <div class="stat-icon">💰</div>
                        <div class="stat-value" id="stat-total-asset">--</div>
                        <div class="stat-label">总资产 (元)</div>
                    </div>
                    <div class="stat-card success">
                        <div class="stat-icon">📈</div>
                        <div class="stat-value" id="stat-market-value">--</div>
                        <div class="stat-label">持股市值 (元)</div>
                    </div>
                    <div class="stat-card info">
                        <div class="stat-icon">💵</div>
                        <div class="stat-value" id="stat-cash">--</div>
                        <div class="stat-label">可用现金 (元)</div>
                    </div>
                    <div class="stat-card warning">
                        <div class="stat-icon">🎯</div>
                        <div class="stat-value" id="stat-accuracy">--%</div>
                        <div class="stat-label">预测准确率</div>
                    </div>
                </div>

                <!-- 主要内容区域 -->
                <div class="dashboard-grid">
                    <!-- 左侧：持仓列表 -->
                    <div class="dashboard-main">
                        <div class="card">
                            <div class="card-header">
                                <h2 class="section-title">💼 我的持仓</h2>
                                <div class="card-actions">
                                    <button class="btn btn-sm" onclick="refreshPositions()">🔄 刷新</button>
                                    <button class="btn btn-sm" onclick="exportData('positions')">📥 导出</button>
                                </div>
                            </div>
                            
                            <!-- 账户分布图表 -->
                            <div class="chart-container">
                                <div id="chart-account" style="height: 200px;"></div>
                            </div>
                            
                            <!-- 持仓表格 -->
                            <div class="table-container">
                                <table class="data-table" id="overview-positions-table">
                                    <thead>
                                        <tr>
                                            <th>股票代码</th>
                                            <th>名称</th>
                                            <th>持仓</th>
                                            <th>成本价</th>
                                            <th>当前价</th>
                                            <th>市值</th>
                                            <th>盈亏</th>
                                            <th>盈亏%</th>
                                            <th>操作</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <!-- 数据通过 JavaScript 动态填充 -->
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        
                        <!-- 其他图表区域 -->
                        <div class="stats-grid" style="grid-template-columns: repeat(2, 1fr); margin-top: 24px;">
                            <div class="card">
                                <h3 class="card-title">📈 预测准确率</h3>
                                <div id="chart-accuracy" style="height: 200px;"></div>
                            </div>
                            <div class="card">
                                <h3 class="card-title">📊 准确率趋势</h3>
                                <div id="chart-accuracy-trend" style="height: 200px;"></div>
                            </div>
                        </div>
                    </div>

                    <!-- 右侧：事件和系统状态 -->
                    <div class="dashboard-sidebar">
                        <!-- 近期事件 -->
                        <div class="card">
                            <div class="card-header">
                                <h3 class="card-title">📅 近期重大事件</h3>
                                <span class="badge" id="event-count-badge">--</span>
                            </div>
                            <div class="event-list" id="sidebar-event-list">
                                <div class="loading">加载中...</div>
                            </div>
                        </div>

                        <!-- 系统状态 -->
                        <div class="card" style="margin-top: 24px;">
                            <h3 class="card-title">🔧 系统状态</h3>
                            <div class="system-status" id="system-status">
                                <div class="status-item">
                                    <span>AI Agents:</span>
                                    <span class="badge success">运行中</span>
                                </div>
                                <div class="status-item">
                                    <span>数据更新:</span>
                                    <span id="last-update-time">--</span>
                                </div>
                                <div class="status-item">
                                    <span>持仓数量:</span>
                                    <span id="position-count">--</span>
                                </div>
                            </div>
                        </div>

                        <!-- 闭环状态 -->
                        <div class="card" style="margin-top: 24px;">
                            <h3 class="card-title">🔄 闭环状态</h3>
                            <div class="loop-status-grid" id="loop-status-grid"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- K线图页面 -->
            <div class="page" id="page-kline">
                <div class="page-header">
                    <h1 class="page-title">📊 股票K线图</h1>
                    <p class="page-subtitle">带事件标记的K线分析</p>
                </div>
                
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        股票选择
                    </div>
                    <div class="form-group">
                        <label for="kline-stock-select">选择股票:</label>
                        <select id="kline-stock-select" onchange="loadKlineData()" class="form-control">
                            <option value="">请选择股票</option>
                            <!-- 股票列表将通过JavaScript动态填充 -->
                        </select>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        K线图 (带事件标记)
                    </div>
                    <div id="kline-chart-container" style="height: 500px; width: 100%;">
                        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">
                            <span>选择股票查看K线图</span>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        相关事件
                    </div>
                    <div id="kline-events-container">
                        <div style="color: var(--text-muted); text-align: center;">选择股票查看相关事件</div>
                    </div>
                </div>
            </div>

            <!-- Agents 页面 -->
            <div class="page" id="page-agents">
                <div class="page-header">
                    <h1 class="page-title">AI Agents</h1>
                    <p class="page-subtitle">6 个智能体协同工作</p>
                </div>

                <div class="agent-grid" id="agents-grid">
                    <div class="loading" style="margin: 40px auto;"></div>
                </div>
            </div>

            <!-- Cron 任务页面 -->
            <div class="page" id="page-cron">
                <div class="page-header">
                    <h1 class="page-title">Cron 任务调度</h1>
                    <p class="page-subtitle">自动化任务执行状态</p>
                </div>

                <div id="cron-status" class="card">
                    <h2 class="card-title">调度器状态</h2>
                    <div id="cron-runner-status">
                        <span class="loading"></span> 检查中...
                    </div>
                </div>

                <div class="chart-container">
                    <div id="chart-cron-timeline" class="chart"></div>
                </div>

                <div id="cron-tasks"></div>
            </div>

            <!-- 规则库页面 -->
            <div class="page" id="page-rules">
                <div class="page-header">
                    <h1 class="page-title">预测规则库</h1>
                    <p class="page-subtitle">16 条已建立规则</p>
                </div>

                <div id="rules-container"></div>
            </div>

            <!-- 验证池页面 -->
            <div class="page" id="page-validation">
                <div class="page-header">
                    <h1 class="page-title">规则验证池</h1>
                    <p class="page-subtitle">15+ 条待验证规则</p>
                </div>

                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="validation-total">--</div>
                        <div class="stat-label">总规则数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="validation-validating">--</div>
                        <div class="stat-label">验证中</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="validation-verified">--</div>
                        <div class="stat-label">已验证</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="validation-rejected">--</div>
                        <div class="stat-label">已拒绝</div>
                    </div>
                </div>

                <div id="validation-rules"></div>
            </div>

            <!-- 知识库页面 -->
            <div class="page" id="page-knowledge">
                <div class="page-header">
                    <h1 class="page-title">知识库</h1>
                    <p class="page-subtitle">书籍知识和实战经验</p>
                </div>

                <div id="knowledge-container"></div>
            </div>

            <!-- 学习日志页面 -->
            <div class="page" id="page-learning">
                <div class="page-header">
                    <h1 class="page-title">每日学习日志</h1>
                    <p class="page-subtitle">AI 系统持续学习记录</p>
                </div>

                <div id="learning-log"></div>
            </div>

            <!-- 交易历史页面 -->
            <div class="page" id="page-trades">
                <div class="page-header">
                    <h1 class="page-title">交易历史</h1>
                    <p class="page-subtitle">所有交易记录</p>
                </div>

                <div class="card">
                    <div class="table-container">
                        <table id="trades-table">
                            <thead>
                                <tr>
                                    <th>时间</th>
                                    <th>股票</th>
                                    <th>方向</th>
                                    <th>数量</th>
                                    <th>价格</th>
                                    <th>金额</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td colspan="6" style="text-align: center;">加载中...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- 提案审批页面 -->
            <div class="page" id="page-proposals">
                <div class="page-header">
                    <h1 class="page-title">提案审批</h1>
                    <p class="page-subtitle">待处理的交易提案</p>
                </div>

                <div class="card">
                    <div class="table-container">
                        <table id="proposals-table">
                            <thead>
                                <tr>
                                    <th>时间</th>
                                    <th>股票</th>
                                    <th>方向</th>
                                    <th>状态</th>
                                    <th>来源</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td colspan="5" style="text-align: center;">加载中...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- 监控列表页面 -->
            <div class="page" id="page-watchlist">
                <div class="page-header">
                    <h1 class="page-title">监控列表</h1>
                    <p class="page-subtitle">关注的股票列表</p>
                </div>

                <div class="card">
                    <div class="table-container">
                        <table id="watchlist-table">
                            <thead>
                                <tr>
                                    <th>股票代码</th>
                                    <th>股票名称</th>
                                    <th>行业</th>
                                    <th>关注原因</th>
                                    <th>添加时间</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td colspan="5" style="text-align: center;">加载中...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- 风险预警页面 -->
            <div class="page" id="page-risk">
                <div class="page-header">
                    <h1 class="page-title">风险预警</h1>
                    <p class="page-subtitle">实时风险监控与预警</p>
                </div>

                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="risk-total" style="color: var(--warning);">--</div>
                        <div class="stat-label">今日预警</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="risk-high" style="color: var(--error);">--</div>
                        <div class="stat-label">高风险</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="risk-medium" style="color: var(--warning);">--</div>
                        <div class="stat-label">中风险</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="risk-low" style="color: var(--success);">--</div>
                        <div class="stat-label">低风险</div>
                    </div>
                </div>

                <div class="card">
                    <h2 class="card-title">持仓风险评估</h2>
                    <div class="table-container">
                        <table id="risk-positions-table">
                            <thead>
                                <tr>
                                    <th>股票代码</th>
                                    <th>股票名称</th>
                                    <th>持仓市值</th>
                                    <th>风险等级</th>
                                    <th>建议仓位</th>
                                    <th>VaR (95%)</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td colspan="6" style="text-align: center;">加载中...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h2 class="card-title">风险日志</h2>
                    <div id="risk-logs"></div>
                </div>
            </div>
        </div>

        <!-- 右侧详情面板 -->
        <div class="detail-panel">
            <h2 class="card-title">全局搜索</h2>
            <div id="search-results" style="display: none;">
                <p style="color: var(--text-muted); font-size: 12px;">搜索结果</p>
                <div id="search-results-list"></div>
            </div>

            <h2 class="card-title" style="margin-top: 24px;">实时通知</h2>
            <div id="notifications">
                <p style="color: var(--text-muted); font-size: 12px;">暂无新通知</p>
            </div>

            <h2 class="card-title" style="margin-top: 24px;">数据导出</h2>
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <button class="btn btn-secondary" onclick="exportData('positions')">📥 导出持仓</button>
                <button class="btn btn-secondary" onclick="exportData('trades')">📥 导出交易</button>
                <button class="btn btn-secondary" onclick="exportData('proposals')">📥 导出提案</button>
            </div>

            <h2 class="card-title" style="margin-top: 24px;">快速操作</h2>
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <button class="btn btn-primary" onclick="refreshAll()">🔄 刷新所有数据</button>
                <button class="btn btn-secondary" onclick="refreshRealtimePrices()">💹 获取实时价格</button>
            </div>
        </div>
    </div>

    <script>
        // ==================== 全局变量 ====================
        let charts = {};
        let currentTab = 'overview';

        // ==================== 时钟更新 ====================
        function updateClock() {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
            document.getElementById('clock').textContent = timeStr;
        }
        setInterval(updateClock, 1000);
        updateClock();

        // ==================== 页面导航 ====================
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function() {
                const page = this.dataset.page;
                if (!page) return;

                // 更新导航状态
                document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
                this.classList.add('active');

                // 切换页面
                document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                document.getElementById('page-' + page).classList.add('active');

                currentTab = page;

                // 加载页面数据
                loadPageData(page);
            });
        });

        // ==================== API 调用 ====================
        async function fetchAPI(endpoint) {
            try {
                const response = await fetch('/api' + endpoint);
                const data = await response.json();
                if (data.error) {
                    console.error('API Error:', data.error);
                    return null;
                }
                return data;
            } catch (error) {
                console.error('Fetch Error:', error);
                return null;
            }
        }

        // ==================== 加载页面数据 ====================
        async function loadPageData(page) {
            switch(page) {
                case 'overview':
                    loadOverviewData();
                    break;
                case 'agents':
                    loadAgentsData();
                    break;
                case 'cron':
                    loadCronData();
                    break;
                case 'rules':
                    loadRulesData();
                    break;
                case 'validation':
                    loadValidationPoolData();
                    break;
                case 'knowledge':
                    loadKnowledgeData();
                    break;
                case 'learning':
                    loadLearningLogData();
                    break;
                case 'trades':
                    loadTradesData();
                    break;
                case 'proposals':
                    loadProposalsData();
                    break;
                case 'watchlist':
                    loadWatchlistData();
                    break;
                case 'agent-logs':
                    loadAgentLogs('all');
                    break;
                case 'risk':
                    loadRiskData();
                    break;
                case 'kline':
                    initializeKlinePage();
                    break;
            }
        }

        // ==================== K线图页面 ====================
        async function initializeKlinePage() {
            // 获取持仓股票列表填充选择框
            try {
                const overviewData = await fetchAPI('/overview');
                if (overviewData && overviewData.positions && overviewData.positions.length > 0) {
                    const select = document.getElementById('kline-stock-select');
                    select.innerHTML = '<option value="">请选择股票</option>';
                    overviewData.positions.forEach(pos => {
                        const option = document.createElement('option');
                        option.value = pos.symbol;
                        option.textContent = `${pos.name} (${pos.symbol})`;
                        select.appendChild(option);
                    });
                }
            } catch (error) {
                console.error('Failed to load positions for kline page:', error);
            }
        }

        async function loadKlineData() {
            const symbol = document.getElementById('kline-stock-select').value;
            if (!symbol) {
                document.getElementById('kline-chart-container').innerHTML =
                    '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">选择股票查看K线图</div>';
                document.getElementById('kline-events-container').innerHTML =
                    '<div style="color: var(--text-muted); text-align: center;">选择股票查看相关事件</div>';
                return;
            }

            try {
                // 加载K线数据
                const klineData = await fetchAPI(`/stocks/${symbol}/kline-with-events`);
                if (!klineData || !klineData.kline_data || klineData.kline_data.length === 0) {
                    throw new Error('No kline data available');
                }

                // 使用 ECharts 渲染 K线图
                const chartDom = document.getElementById('kline-chart-container');
                chartDom.innerHTML = ''; // 清空容器

                if (charts.kline) {
                    charts.kline.dispose();
                }
                charts.kline = echarts.init(chartDom);

                // 准备 K线数据 [open, close, lowest, highest]
                const klineDataArray = klineData.kline_data.map(d => [
                    d.open || 0,
                    d.close || 0,
                    d.lowest || d.low || 0,
                    d.highest || d.high || 0
                ]);

                // 准备事件标记数据
                const markLineData = (klineData.events || []).map(event => {
                    // 找到事件日期在 K线数据中的位置
                    const eventDate = event.kline_start_date || event.date;
                    const dataIndex = klineData.kline_data.findIndex(d => d.date === eventDate);
                    if (dataIndex >= 0) {
                        return {
                            name: event.title || '事件',
                            xAxis: dataIndex,
                            lineStyle: {
                                color: event.sentiment === 'positive' ? '#00CC66' : event.sentiment === 'negative' ? '#FF3333' : '#FFCC00',
                                type: 'dashed',
                                width: 2
                            },
                            label: {
                                formatter: '{name}',
                                color: event.sentiment === 'positive' ? '#00CC66' : event.sentiment === 'negative' ? '#FF3333' : '#FFCC00'
                            }
                        };
                    }
                    return null;
                }).filter(Boolean);

                const option = {
                    title: {
                        text: `${symbol} 近30天K线图`,
                        textStyle: { color: '#FFFFFF', fontSize: 14 },
                        left: 'center',
                        top: 5
                    },
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: { type: 'shadow' },
                        formatter: function(params) {
                            const param = params[0];
                            const date = param.name;
                            const data = param.data;
                            if (!data || data.length !== 4) return;
                            return `
                                <div style="font-weight: 600;">${date}</div>
                                <div>开: ${data[0].toFixed(2)}</div>
                                <div>收: ${data[1].toFixed(2)}</div>
                                <div>低: ${data[2].toFixed(2)}</div>
                                <div>高: ${data[3].toFixed(2)}</div>
                            `;
                        }
                    },
                    axisPointer: {
                        link: { xAxisIndex: 'all' }
                    },
                    grid: [
                        {
                            left: 60,
                            right: 60,
                            top: 50,
                            bottom: 40
                        }
                    ],
                    xAxis: [
                        {
                            type: 'category',
                            data: klineData.kline_data.map(d => d.date),
                            scale: true,
                            boundaryGap: false,
                            axisLine: { lineStyle: { color: '#666' } },
                            splitLine: { show: false },
                            axisLabel: { color: '#A0A0A0', fontSize: 10 }
                        }
                    ],
                    yAxis: [
                        {
                            scale: true,
                            axisLine: { lineStyle: { color: '#666' } },
                            splitLine: { show: true, lineStyle: { color: '#2A2A2A' } },
                            axisLabel: { color: '#A0A0A0', fontSize: 10 }
                        }
                    ],
                    axisPointer: {
                        link: { xAxisIndex: 'all' }
                    },
                    dataZoom: [
                        {
                            type: '内置于'
                        },
                        {
                            type: 'slider',
                            show: true,
                            xAxisIndex: 0,
                            start: 30,
                            end: 100,
                            handleSize: 8,
                            height: 10,
                            handleColor: '#0066FF',
                            borderColor: '#3A3A3A'
                        }
                    ],
                    series: [
                        {
                            name: 'K线',
                            type: 'candlestick',
                            data: klineDataArray,
                            itemStyle: {
                                color: '#FF3333', // 红色代表上涨
                                color0: '#00CC66', // 绿色代表下跌
                                borderColor: '#FF3333',
                                borderColor0: '#00CC66'
                            },
                            tooltip: { show: true }
                        },
                        {
                            name: '成交量',
                            type: 'bar',
                            xAxisIndex: 1,
                            yAxisIndex: 1,
                            data: klineData.kline_data.map(d => ({
                                value: d.volume || 0,
                                itemStyle: {
                                    color: function(param) {
                                        const data = param.data;
                                        if (data && data.length === 4) {
                                            return data[1] > data[0] ? '#FF3333' : '#00CC66';
        /* 主容器 */
        .container {
            display: flex;
            min-height: 100vh;
            background: var(--bg-primary);
            color: var(--text-primary);
        }

        nav {
            width: 280px;
            background: #080808;
            border-right: 1px solid rgba(255, 255, 255, 0.1);
            overflow-y: auto;
            position: fixed;
            height: 100vh;
            padding-bottom: 80px;
        }

        .main-content {
            margin-left: 280px;
            padding: 32px;
            width: calc(100% - 280px);
            max-width: 1400px;
            margin: 0 auto;
        }

        /* 响应式设计 */
        @media (max-width: 1200px) {
            nav {
                width: 240px;
            }
            .main-content {
                margin-left: 240px;
                width: calc(100% - 240px);
                padding: 24px;
            }
            .key-metrics-grid {
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
        }

        @media (max-width: 992px) {
            .main-content-grid {
                grid-template-columns: 1fr;
            }
            nav {
                width: 200px;
            }
            .main-content {
                margin-left: 200px;
                width: calc(100% - 200px);
            }
        }

        @media (max-width: 768px) {
            nav {
                position: relative;
                width: 100%;
                height: auto;
                border-right: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            .main-content {
                margin-left: 0;
                width: 100%;
                padding: 16px;
            }
            .key-metrics-grid {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }
            .metric-value {
                font-size: 24px;
            }
        }

        /* 按钮样式 */
        .btn {
            padding: 8px 16px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }

        .btn:hover {
            background: var(--bg-hover);
            border-color: var(--accent);
        }

        .btn-sm {
            padding: 6px 12px;
            font-size: 11px;
        }

        .btn-primary {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }

        .btn-primary:hover {
            background: var(--accent-hover);
            border-color: var(--accent-hover);
        }

        .btn-secondary {
            background: transparent;
        }

        /* 数据表格 */
        .data-table {
            width: 100%;
            border-collapse: collapse;
        }

        .data-table th,
        .data-table td {
            padding: 12px 8px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        .data-table th {
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }

        .data-table tbody tr:hover {
            background: var(--bg-hover);
        }

        .positive {
            color: var(--success);
        }

        .negative {
            color: var(--error);
        }

        /* 图表容器 */
        .chart-container {
            background: var(--bg-card);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }

        .chart {
            height: 250px !important;
            width: 100% !important;
        }

        /* 卡片样式 */
        .card {
            background: rgba(15, 15, 15, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            background: var(--bg-hover);
            color: var(--text-primary);
        }

        .badge.success {
            background: var(--success);
            color: #000;
        }

        .badge.error {
            background: var(--error);
            color: #FFF;
        }

        .badge.warning {
            background: var(--warning);
            color: #000;
        }

        .badge.pending {
            background: var(--text-muted);
            color: #FFF;
        }

        /* 加载状态 */
        .loading {
            text-align: center;
            color: var(--text-muted);
            padding: 20px;
        }

        /* 通知区域 */
        #notifications {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1000;
            max-width: 300px;
        }
                                        return '#999';
                                    }
                                }
                            })),
                            itemStyle: {
                                color: '#999'
                            },
                            opacity: 0.5
                        }
                    ]
                };

                // 添加事件标记线
                if (markLineData.length > 0) {
                    option.series.push({
                        name: '事件',
                        type: 'line',
                        data: markLineData.map((md, idx) => ({
                            xAxis: md.xAxis,
                            yAxis: 'max'
                        })),
                        markLine: {
                            data: markLineData,
                            lineStyle: {
                                color: '#FFCC00',
                                type: 'dashed'
                            }
                        },
                        symbol: 'none',
                        lineStyle: {
                            color: '#FFCC00',
                            type: 'dashed'
                        },
                        label: {
                            formatter: '{name}',
                            color: '#FFCC00'
                        }
                    });
                }

                charts.kline.setOption(option);
                window.addEventListener('resize', () => charts.kline.resize());

                // 显示相关事件
                if (klineData.events && klineData.events.length > 0) {
                    let eventsHtml = '<div class="event-list">';
                    klineData.events.forEach(event => {
                        const sentimentColor = event.sentiment === 'positive' ? 'green' :
                                            event.sentiment === 'negative' ? 'red' : 'yellow';
                        const eventType = Array.isArray(event.event_types) ? event.event_types.join(', ') : event.event_types;

                        eventsHtml += `
                        <div class="event-item" style="padding: 12px; margin-bottom: 8px; background: rgba(25,25,25,0.8); border-radius: 6px; border-left: 3px solid ${sentimentColor === 'green' ? '#00CC66' : sentimentColor === 'red' ? '#FF3333' : '#FFCC00'};">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                <span style="background: ${sentimentColor === 'green' ? 'rgba(0,204,102,0.2)' :
                                            sentimentColor === 'red' ? 'rgba(255,51,51,0.2)' : 'rgba(255,204,0,0.2)'};
                                      color: ${sentimentColor === 'green' ? '#00CC66' :
                                              sentimentColor === 'red' ? '#FF3333' : '#FFCC00'};
                                      padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                                    ${event.sentiment}
                                </span>
                                <strong>${event.title}</strong>
                            </div>
                            <p style="color: #999; font-size: 12px; margin: 4px 0;">
                                日期: ${event.kline_start_date} | 影响分数: ${event.impact_score ? event.impact_score.toFixed(0) : 'N/A'}
                            </p>
                            <p style="color: #999; font-size: 12px; margin: 4px 0;">
                                事件类型: ${eventType}
                            </p>
                        </div>
                        `;
                    });
                    eventsHtml += '</div>';
                    document.getElementById('kline-events-container').innerHTML = eventsHtml;
                } else {
                    document.getElementById('kline-events-container').innerHTML =
                        '<div style="color: var(--text-muted); text-align: center;">暂无相关事件</div>';
                }

            } catch (error) {
                console.error('Failed to load kline data:', error);
                document.getElementById('kline-chart-container').innerHTML =
                    '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-error);">加载失败，请稍后重试</div>';
                document.getElementById('kline-events-container').innerHTML =
                    '<div style="color: var(--text-error); text-align: center;">加载事件数据失败</div>';
            }
        }

        // ==================== 概览数据 ====================
        async function loadOverviewData() {
            const data = await fetchAPI('/overview');
            if (!data) return;

            // 更新统计数据
            document.getElementById('stat-total-asset').textContent =
                data.account.total_asset.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            document.getElementById('stat-market-value').textContent =
                data.account.market_value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            document.getElementById('stat-cash').textContent =
                data.account.cash.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            const profitEl = document.getElementById('stat-profit');
            if (profitEl) {
                profitEl.textContent = data.account.profit_loss.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                profitEl.className = 'stat-value ' + (data.account.profit_loss >= 0 ? 'positive' : 'negative');
            }

            document.getElementById('stat-accuracy').textContent = data.accuracy.accuracy_rate + '%';

            // 获取事件数据
            const eventData = await fetchAPI('/event-analysis');
            if (eventData && eventData.recent_events) {
                document.getElementById('stat-event-count').textContent = eventData.recent_events.length;
                document.getElementById('event-count-badge').textContent = eventData.recent_events.length;
                renderSidebarEventList(eventData.recent_events);
            }

            // 更新持仓表格
            const positionsTable = document.querySelector('#overview-positions-table tbody');
            if (data.positions.length > 0) {
                positionsTable.innerHTML = data.positions.map(pos => {
                    const marketValue = pos.shares * pos.current_price;
                    return `
                        <tr class="position-row clickable" style="cursor: pointer;" data-symbol="${pos.symbol}" data-position='${JSON.stringify(pos)}'>
                            <td>${pos.symbol}</td>
                            <td>${pos.name || '--'}</td>
                            <td>${pos.shares}</td>
                            <td>¥${pos.cost_price ? pos.cost_price.toFixed(2) : '--'}</td>
                            <td>¥${pos.current_price ? pos.current_price.toFixed(2) : '--'}</td>
                            <td>¥${marketValue ? marketValue.toFixed(2) : '--'}</td>
                            <td class="${pos.profit_loss >= 0 ? 'positive' : 'negative'}">
                                ¥${pos.profit_loss ? pos.profit_loss.toFixed(2) : '--'}
                            </td>
                            <td class="${pos.profit_loss_pct >= 0 ? 'positive' : 'negative'}">
                                ${pos.profit_loss_pct ? pos.profit_loss_pct.toFixed(2) : '--'}%
                            </td>
                            <td>
                                <button class="btn btn-sm" onclick="showPositionDetails('${pos.symbol}')">详情</button>
                            </td>
                        </tr>
                    `;
                }).join('');
                
                // 更新系统状态
                document.getElementById('position-count').textContent = data.positions.length;
            } else {
                positionsTable.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">暂无持仓数据</td></tr>';
                document.getElementById('position-count').textContent = '0';
            }

            // 更新系统状态时间
            document.getElementById('last-update-time').textContent = new Date().toLocaleTimeString('zh-CN');

            // 更新图表
            updateAccuracyChart(data.accuracy);
            updateAccountChart(data.account);
            
            // 更新闭环状态
            await loadLoopStatus();
            await loadAccuracyTrend();
        }

        function renderSidebarEventList(events) {
            const eventListEl = document.getElementById('sidebar-event-list');
            if (!events || events.length === 0) {
                eventListEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">暂无近期事件</p>';
                return;
            }

            let html = '';
            events.forEach(event => {
                const sentimentColor = event.sentiment === 'positive' ? 'green' : 
                                    event.sentiment === 'negative' ? 'red' : 'yellow';
                const eventType = Array.isArray(event.event_types) ? event.event_types.join(', ') : event.event_types;
                
                html += `
                <div class="event-item" style="padding: 12px; margin-bottom: 8px; background: rgba(25,25,25,0.8); border-radius: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span style="background: ${sentimentColor === 'green' ? 'rgba(0,204,102,0.2)' : 
                                    sentimentColor === 'red' ? 'rgba(255,51,51,0.2)' : 'rgba(255,204,0,0.2)'}; 
                              color: ${sentimentColor === 'green' ? '#00CC66' : 
                                      sentimentColor === 'red' ? '#FF3333' : '#FFCC00'};
                              padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                            ${event.sentiment}
                        </span>
                        <strong style="font-size: 13px;">${event.title}</strong>
                    </div>
                    <p style="color: #999; font-size: 12px; margin: 4px 0;">
                        ${event.stock_name} (${event.stock_code}) | ${event.kline_start_date}
                    </p>
                    <p style="color: #999; font-size: 12px; margin: 4px 0;">
                        ${eventType} | 影响: ${event.impact_score ? event.impact_score.toFixed(0) : 'N/A'}
                    </p>
                </div>
                `;
            });
            eventListEl.innerHTML = html;
        }

            // 更新持仓表格
            const positionsTable = document.querySelector('#overview-positions-table tbody');
            if (data.positions.length > 0) {
                positionsTable.innerHTML = data.positions.map(pos => {
                    const marketValue = pos.shares * pos.current_price;
                    return `
                        <tr class="position-row clickable" style="cursor: pointer;" data-symbol="${pos.symbol}" data-position='${JSON.stringify(pos)}'>
                            <td>${pos.symbol}</td>
                            <td>${pos.name || '--'}</td>
                            <td>${pos.shares}</td>
                            <td>¥${pos.cost_price ? pos.cost_price.toFixed(2) : '--'}</td>
                            <td>¥${pos.current_price ? pos.current_price.toFixed(2) : '--'}</td>
                            <td>¥${marketValue ? marketValue.toFixed(2) : '--'}</td>
                            <td class="${pos.profit_loss >= 0 ? 'positive' : 'negative'}">
                                ¥${pos.profit_loss ? pos.profit_loss.toFixed(2) : '--'}
                            </td>
                            <td class="${pos.profit_loss_pct >= 0 ? 'positive' : 'negative'}">
                                ${pos.profit_loss_pct ? pos.profit_loss_pct.toFixed(2) : '--'}%
                            </td>
                            <td>
                                <button class="btn btn-sm" onclick="showPositionDetails('${pos.symbol}')">详情</button>
                            </td>
                        </tr>
                    `;
                }).join('');
                
                // 更新系统状态
                document.getElementById('position-count').textContent = data.positions.length;
            } else {
                positionsTable.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">暂无持仓数据</td></tr>';
                document.getElementById('position-count').textContent = '0';
            }

            // 更新系统状态
            document.getElementById('last-update-time').textContent = new Date().toLocaleTimeString('zh-CN');

            // 更新图表
            updateAccuracyChart(data.accuracy);
            updateAccountChart(data.account);
            await loadLoopStatus();
            await loadAccuracyTrend();
        }

        function renderSidebarEventList(events) {
            const eventListEl = document.getElementById('sidebar-event-list');
            if (!events || events.length === 0) {
                eventListEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">暂无近期事件</p>';
                return;
            }

            let html = '';
            events.forEach(event => {
                const sentimentColor = event.sentiment === 'positive' ? 'green' : 
                                    event.sentiment === 'negative' ? 'red' : 'yellow';
                const eventType = Array.isArray(event.event_types) ? event.event_types.join(', ') : event.event_types;
                
                html += `
                <div class="event-item">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span style="background: ${sentimentColor === 'green' ? 'rgba(0,204,102,0.2)' : 
                                    sentimentColor === 'red' ? 'rgba(255,51,51,0.2)' : 'rgba(255,204,0,0.2)'}; 
                              color: ${sentimentColor === 'green' ? '#00CC66' : 
                                      sentimentColor === 'red' ? '#FF3333' : '#FFCC00'};
                              padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                            ${event.sentiment}
                        </span>
                        <strong style="font-size: 14px;">${event.title}</strong>
                    </div>
                    <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                        ${event.stock_name} (${event.stock_code}) | ${event.kline_start_date}
                    </p>
                    <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                        ${eventType} | 影响: ${event.impact_score ? event.impact_score.toFixed(0) : 'N/A'}
                    </p>
                </div>
                `;
            });
            eventListEl.innerHTML = html;
        }

            // 更新持仓表格
            const positionsTable = document.querySelector('#overview-positions-table tbody');
            if (data.positions.length > 0) {
                positionsTable.innerHTML = data.positions.map(pos => `
                    <tr class="position-row clickable" style="cursor: pointer;" data-symbol="${pos.symbol}" data-position='${JSON.stringify(pos)}'>
                        <td>${pos.symbol}</td>
                        <td>${pos.name || '--'}</td>
                        <td>${pos.shares}</td>
                        <td>¥${pos.cost_price ? pos.cost_price.toFixed(2) : '--'}</td>
                        <td>¥${pos.current_price ? pos.current_price.toFixed(2) : '--'}</td>
                        <td class="${pos.profit_loss >= 0 ? 'positive' : 'negative'}">
                            ¥${pos.profit_loss ? pos.profit_loss.toFixed(2) : '--'}
                        </td>
                        <td class="${pos.profit_loss_pct >= 0 ? 'positive' : 'negative'}">
                            ${pos.profit_loss_pct ? pos.profit_loss_pct.toFixed(2) : '--'}%
                        </td>
                        <td>
                            <button class="btn btn-sm" onclick="showPositionDetails('${pos.symbol}')">详情</button>
                        </td>
                        </tr>
                    `).join('');
                } else {
                    positionsTable.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">暂无持仓数据</td></tr>';
                    document.getElementById('position-count').textContent = '0';
                }

                // 更新系统状态时间
                document.getElementById('last-update-time').textContent = new Date().toLocaleTimeString('zh-CN');

                // 更新图表
                updateAccuracyChart(data.accuracy);
                updateAccountChart(data.account);
                
                // 更新闭环状态
                await loadLoopStatus();
                await loadAccuracyTrend();
            }

        // 更新准确率图表
        updateAccuracyChart(data.accuracy);

        // 更新账户分布图表
        updateAccountChart(data.account);

        // 更新闭环状态
        await loadLoopStatus();

            // 更新准确率趋势
            await loadAccuracyTrend();
        }

        function renderEventTimeline(events) {
            const timelineEl = document.getElementById('event-timeline');
            if (!events || events.length === 0) {
                timelineEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">暂无近期事件</p>';
                return;
            }

            let html = '';
            events.forEach(event => {
                const sentimentColor = event.sentiment === 'positive' ? 'green' : 
                                    event.sentiment === 'negative' ? 'red' : 'yellow';
                const eventType = Array.isArray(event.event_types) ? event.event_types.join(', ') : event.event_types;
                
                html += `
                <div class="event-card" style="margin-bottom: 12px; padding: 12px; border-radius: 8px; background: var(--bg-card);">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                <span style="background: ${sentimentColor === 'green' ? 'rgba(0,204,102,0.2)' : 
                                            sentimentColor === 'red' ? 'rgba(255,51,51,0.2)' : 'rgba(255,204,0,0.2)'}; 
                                      color: ${sentimentColor === 'green' ? '#00CC66' : 
                                              sentimentColor === 'red' ? '#FF3333' : '#FFCC00'};
                                      padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">
                                    ${event.sentiment}
                                </span>
                                <h4 style="font-weight: 600; margin: 0; font-size: 14px;">${event.title}</h4>
                            </div>
                            <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                                ${event.stock_name} (${event.stock_code}) | 日期: ${event.kline_start_date}
                            </p>
                             <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                                 事件类型: ${eventType} | 影响分数: ${event.impact_score ? event.impact_score.toFixed(0) : 'N/A'}
                             </p>
                             <p style="color: var(--text-muted); font-size: 12px; margin: 4px 0;">
                                 1日涨跌: ${event.day1_change ? event.day1_change.toFixed(2) : 'N/A'}% | 
                                 5日涨跌: ${event.day5_change ? event.day5_change.toFixed(2) : 'N/A'}%
                             </p>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <button class="btn btn-sm" onclick="showStockKlineWithEvents('${event.stock_code}')">
                                K线图
                            </button>
                        </div>
                    </div>
                </div>
                `;
            });
            timelineEl.innerHTML = html;
        }

        function showStockKlineWithEvents(symbol) {
            // 这里可以打开一个模态框显示K线图
            alert('K线图功能将在下一阶段实现: ' + symbol);
        }

        // ==================== 准确率趋势数据 ====================
        async function loadAccuracyTrend() {
            const data = await fetchAPI('/accuracy-trend');
            if (!data) return;

            updateAccuracyTrendChart(data.trend_data, data.trend_analysis);
        }

        // ==================== 闭环状态数据 ====================
        async function loadLoopStatus() {
            const data = await fetchAPI('/loop-status');
            if (!data) return;

            const loopGrid = document.getElementById('loop-status-grid');
            const loopKeys = ['data', 'rules', 'validation', 'learning'];
            const loopLabels = {
                'data': '数据闭环',
                'rules': '规则闭环',
                'validation': '验证闭环',
                'learning': '学习闭环'
            };
            const loopColors = {
                'data': '#00CC66',
                'rules': '#0066FF',
                'validation': '#FFCC00',
                'learning': '#9900FF'
            };

            loopGrid.innerHTML = loopKeys.map(key => {
                const loop = data.loops[key];
                const score = loop.score;
                const statusClass = score >= 80 ? 'success' : (score >= 60 ? 'warning' : 'error');
                const statusColor = score >= 80 ? '#00CC66' : (score >= 60 ? '#FFCC00' : '#FF3333');
                const hasBreakpoints = loop.breakpoints && loop.breakpoints.length > 0;

                return `
                    <div class="stat-card loop-card" style="border-top: 3px solid ${statusColor};">
                        <div class="stat-value" style="color: ${statusColor};">${score}%</div>
                        <div class="stat-label">${loop.name}</div>
                        <div class="loop-status">
                            <span class="badge ${statusClass}">${loop.status}</span>
                        </div>
                        ${hasBreakpoints ? `
                            <div class="loop-breakpoints">
                                <div style="font-size: 11px; color: var(--text-muted); margin-top: 8px;">⚠️ 断点:</div>
                                ${loop.breakpoints.map(bp => `
                                    <div class="breakpoint-item" style="font-size: 11px; margin-top: 4px;">
                                        ${bp.message}
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('');

            // 更新建议
            const recommendationsEl = document.getElementById('loop-recommendations');
            if (data.recommendations && data.recommendations.length > 0) {
                recommendationsEl.innerHTML = `
                    <div style="background: var(--bg-hover); padding: 12px; border-radius: 8px; border-left: 3px solid var(--warning);">
                        <div style="font-size: 12px; font-weight: 600; color: var(--warning); margin-bottom: 8px;">💡 改进建议</div>
                        ${data.recommendations.map(rec => `
                            <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">• ${rec}</div>
                        `).join('')}
                    </div>
                `;
            } else {
                recommendationsEl.innerHTML = '';
            }
        }

        // ==================== Agents 数据 ====================
        async function loadAgentsData() {
            const data = await fetchAPI('/agents');
            if (!data) return;

            const agentsGrid = document.getElementById('agents-grid');
            agentsGrid.innerHTML = data.agents.map(agent => `
                <div class="agent-card" style="border-left-color: ${agent.color || 'var(--accent)'}">
                    <div class="agent-header">
                        <div class="agent-name">${agent.name}</div>
                        <span class="badge ${agent.status === 'active' ? 'success' : 'error'}">${agent.status}</span>
                    </div>
                    <div class="agent-role">${agent.role}</div>
                    <div class="agent-kpi">KPI: ${agent.kpi}</div>
                </div>
            `).join('');
        }

        // ==================== Cron 数据 ====================
        async function loadCronData() {
            const data = await fetchAPI('/cron');
            if (!data) return;

            // 更新调度器状态
            const runnerStatus = document.getElementById('cron-runner-status');
            if (data.is_running) {
                runnerStatus.innerHTML = '<span class="status-dot"></span> 调度器运行中';
            } else {
                runnerStatus.innerHTML = '<span class="badge error">调度器未运行</span>';
            }

            // 更新任务列表
            const tasksContainer = document.getElementById('cron-tasks');
            tasksContainer.innerHTML = data.tasks.map(task => `
                <div class="cron-item">
                    <div class="cron-info">
                        <div class="cron-name">${task.name}</div>
                        <div class="cron-schedule">⏰ ${task.schedule} | ${task.description || ''}</div>
                    </div>
                    <div>
                        <span class="cron-status ${task.last_status || 'pending'}">${task.last_status || 'pending'}</span>
                    </div>
                </div>
            `).join('');

            // 更新Cron时间线图表
            updateCronTimelineChart(data.tasks);
        }

        // ==================== 规则数据 ====================
        async function loadRulesData() {
            const data = await fetchAPI('/rules');
            if (!data) return;

            // 保存所有规则到全局变量，供点击事件使用
            window.currentRules = {};
            Object.values(data.rules || {}).forEach(categoryRules => {
                Object.entries(categoryRules || {}).forEach(([ruleId, rule]) => {
                    window.currentRules[ruleId] = rule;
                });
            });

            const container = document.getElementById('rules-container');
            const categories = [
                { key: 'direction_rules', title: '方向规则', icon: '📈' },
                { key: 'magnitude_rules', title: '幅度规则', icon: '📊' },
                { key: 'timing_rules', title: '时机规则', icon: '⏱️' },
                { key: 'confidence_rules', title: '置信度规则', icon: '🎯' }
            ];

            container.innerHTML = categories.map(cat => {
                const rules = Object.entries(data.rules[cat.key] || {});
                return `
                    <div class="card">
                        <h2 class="card-title">${cat.icon} ${cat.title} (${rules.length})</h2>
                        ${rules.length > 0 ? rules.map(([ruleId, rule]) => `
                            <div class="rule-item clickable" style="cursor: pointer;" data-rule-id="${ruleId}">
                                <div class="rule-header">
                                    <span style="font-weight: 600;">${ruleId}</span>
                                    <span class="badge ${rule.success_rate >= 60 ? 'success' : 'pending'}">
                                        ${rule.success_rate || 0}%
                                    </span>
                                </div>
                                <div class="rule-condition">${rule.condition}</div>
                                <div class="rule-prediction">${rule.prediction}</div>
                                <div class="rule-stats">
                                    <div class="rule-stat">样本: <span>${rule.samples || 0}</span></div>
                                    <div class="rule-stat">来源: <span>${rule.source}</span></div>
                                </div>
                            </div>
                        `).join('') : '<p style="color: var(--text-muted);">暂无规则</p>'}
                    </div>
                `;
            }).join('');

            // 添加点击事件
            container.querySelectorAll('.rule-item').forEach(item => {
                item.addEventListener('click', function() {
                    const ruleId = this.dataset.ruleId;
                    const rule = window.currentRules?.[ruleId];
                    if (rule) {
                        showRuleHistory(ruleId, rule);
                    }
                });
            });
        }

        // ==================== 验证池数据 ====================
        async function loadValidationPoolData() {
            const data = await fetchAPI('/validation-pool');
            if (!data) return;

            // 更新统计
            document.getElementById('validation-total').textContent = data.stats.total;
            document.getElementById('validation-validating').textContent = data.stats.by_status.validating || 0;
            document.getElementById('validation-verified').textContent = data.stats.by_status.verified || 0;
            document.getElementById('validation-rejected').textContent = data.stats.by_status.rejected || 0;

            // 显示规则
            const container = document.getElementById('validation-rules');
            const rules = Object.entries(data.pool || {}).slice(0, 20);

            if (rules.length > 0) {
                container.innerHTML = rules.map(([ruleId, rule]) => `
                    <div class="rule-item">
                        <div class="rule-header">
                            <span style="font-weight: 600;">${ruleId}</span>
                            <span class="badge ${rule.status === 'verified' ? 'success' : rule.status === 'rejected' ? 'error' : 'pending'}">
                                ${rule.status}
                            </span>
                        </div>
                        <div class="rule-condition">${rule.rule}</div>
                        <div class="rule-prediction">${rule.testable_form}</div>
                        <div class="rule-stats">
                            <div class="rule-stat">分类: <span>${rule.category}</span></div>
                            <div class="rule-stat">置信度: <span>${(rule.confidence * 100).toFixed(0)}%</span></div>
                            <div class="rule-stat">样本: <span>${rule.live_test?.samples || 0}</span></div>
                        </div>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: var(--text-muted);">暂无待验证规则</p>';
            }
        }

        // ==================== 知识库数据 ====================
        async function loadKnowledgeData() {
            const data = await fetchAPI('/knowledge');
            if (!data) return;

            const container = document.getElementById('knowledge-container');

            // 书籍知识
            const books = Object.entries(data.book_knowledge || {});
            let html = '';

            if (books.length > 0) {
                html += '<div class="card"><h2 class="card-title">📚 书籍学习</h2>';
                html += books.map(([bookId, book]) => `
                    <div style="margin-bottom: 20px;">
                        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">
                            ${book.title}
                        </h3>
                        <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 8px;">
                            作者: ${book.author} | 学习日期: ${book.learned_date}
                        </p>
                        <div style="background: var(--bg-secondary); border-radius: 8px; padding: 12px;">
                            ${book.key_points?.map(point => `
                                <div style="margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border);">
                                    <div style="font-size: 13px; font-weight: 500;">${point.content}</div>
                                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                                        ${point.testable_rule}
                                    </div>
                                </div>
                            `).join('') || '<p style="color: var(--text-muted);">暂无知识点</p>'}
                        </div>
                    </div>
                `).join('');
                html += '</div>';
            }

            container.innerHTML = html || '<p style="color: var(--text-muted);">暂无知识</p>';
        }

        // ==================== 学习日志数据 ====================
        async function loadLearningLogData() {
            const data = await fetchAPI('/learning-log');
            if (!data) return;

            const container = document.getElementById('learning-log');

            if (data.log && data.log.length > 0) {
                container.innerHTML = data.log.slice(0, 50).map(entry => `
                    <div class="rule-item">
                        <div class="rule-header">
                            <span style="font-weight: 600;">${entry.type || 'unknown'}</span>
                            <span style="font-size: 12px; color: var(--text-muted);">${entry.date || ''}</span>
                        </div>
                        <div style="font-size: 13px; color: var(--text-primary);">${entry.content || ''}</div>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: var(--text-muted);">暂无学习日志</p>';
            }
        }

        // ==================== 交易历史数据 ====================
        async function loadTradesData() {
            const data = await fetchAPI('/trades');
            if (!data) return;

            const tbody = document.querySelector('#trades-table tbody');

            if (data.trades && data.trades.length > 0) {
                tbody.innerHTML = data.trades.map(trade => `
                    <tr>
                        <td>${trade.executed_at?.split('T')[0] || '--'}</td>
                        <td>${trade.symbol || '--'}</td>
                        <td class="${trade.direction === 'buy' ? 'positive' : 'negative'}">
                            ${trade.direction === 'buy' ? '买入' : '卖出'}
                        </td>
                        <td>${trade.shares || '--'}</td>
                        <td>¥${trade.price?.toFixed(2) || '--'}</td>
                        <td>¥${trade.amount?.toFixed(2) || '--'}</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">暂无交易记录</td></tr>';
            }
        }

        // ==================== 提案审批数据 ====================
        async function loadProposalsData() {
            const data = await fetchAPI('/proposals');
            if (!data) return;

            const tbody = document.querySelector('#proposals-table tbody');

            if (data.proposals && data.proposals.length > 0) {
                tbody.innerHTML = data.proposals.map(prop => `
                    <tr>
                        <td>${prop.created_at?.split('T')[0] || '--'}</td>
                        <td>${prop.symbol || '--'}</td>
                        <td class="${prop.direction === 'buy' ? 'positive' : 'negative'}">
                            ${prop.direction === 'buy' ? '买入' : '卖出'}
                        </td>
                        <td><span class="badge ${prop.status === 'approved' ? 'success' : prop.status === 'rejected' ? 'error' : 'pending'}">${prop.status}</span></td>
                        <td>${prop.source_agent || '--'}</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">暂无提案</td></tr>';
            }
        }

        // ==================== 监控列表数据 ====================
        async function loadWatchlistData() {
            const data = await fetchAPI('/watchlist');
            if (!data) return;

            const tbody = document.querySelector('#watchlist-table tbody');

            if (data.watchlist && data.watchlist.length > 0) {
                tbody.innerHTML = data.watchlist.map(item => `
                    <tr>
                        <td>${item.symbol || '--'}</td>
                        <td>${item.name || '--'}</td>
                        <td>${item.industry || '--'}</td>
                        <td>${item.reason || '--'}</td>
                        <td>${item.added_at?.split('T')[0] || '--'}</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">暂无监控列表</td></tr>';
            }
        }

        // ==================== 风险预警数据 ====================
        async function loadRiskData() {
            const data = await fetchAPI('/overview');
            if (!data) return;

            // 获取持仓数据并计算风险
            const positions = data.positions || [];
            let highRisk = 0;
            let mediumRisk = 0;
            let lowRisk = 0;

            const tbody = document.querySelector('#risk-positions-table tbody');

            if (positions.length > 0) {
                tbody.innerHTML = positions.map(pos => {
                    // 简化风险评估逻辑
                    const profitPct = pos.profit_loss_pct || 0;
                    let riskLevel = 'low';
                    let riskColor = 'var(--success)';

                    if (profitPct < -10) {
                        riskLevel = 'high';
                        riskColor = 'var(--error)';
                        highRisk++;
                    } else if (profitPct < -5) {
                        riskLevel = 'medium';
                        riskColor = 'var(--warning)';
                        mediumRisk++;
                    } else {
                        lowRisk++;
                    }

                    const marketValue = (pos.shares * pos.current_price) || 0;

                    return `
                        <tr>
                            <td>${pos.symbol}</td>
                            <td>${pos.name || '--'}</td>
                            <td>¥${marketValue.toFixed(2)}</td>
                            <td><span class="badge" style="background: ${riskColor}; color: #FFF;">${riskLevel.toUpperCase()}</span></td>
                            <td>${riskLevel === 'high' ? '减仓' : riskLevel === 'medium' ? '观察' : '持有'}</td>
                            <td>¥${(marketValue * 0.05).toFixed(2)}</td>
                        </tr>
                    `;
                }).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">暂无持仓</td></tr>';
            }

            // 更新统计数据
            const totalRisk = highRisk + mediumRisk + lowRisk;
            document.getElementById('risk-total').textContent = totalRisk;
            document.getElementById('risk-high').textContent = highRisk;
            document.getElementById('risk-medium').textContent = mediumRisk;
            document.getElementById('risk-low').textContent = lowRisk;

            // 获取Risk Agent日志
            const logsData = await fetchAPI('/agent-logs?agent=risk');
            const logsContainer = document.getElementById('risk-logs');

            if (logsData && logsData.logs && logsData.logs.length > 0) {
                logsContainer.innerHTML = logsData.logs.slice(0, 10).map(log => `
                    <div class="rule-item">
                        <div class="rule-header">
                            <span style="font-weight: 600;">${log.event_type || 'alert'}</span>
                            <span style="font-size: 12px; color: var(--text-muted);">${log.created_at || ''}</span>
                        </div>
                        <div style="font-size: 13px; color: var(--text-primary);">
                            ${JSON.stringify(log.event_data || {})}
                        </div>
                    </div>
                `).join('');
            } else {
                logsContainer.innerHTML = '<p style="color: var(--text-muted);">暂无风险日志</p>';
            }
        }

        // ==================== 图表更新 ====================
        function updateAccuracyChart(accuracy) {
            const chartDom = document.getElementById('chart-accuracy');
            if (!chartDom) return;

            if (charts.accuracy) {
                charts.accuracy.dispose();
            }

            charts.accuracy = echarts.init(chartDom);

            const option = {
                title: {
                    text: '预测准确率',
                    textStyle: { color: '#FFFFFF' },
                    left: 'center'
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    textStyle: { color: '#A0A0A0' }
                },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 10,
                        borderColor: '#0A0A0A',
                        borderWidth: 2
                    },
                    label: {
                        show: true,
                        position: 'outside',
                        formatter: '{b}: {d}%',
                        color: '#FFFFFF'
                    },
                    labelLine: {
                        show: true
                    },
                    data: [
                        { value: accuracy.correct || 0, name: '正确', itemStyle: { color: '#00CC66' } },
                        { value: accuracy.partial || 0, name: '部分正确', itemStyle: { color: '#FFCC00' } },
                        { value: accuracy.wrong || 0, name: '错误', itemStyle: { color: '#FF3333' } }
                    ]
                }]
            };

            charts.accuracy.setOption(option);
        }

        function updateAccountChart(account) {
            const chartDom = document.getElementById('chart-account');
            if (!chartDom) return;

            if (charts.account) {
                charts.account.dispose();
            }

            charts.account = echarts.init(chartDom);

            const option = {
                title: {
                    text: '账户资产分布',
                    textStyle: { color: '#FFFFFF' },
                    left: 'center'
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: ¥{c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    textStyle: { color: '#A0A0A0' }
                },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 10,
                        borderColor: '#0A0A0A',
                        borderWidth: 2
                    },
                    label: {
                        show: true,
                        position: 'outside',
                        formatter: '{b}: {d}%',
                        color: '#FFFFFF'
                    },
                    labelLine: {
                        show: true
                    },
                    data: [
                        { value: account.cash || 0, name: '现金', itemStyle: { color: '#0066FF' } },
                        { value: account.market_value || 0, name: '市值', itemStyle: { color: '#00CC66' } }
                    ]
                }]
            };

            charts.account.setOption(option);
        }

        function updateAccuracyTrendChart(trendData, trendAnalysis) {
            const chartDom = document.getElementById('chart-accuracy-trend');
            if (!chartDom) return;

            if (charts.accuracyTrend) {
                charts.accuracyTrend.dispose();
            }

            charts.accuracyTrend = echarts.init(chartDom);

            const dates = trendData.map(d => d.date.substring(5)); // 显示 MM-DD
            const accuracies = trendData.map(d => d.accuracy);

            // 计算移动平均
            const ma7 = [];
            for (let i = 0; i < accuracies.length; i++) {
                if (i < 6) {
                    ma7.push(null);
                } else {
                    const sum = accuracies.slice(i - 6, i + 1).reduce((a, b) => a + b, 0);
                    ma7.push(+(sum / 7).toFixed(1));
                }
            }

            const option = {
                title: {
                    text: `准确率趋势 (${trendAnalysis.direction === 'improving' ? '↑ 提升' : trendAnalysis.direction === 'declining' ? '↓ 下降' : '→ 稳定'} ${Math.abs(trendAnalysis.change || 0)}%)`,
                    textStyle: { color: '#FFFFFF', fontSize: 12 },
                    left: 'center',
                    top: 10
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    formatter: function(params) {
                        let result = `<div style="font-weight: 600;">${params[0].axisValue}</div>`;
                        params.forEach(param => {
                            if (param.value !== null) {
                                result += `<div style="margin-top: 4px;">${param.marker} ${param.seriesName}: ${param.value}%</div>`;
                            }
                        });
                        return result;
                    }
                },
                legend: {
                    data: ['准确率', '7日均线'],
                    textStyle: { color: '#A0A0A0', fontSize: 10 },
                    top: 35
                },
                grid: {
                    left: 50,
                    right: 20,
                    top: 70,
                    bottom: 30
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisLabel: {
                        color: '#A0A0A0',
                        fontSize: 10,
                        rotate: 45
                    },
                    axisLine: {
                        lineStyle: { color: '#2A2A2A' }
                    }
                },
                yAxis: {
                    type: 'value',
                    min: 0,
                    max: 100,
                    axisLabel: {
                        color: '#A0A0A0',
                        fontSize: 10,
                        formatter: '{value}%'
                    },
                    axisLine: {
                        lineStyle: { color: '#2A2A2A' }
                    },
                    splitLine: {
                        lineStyle: { color: '#2A2A2A' }
                    }
                },
                series: [
                    {
                        name: '准确率',
                        type: 'line',
                        data: accuracies,
                        smooth: true,
                        lineStyle: {
                            width: 2,
                            color: '#0066FF'
                        },
                        itemStyle: {
                            color: '#0066FF'
                        },
                        areaStyle: {
                            color: {
                                type: 'linear',
                                x: 0,
                                y: 0,
                                x2: 0,
                                y2: 1,
                                colorStops: [{
                                    offset: 0, color: 'rgba(0, 102, 255, 0.3)'
                                }, {
                                    offset: 1, color: 'rgba(0, 102, 255, 0.05)'
                                }]
                            }
                        }
                    },
                    {
                        name: '7日均线',
                        type: 'line',
                        data: ma7,
                        smooth: true,
                        lineStyle: {
                            width: 1.5,
                            color: '#FFCC00',
                            type: 'dashed'
                        },
                        itemStyle: {
                            color: '#FFCC00'
                        },
                        symbol: 'none'
                    }
                ]
            };

            charts.accuracyTrend.setOption(option);
        }

        function updateCronTimelineChart(tasks) {
            const chartDom = document.getElementById('chart-cron-timeline');
            if (!chartDom) return;

            if (charts.cronTimeline) {
                charts.cronTimeline.dispose();
            }

            charts.cronTimeline = echarts.init(chartDom);

            // 转换任务时间为时间点
            const taskNames = tasks.map(t => t.name);
            const taskTimes = tasks.map(t => {
                const match = t.schedule.match(/(\d{1,2}):(\d{2})/);
                if (match) {
                    const hour = parseInt(match[1]);
                    const minute = parseInt(match[2]);
                    return hour * 3600 + minute * 60;
                }
                return 0;
            });

            const option = {
                title: {
                    text: 'Cron 任务时间线',
                    textStyle: { color: '#FFFFFF' },
                    left: 'center'
                },
                tooltip: {
                    formatter: function(params) {
                        const task = tasks[params.dataIndex];
                        return `${task.name}<br/>${task.schedule}<br/>状态: ${task.last_status || 'pending'}`;
                    }
                },
                xAxis: {
                    type: 'value',
                    axisLabel: {
                        formatter: function(value) {
                            const hours = Math.floor(value / 3600);
                            const minutes = Math.floor((value % 3600) / 60);
                            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
                        },
                        color: '#A0A0A0'
                    },
                    axisLine: { lineStyle: { color: '#2A2A2A' } },
                    axisTick: { lineStyle: { color: '#2A2A2A' } }
                },
                yAxis: {
                    type: 'category',
                    data: taskNames,
                    axisLabel: { color: '#A0A0A0' },
                    axisLine: { lineStyle: { color: '#2A2A2A' } },
                    axisTick: { lineStyle: { color: '#2A2A2A' } }
                },
                series: [{
                    type: 'scatter',
                    symbolSize: 20,
                    data: taskTimes.map((time, i) => [time, i]),
                    itemStyle: {
                        color: '#0066FF',
                        borderColor: '#FFFFFF',
                        borderWidth: 2
                    }
                }]
            };

            charts.cronTimeline.setOption(option);
        }

        // ==================== 搜索功能 ====================
        function performSearch() {
            const query = document.getElementById('dashboard-search').value.trim();
            if (!query) return;
            
            // 在持仓中搜索
            const positions = document.querySelectorAll('.position-row');
            let found = false;
            
            positions.forEach(row => {
                const symbol = row.querySelector('td:nth-child(1)').textContent;
                const name = row.querySelector('td:nth-child(2)').textContent;
                
                if (symbol.includes(query) || name.includes(query)) {
                    row.style.backgroundColor = 'rgba(0, 102, 255, 0.2)';
                    found = true;
                } else {
                    row.style.backgroundColor = '';
                }
            });
            
            if (!found) {
                alert('未找到匹配的股票');
            }
        }

        // ==================== 刷新功能 ====================
        async function refreshPositions() {
            await loadPageData('overview');
        }

        async function refreshAll() {
            await loadPageData(currentTab);
        }

        async function refreshRealtimePrices() {
            const data = await fetchAPI('/realtime-prices');
            if (data && data.prices) {
                const notifications = document.getElementById('notifications');
                const now = new Date();
                const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });

                let html = `
                    <div style="padding: 8px; background: var(--bg-card); border-radius: 6px; margin-bottom: 12px; border-left: 3px solid var(--accent);">
                        <div style="font-size: 11px; color: var(--text-muted);">最后更新: ${timeStr}</div>
                    </div>
                `;

                Object.entries(data.prices).forEach(([symbol, priceData]) => {
                    html += `
                        <div style="padding: 10px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 8px; border-left: 3px solid ${priceData.change_pct >= 0 ? 'var(--success)' : 'var(--error)'};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-weight: 600;">${symbol}</div>
                                <div style="font-size: 12px; color: ${priceData.change_pct >= 0 ? 'var(--success)' : 'var(--error)'}; font-weight: 600;">
                                    ${priceData.change_pct > 0 ? '+' : ''}${priceData.change_pct}%
                                </div>
                            </div>
                            <div style="font-size: 16px; font-weight: 700; margin-top: 4px; color: var(--text-primary);">
                                ¥${priceData.price.toFixed(2)}
                            </div>
                        </div>
                    `;
                });

                notifications.innerHTML = html || '<p style="color: var(--text-muted);">暂无持仓数据</p>';

                // 更新概览页面的价格显示
                updateOverviewPrices(data.prices);
            }
        }

        function updateOverviewPrices(prices) {
            // 更新持仓表格中的价格显示
            const rows = document.querySelectorAll('#overview-positions-table tbody tr');
              rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const symbol = cells[0].textContent.trim();
                    if (prices[symbol]) {
                        const priceData = prices[symbol];
                        // 更新当前价格（第5列，索引4）
                        if (cells[4]) {
                            cells[4].textContent = `¥${priceData.price.toFixed(2)}`;
                            // 更新盈亏（第6列，索引5）
                            if (cells[5]) {
                                cells[5].textContent = `¥${priceData.change_pct > 0 ? '+' : ''}${priceData.change_pct.toFixed(2)}`;
                                cells[5].className = priceData.change_pct >= 0 ? 'positive' : 'negative';
                            }
                            // 更新盈亏%（第7列，索引6）
                            if (cells[6]) {
                                cells[6].textContent = `${priceData.change_pct.toFixed(2)}%`;
                                cells[6].className = priceData.change_pct >= 0 ? 'positive' : 'negative';
                            }
                        }
                    }
                }
            });
        }

        // ==================== 全局搜索 ====================
        const searchInput = document.getElementById('global-search');
        let searchTimeout = null;

        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const query = e.target.value.trim();

            if (query.length < 2) {
                document.getElementById('search-results').style.display = 'none';
                return;
            }

            searchTimeout = setTimeout(() => performGlobalSearch(query), 300);
        });

        async function performGlobalSearch(query) {
            const resultsContainer = document.getElementById('search-results-list');
            const searchResultsDiv = document.getElementById('search-results');

            // 显示加载中
            resultsContainer.innerHTML = '<p style="color: var(--text-muted);"><span class="loading"></span> 搜索中...</p>';
            searchResultsDiv.style.display = 'block';

            try {
                // 并发获取多个数据源
                const [overview, rules, logs] = await Promise.all([
                    fetchAPI('/overview'),
                    fetchAPI('/rules'),
                    fetchAPI('/learning-log')
                ]);

                let results = [];

                // 搜索持仓
                if (overview && overview.positions) {
                    overview.positions.forEach(pos => {
                        if (pos.symbol.toLowerCase().includes(query.toLowerCase()) ||
                            (pos.name && pos.name.includes(query))) {
                            results.push({
                                type: '持仓',
                                title: `${pos.symbol} - ${pos.name || ''}`,
                                subtitle: `数量: ${pos.shares} | 盈亏: ${pos.profit_loss_pct?.toFixed(2) || 0}%`,
                                page: 'overview'
                            });
                        }
                    });
                }

                // 搜索规则
                if (rules && rules.rules) {
                    ['direction_rules', 'magnitude_rules', 'timing_rules', 'confidence_rules'].forEach(category => {
                        Object.entries(rules.rules[category] || {}).forEach(([ruleId, rule]) => {
                            if (rule.condition.includes(query) || rule.prediction.includes(query)) {
                                results.push({
                                    type: '规则',
                                    title: ruleId,
                                    subtitle: rule.condition,
                                    page: 'rules'
                                });
                            }
                        });
                    });
                }

                // 搜索日志
                if (logs && logs.log) {
                    logs.log.forEach(log => {
                        if (log.content && log.content.includes(query)) {
                            results.push({
                                type: '日志',
                                title: log.type || 'unknown',
                                subtitle: log.content.substring(0, 50) + '...',
                                page: 'learning'
                            });
                        }
                    });
                }

                // 显示结果
                if (results.length > 0) {
                    resultsContainer.innerHTML = results.map(r => `
                        <div style="padding: 8px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 8px; cursor: pointer;"
                             onclick="navigateToPage('${r.page}')">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-weight: 600;">${r.title}</span>
                                <span class="badge active">${r.type}</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">${r.subtitle}</div>
                        </div>
                    `).join('');
                } else {
                    resultsContainer.innerHTML = '<p style="color: var(--text-muted);">未找到相关结果</p>';
                }
            } catch (error) {
                resultsContainer.innerHTML = '<p style="color: var(--error);">搜索失败: ' + error.message + '</p>';
            }
        }

        function navigateToPage(page) {
            document.querySelector(`[data-page="${page}"]`)?.click();
        }

        // ==================== 数据导出 ====================
        function exportData(type) {
            const url = `/export/${type}`;
            window.location.href = url;
        }

        // ==================== 自动刷新 ====================
        // 每10秒刷新实时价格（交易时间内）
        let priceRefreshInterval = null;

        function startPriceAutoRefresh() {
            if (priceRefreshInterval) {
                clearInterval(priceRefreshInterval);
            }
            // 刷新间隔：交易时间10秒，非交易时间60秒
            const interval = isTradingTime() ? 10000 : 60000;
            priceRefreshInterval = setInterval(refreshRealtimePrices, interval);
            console.log(`价格自动刷新已启动，间隔: ${interval/1000}秒`);
        }

        function isTradingTime() {
            const now = new Date();
            const day = now.getDay();
            // 周末不交易
            if (day === 0 || day === 6) return false;
            const hour = now.getHours();
            const minute = now.getMinutes();
            const time = hour * 60 + minute;
            // 交易时间：9:30-11:30, 13:00-15:00
            return (time >= 9*60+30 && time <= 11*60+30) ||
                   (time >= 13*60 && time <= 15*60);
        }

        // 每30秒刷新所有数据
        setInterval(refreshAll, 30000);

        // 启动价格自动刷新
        startPriceAutoRefresh();

        // ==================== 初始化 ====================
        document.addEventListener('DOMContentLoaded', function() {
            // 导航初始化
            document.querySelectorAll('.nav-item').forEach(item => {
                item.addEventListener('click', function() {
                    const page = this.dataset.page;
                    if (!page) return;

                    // 更新导航状态
                    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
                    this.classList.add('active');

                    // 切换页面
                    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                    document.getElementById('page-' + page).classList.add('active');

                    currentTab = page;

                    // 加载页面数据
                    loadPageData(page);
                });
            });

            // 搜索功能初始化
            const searchInput = document.getElementById('dashboard-search');
            if (searchInput) {
                searchInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        performSearch();
                    }
                });
            }

            // 页面初始化
            loadPageData(currentTab);
            setInterval(updateClock, 1000);
            updateClock();
            
            // 启动价格自动刷新
            startPriceAutoRefresh();
        });
    </script>
</body>
</html>"""


# ==================== 启动服务器 ====================

def run_server():
    """启动 HTTP 服务器"""
    try:
        with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
            logger.info(f"Dashboard server started at http://127.0.0.1:{PORT}")
            logger.info(f"Press Ctrl+C to stop")
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")


if __name__ == "__main__":
    run_server()
