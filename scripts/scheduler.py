#!/usr/bin/env python3
"""
24小时调度器 v2.0
- 自动运行所有定时任务
- 支持交易日检测
- 日志记录

运行方式:
  python scheduler.py start   # 后台启动
  python scheduler.py stop    # 停止
  python scheduler.py status  # 查看状态
"""

import sys
import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "bin", "python3")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
PID_FILE = os.path.join(PROJECT_ROOT, ".scheduler.pid")
STATE_FILE = os.path.join(PROJECT_ROOT, ".scheduler.state")

# 定时任务配置
# 完整的19个交易任务 + 周期性任务

# 核心交易任务 (19个)
SCHEDULE = {
    # 1. 09:00 开盘前联网搜索
    "morning_web_search": {
        "time": "09:00",
        "script": "daily_web_search.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "联网搜索"
    },

    # 2. 09:25 涨跌停实时监控
    "intraday_limit_monitor": {
        "time": "09:25",
        "script": "intraday_monitor.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "实时市场数据"
    },

    # 3. 09:30 AI预测生成
    "morning_prediction": {
        "time": "09:30",
        "script": "ai_predictor.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "知识库+历史数据"
    },

    # 4. 09:30 自动买入
    "auto_buy": {
        "time": "09:30",
        "script": "auto_trader_v3.py",
        "args": ["--buy", "--dry-run"],  # 默认dry-run，实际执行需--execute
        "enabled": True,
        "trading_days_only": True,
        "data_source": "预测信号"
    },

    # 5. 09:35 持仓汇报早盘
    "feishu_morning_report": {
        "time": "09:35",
        "script": "feishu_notifier.py",
        "args": ["--report", "morning"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "持仓数据"
    },

    # 6. 10:00 新闻监控预测更新
    "news_monitor_check1": {
        "time": "10:00",
        "script": "news_monitor.py",
        "args": ["check"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "实时新闻"
    },

    # 7. 10:00 每日深度研究1股
    "daily_stock_research": {
        "time": "10:00",
        "script": "daily_stock_research.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "股票池+知识库"
    },

    # 8. 11:30 持仓汇报午盘收盘
    "feishu_noon_close_report": {
        "time": "11:30",
        "script": "feishu_notifier.py",
        "args": ["--report", "noon_close"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "持仓数据"
    },

    # 9. 11:30 午盘反思
    "midday_reflection": {
        "time": "11:30",
        "script": "daily_learning.py",
        "args": ["--reflect"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "交易记录"
    },

    # 10. 13:00 下午开盘前更新
    "noon_update": {
        "time": "13:00",
        "script": "ai_predictor.py",
        "args": ["--update"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "市场最新数据"
    },

    # 11. 14:00 持仓汇报午盘开盘
    "feishu_noon_open_report": {
        "time": "14:00",
        "script": "feishu_notifier.py",
        "args": ["--report", "noon_open"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "持仓数据"
    },

    # 12. 14:00 新闻监控
    "news_monitor_check2": {
        "time": "14:00",
        "script": "news_monitor.py",
        "args": ["check"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "实时新闻"
    },

    # 13. 15:00 选股层动态标准选股
    "daily_scan": {
        "time": "15:00",
        "script": "daily_scan.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "全市场扫描"
    },

    # 14. 15:05 持仓汇报收盘汇总
    "feishu_close_report": {
        "time": "15:05",
        "script": "feishu_notifier.py",
        "args": ["--report", "close"],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "持仓数据"
    },

    # 15. 15:10 自动卖出
    "auto_sell": {
        "time": "15:10",
        "script": "auto_trader_v3.py",
        "args": ["--sell", "--dry-run"],  # 默认dry-run，实际执行需--execute
        "enabled": True,
        "trading_days_only": True,
        "data_source": "持仓数据"
    },

    # 16. 每日预测复盘 (15:30)
    "afternoon_review": {
        "time": "15:30",
        "script": "daily_review_closed_loop.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "预测结果+实际行情"
    },

    # 17. 16:00 每日绩效汇报
    "daily_performance_report": {
        "time": "16:00",
        "script": "daily_performance_report.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "交易记录"
    },

    # 18. 16:00 规则验证
    "rule_validation": {
        "time": "16:00",
        "script": "rule_validation.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "规则池+市场数据"
    },

    # 19. 20:00 每日炒股书籍学习
    "book_learning": {
        "time": "20:00",
        "script": "daily_book_learning.py",
        "args": [],
        "enabled": True,
        "trading_days_only": False,
        "data_source": "书籍库"
    },

    # ========== 以下为周期性补充任务 ==========

    # 规则晋升检查 (16:00)
    "rule_promotion": {
        "time": "16:00",
        "script": "rule_promotion.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "验证池+规则池"
    },

    # 每周总结 (周日 20:00)
    "weekly_summary": {
        "time": "20:00",
        "day": 6,  # 周日
        "script": "weekly_summary.py",
        "args": [],
        "enabled": True,
        "trading_days_only": False,
        "data_source": "周度汇总"
    },

    # 知识库每日收集 (06:00)
    "knowledge_collect_daily": {
        "time": "06:00",
        "script": "knowledge_collector.py",
        "args": ["--mode", "daily", "--save-stats"],
        "enabled": True,
        "trading_days_only": False,
        "data_source": "研报/新闻/KOL"
    },

    # 知识库每周收集 (周日 07:00)
    "knowledge_collect_weekly": {
        "time": "07:00",
        "day": 6,  # 周日
        "script": "knowledge_collector.py",
        "args": ["--mode", "weekly", "--save-stats"],
        "enabled": True,
        "trading_days_only": False,
        "data_source": "年报/基金经理"
    },

    # 教训应用 (每周一 10:00)
    "lesson_apply": {
        "time": "10:00",
        "day": 0,  # 周一
        "script": "lesson_applier.py",
        "args": [],
        "enabled": True,
        "trading_days_only": False,
        "data_source": "学习记忆"
    },

    # 闭环健康度检查 (每天 17:00)
    "closed_loop_health": {
        "time": "17:00",
        "script": "closed_loop_health_check.py",
        "args": [],
        "enabled": True,
        "trading_days_only": True,
        "data_source": "系统日志"
    }
}


class Scheduler:
    """24小时调度器"""
    
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.running = False
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            "started_at": None,
            "last_runs": {},
            "total_runs": 0
        }
    
    def _save_state(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _is_trading_day(self) -> bool:
        """检查是否是交易日（简化版：周一到周五）"""
        return datetime.now().weekday() < 5
    
    def _run_script(self, task_name: str, script: str, args: List[str]) -> bool:
        """运行脚本"""
        script_path = os.path.join(PROJECT_ROOT, "scripts", script)
        
        if not os.path.exists(script_path):
            print(f"  ⚠️ 脚本不存在: {script}")
            return False
        
        cmd = [VENV_PYTHON, script_path] + args
        log_file = os.path.join(LOG_DIR, f"{task_name}_{datetime.now().strftime('%Y%m%d')}.log")
        
        print(f"  🚀 运行: {script} {' '.join(args)}")
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
                f.write(f"命令: {' '.join(cmd)}\n")
                f.write(f"{'='*50}\n\n")
                
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=PROJECT_ROOT,
                    timeout=300  # 5分钟超时
                )
            
            if result.returncode == 0:
                print(f"  ✅ 完成: {script}")
                return True
            else:
                print(f"  ❌ 失败: {script} (退出码 {result.returncode})")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"  ⏱️ 超时: {script}")
            return False
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            return False
    
    def _should_run(self, task_name: str, task: Dict) -> bool:
        """检查任务是否应该运行"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # 检查是否启用
        if not task.get("enabled", True):
            return False
        
        # 检查交易日
        if task.get("trading_days_only", False) and not self._is_trading_day():
            return False
        
        # 检查星期几
        if "day" in task and now.weekday() != task["day"]:
            return False
        
        # 检查时间
        if "times" in task:
            # 多次运行的任务
            for t in task["times"]:
                if current_time == t:
                    # 检查今天是否已经运行过这个时间点
                    last_run_key = f"{task_name}_{t}"
                    last_run = self.state["last_runs"].get(last_run_key, "")
                    if last_run != now.strftime("%Y-%m-%d"):
                        return True
            return False
        else:
            # 单次运行的任务
            if current_time != task["time"]:
                return False
            
            # 检查今天是否已经运行过
            last_run = self.state["last_runs"].get(task_name, "")
            if last_run == now.strftime("%Y-%m-%d"):
                return False
            
            return True
    
    def _mark_run(self, task_name: str, time_key: str = None):
        """标记任务已运行"""
        key = f"{task_name}_{time_key}" if time_key else task_name
        self.state["last_runs"][key] = datetime.now().strftime("%Y-%m-%d")
        self.state["total_runs"] += 1
        self._save_state()
    
    def run_once(self):
        """运行一次检查"""
        print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 检查任务...")
        
        for task_name, task in SCHEDULE.items():
            if self._should_run(task_name, task):
                print(f"\n📋 执行任务: {task_name}")
                
                success = self._run_script(
                    task_name,
                    task["script"],
                    task.get("args", [])
                )
                
                # 标记已运行
                if "times" in task:
                    current_time = datetime.now().strftime("%H:%M")
                    self._mark_run(task_name, current_time)
                else:
                    self._mark_run(task_name)
    
    def start(self):
        """启动调度器"""
        print("=" * 60)
        print("🤖 股票团队 24小时调度器 v2.0")
        print("=" * 60)
        print(f"启动时间: {datetime.now().isoformat()}")
        print()
        
        # 检查是否已在运行
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = f.read().strip()
            print(f"⚠️ 调度器可能已在运行 (PID: {pid})")
            print("如需重启，请先运行: python scheduler.py stop")
            return
        
        # 写入 PID
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        
        self.state["started_at"] = datetime.now().isoformat()
        self._save_state()
        
        print("📋 已配置任务:")
        for name, task in SCHEDULE.items():
            status = "✅" if task.get("enabled", True) else "❌"
            times = task.get("times", [task.get("time", "?")])
            trading = "📅 交易日" if task.get("trading_days_only") else "📆 每天"
            print(f"  {status} {name}: {times} ({trading})")
        
        print()
        print("🚀 调度器已启动，每分钟检查一次...")
        print("   日志目录:", LOG_DIR)
        print()
        
        self.running = True
        
        try:
            while self.running:
                self.run_once()
                time.sleep(60)  # 每分钟检查一次
        except KeyboardInterrupt:
            print("\n\n⏹️ 收到停止信号...")
        finally:
            self.stop()
    
    def stop(self):
        """停止调度器"""
        print("🛑 停止调度器...")
        self.running = False
        
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        
        print("✅ 调度器已停止")
    
    def status(self):
        """查看状态"""
        print("=" * 60)
        print("📊 调度器状态")
        print("=" * 60)
        
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = f.read().strip()
            print(f"状态: 🟢 运行中 (PID: {pid})")
        else:
            print("状态: 🔴 未运行")
        
        print()
        print("📋 任务配置:")
        for name, task in SCHEDULE.items():
            status = "✅" if task.get("enabled", True) else "❌"
            times = task.get("times", [task.get("time", "?")])
            last_run = self.state["last_runs"].get(name, "从未运行")
            print(f"  {status} {name}:")
            print(f"     时间: {times}")
            print(f"     上次: {last_run}")
        
        print()
        print(f"总运行次数: {self.state.get('total_runs', 0)}")
        print(f"启动时间: {self.state.get('started_at', '未启动')}")
        print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("用法: python scheduler.py [start|stop|status|run_once]")
        sys.exit(1)
    
    command = sys.argv[1]
    scheduler = Scheduler()
    
    if command == "start":
        scheduler.start()
    elif command == "stop":
        scheduler.stop()
    elif command == "status":
        scheduler.status()
    elif command == "run_once":
        scheduler.run_once()
    else:
        print(f"未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
