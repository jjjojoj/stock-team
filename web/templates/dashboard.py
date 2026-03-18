#!/usr/bin/env python3
"""
AI 股票团队监控面板 v1.0.0
"""

import sqlite3
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional
import threading

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "database" / "stock_team.db"
LEARNING_DIR = PROJECT_ROOT / "learning"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_realtime_price(code: str) -> Optional[Dict]:
    try:
        stock_code = code.replace('.', '')
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
    except:
        pass
    return None

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_html()
        elif self.path == '/health':
            self.send_json({"status": "ok", "version": "1.0.0"})
        elif self.path == '/api/agents':
            self.send_json(self.get_agents())
        elif self.path == '/api/cron':
            self.send_json(self.get_cron())
        elif self.path == '/api/rules':
            self.send_json(self.get_rules())
        elif self.path == '/api/validation-pool':
            self.send_json(self.get_validation_pool())
        elif self.path == '/api/knowledge-base':
            self.send_json(self.get_knowledge_base())
        elif self.path == '/api/account':
            self.send_json(self.get_account())
        elif self.path == '/api/accuracy':
            self.send_json(self.get_accuracy())
        elif self.path == '/api/event-analysis':
            self.send_json(self.get_event_analysis())
        elif self.path == '/api/event-analysis/news':
            self.send_json(self.get_event_news())
        elif self.path.startswith('/api/event-analysis/range'):
            self.send_json(self.get_range_analysis())
        elif self.path == '/api/event-analysis/history':
            self.send_json(self.get_event_history())
        else:
            self.send_error(404)

    def send_html(self):
        html = self.get_html_template()
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def get_agents(self):
        return {
            'agents': [
                {'id': 'cio', 'name': 'CIO', 'role': '首席投资官',
                 'responsibilities': ['最终投资决策审批', '仓位上限控制', '风险敞口管理'],
                 'kpi': {'组合月收益率': '≥ 5%', '最大回撤': '≤ 15%', '夏普比率': '≥ 1.5'}},
                {'id': 'quant', 'name': 'Quant', 'role': '量化分析师',
                 'responsibilities': ['选股模型维护', '因子有效性监控', '策略回测优化'],
                 'kpi': {'选股胜率': '≥ 60%', '推荐股票月均收益': '≥ 8%', '因子 IC 值': '≥ 0.05'}},
                {'id': 'trader', 'name': 'Trader', 'role': '交易员',
                 'responsibilities': ['执行买卖指令', '择时优化', '滑点控制'],
                 'kpi': {'成交率': '≥ 95%', '平均滑点': '≤ 0.5%', '买入后5日胜率': '≥ 55%'}},
                {'id': 'risk', 'name': 'Risk', 'role': '风控官',
                 'responsibilities': ['风险监控与预警', '止损执行', '合规审查'],
                 'kpi': {'风险预警准确率': '≥ 80%', '止损执行率': '100%'}},
                {'id': 'researcher', 'name': 'Researcher', 'role': '研究员',
                 'responsibilities': ['行业研究', '公司调研', '信息收集'],
                 'kpi': {'研究报告准确率': '≥ 70%'}},
                {'id': 'learning', 'name': 'Learning', 'role': '学习系统',
                 'responsibilities': ['书籍学习', '实战总结', '规则提取'],
                 'kpi': {'规则验证通过率': '≥ 50%'}}
            ]
        }

    def get_cron(self):
        state_file = PROJECT_ROOT / ".scheduler.state"
        state = load_json(state_file)
        
        tasks = [
            {'id': 'morning_prediction', 'name': '早盘预测', 'schedule': '09:00',
             'script': 'ai_predictor.py', 'enabled': True, 'trading_days_only': True,
             'last_run': state.get('last_runs', {}).get('morning_prediction'),
             'description': '分析持仓和自选股，生成今日预测'},
            {'id': 'noon_update', 'name': '午盘更新', 'schedule': '13:00',
             'script': 'ai_predictor.py --update', 'enabled': True, 'trading_days_only': True,
             'last_run': state.get('last_runs', {}).get('noon_update'),
             'description': '根据午盘走势调整预测'},
            {'id': 'afternoon_review', 'name': '盘后复盘', 'schedule': '15:30',
             'script': 'daily_review_closed_loop.py', 'enabled': True, 'trading_days_only': True,
             'last_run': state.get('last_runs', {}).get('afternoon_review'),
             'description': '验证今日预测，记录对错，学习提升'},
            {'id': 'rule_promotion', 'name': '规则晋升', 'schedule': '16:00',
             'script': 'rule_promotion.py', 'enabled': True, 'trading_days_only': True,
             'last_run': state.get('last_runs', {}).get('rule_promotion'),
             'description': '检查验证池，晋升成熟规则'},
            {'id': 'book_learning', 'name': '深度学习', 'schedule': '20:00',
             'script': 'daily_book_learning.py', 'enabled': True, 'trading_days_only': False,
             'last_run': state.get('last_runs', {}).get('book_learning'),
             'description': '从投资书籍中提取可验证规则'},
            {'id': 'news_monitor', 'name': '新闻监控', 'schedule': '09:30, 11:00, 14:00',
             'script': 'news_monitor.py check', 'enabled': False, 'trading_days_only': True,
             'last_run': state.get('last_runs', {}).get('news_monitor_09:30'),
             'description': '监控重要新闻，触发预测更新（已禁用）'},
            {'id': 'weekly_summary', 'name': '每周总结', 'schedule': '周日 20:00',
             'script': 'weekly_summary.py', 'enabled': True, 'trading_days_only': False,
             'last_run': state.get('last_runs', {}).get('weekly_summary'),
             'description': '总结本周表现，识别问题，提出改进'}
        ]
        
        return {'tasks': tasks, 'scheduler_started_at': state.get('started_at'),
                'total_runs': state.get('total_runs', 0)}

    def get_rules(self):
        rules_file = LEARNING_DIR / "prediction_rules.json"
        rules = load_json(rules_file)
        
        result = {'direction': [], 'magnitude': [], 'timing': [], 'confidence': []}
        
        for category in ['direction_rules', 'magnitude_rules', 'timing_rules', 'confidence_rules']:
            cat_key = category.replace('_rules', '')
            for rule_id, rule in rules.get(category, {}).items():
                result[cat_key].append({
                    'id': rule_id,
                    'condition': rule.get('condition'),
                    'prediction': rule.get('prediction'),
                    'confidence_boost': rule.get('confidence_boost'),
                    'samples': rule.get('samples', 0),
                    'success_rate': rule.get('success_rate', 0.0),
                    'source': rule.get('source', '未知'),
                    'created_at': rule.get('created_at')
                })
        
        return result

    def get_validation_pool(self):
        pool_file = LEARNING_DIR / "rule_validation_pool.json"
        pool = load_json(pool_file)
        
        rules = []
        pool_rules = pool if isinstance(pool, dict) and 'rules' not in pool else pool.get('rules', {})
        
        for rule_id, rule in pool_rules.items():
            rules.append({
                'id': rule_id,
                'rule': rule.get('rule'),
                'testable_form': rule.get('testable_form'),
                'category': rule.get('category'),
                'source': rule.get('source', rule.get('source_book', '未知')),
                'status': rule.get('status'),
                'confidence': rule.get('confidence', 0.5),
                'live_samples': rule.get('live_test', {}).get('samples', 0),
                'live_success_rate': rule.get('live_test', {}).get('success_rate', 0.0),
                'created_at': rule.get('created_at'),
                'auto_generated': rule.get('auto_generated', False),
                'experience_based': rule.get('experience_based', False)
            })
        
        sources = {}
        for rule in rules:
            source = rule['source']
            sources[source] = sources.get(source, 0) + 1
        
        return {
            'rules': rules,
            'total': len(rules),
            'by_status': {
                'validating': len([r for r in rules if r['status'] == 'validating']),
                'verified': len([r for r in rules if r['status'] == 'verified']),
                'rejected': len([r for r in rules if r['status'] == 'rejected'])
            },
            'by_source': sources
        }

    def get_knowledge_base(self):
        kb_file = LEARNING_DIR / "knowledge_base.json"
        book_file = LEARNING_DIR / "book_knowledge.json"
        
        kb = load_json(kb_file)
        books = load_json(book_file)
        
        items = []
        for item in kb.get('items', []):
            items.append({
                'id': item['id'],
                'type': item['type'],
                'source': item['source'],
                'title': item['title'],
                'content': item.get('content', '')[:200] + '...' if len(item.get('content', '')) > 200 else item.get('content', ''),
                'rules_generated': item.get('rules_generated', 0),
                'collected_at': item.get('collected_at')
            })
        
        books_list = []
        for book_id, book in books.items():
            books_list.append({
                'id': book_id,
                'title': book['title'],
                'author': book['author'],
                'learned_date': book['learned_date'],
                'key_points_count': len(book.get('key_points', []))
            })
        
        return {'items': items, 'books': books_list, 'stats': kb.get('stats', {})}

    def get_account(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取最新的账户信息来确定现金余额
        cursor.execute("SELECT cash, total_profit FROM account ORDER BY date DESC LIMIT 1")
        account_row = cursor.fetchone()
        
        cursor.execute("SELECT * FROM positions WHERE status = 'holding'")
        positions = cursor.fetchall()
        
        total_value = 0
        total_cost = 0
        position_list = []
        
        for pos in positions:
            realtime = get_realtime_price(pos['symbol'])
            current_price = realtime['price'] if realtime else pos['current_price']
            value = pos['shares'] * current_price
            cost = pos['shares'] * pos['cost_price']
            
            total_value += value
            total_cost += cost
            
            position_list.append({
                'code': pos['symbol'],
                'name': pos['name'],
                'shares': pos['shares'],
                'cost_price': pos['cost_price'],
                'current_price': current_price,
                'profit': value - cost,
                'profit_pct': (value - cost) / cost * 100 if cost > 0 else 0,
                'change_pct': realtime['change_pct'] if realtime else 0
            })
        
        conn.close()
        
        # 计算真实现金：总资产减去持仓市值
        # 从数据库获取的cash实际上是总资产，所以我们需要减去当前持仓市值来得到真实现金
        if account_row:
            total_asset_from_db = account_row['cash']  # 数据库中的cash字段实际是总资产
            cash = max(0, total_asset_from_db - total_value)
            total_asset = total_asset_from_db
            total_profit = account_row['total_profit']
            total_profit_pct = (total_profit / (total_asset - total_profit) * 100) if (total_asset - total_profit) > 0 else 0
        else:
            cash = 0
            total_asset = total_value
            total_profit = 0
            total_profit_pct = 0
        
        return {
            'total_asset': total_asset,
            'cash': cash,
            'market_value': total_value,
            'total_profit': total_profit,
            'total_profit_pct': total_profit_pct,
            'position_count': len(position_list),
            'positions': position_list
        }

    def get_accuracy(self):
        accuracy_file = LEARNING_DIR / "accuracy_stats.json"
        accuracy = load_json(accuracy_file)

        total = accuracy.get('total_predictions', 0)
        correct = accuracy.get('correct', 0)

        return {
            'total': total,
            'correct': correct,
            'partial': accuracy.get('partial', 0),
            'wrong': accuracy.get('wrong', 0),
            'accuracy_rate': correct / total * 100 if total > 0 else 0,
            'by_rule': accuracy.get('by_rule', {}),
            'by_direction': accuracy.get('by_direction', {})
        }

    def get_event_analysis(self):
        """获取事件分析概览"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取近期重大事件
        try:
            cursor.execute("""
                SELECT eka.*, nl.title, nl.sentiment, nl.event_types, nl.impact_score
                FROM event_kline_associations eka
                JOIN news_labels nl ON eka.news_id = nl.news_id
                WHERE eka.kline_start_date >= date('now', '-7 days')
                ORDER BY eka.kline_start_date DESC
                LIMIT 10
            """)
            recent_events = []
            for row in cursor.fetchall():
                event_dict = dict(row)
                # 解析 event_types JSON 字符串
                try:
                    if event_dict.get('event_types'):
                        event_dict['event_types'] = json.loads(event_dict['event_types'])
                except (json.JSONDecodeError, TypeError):
                    event_dict['event_types'] = []
                recent_events.append(event_dict)
        except sqlite3.OperationalError:
            recent_events = []

        # 统计情绪分布
        try:
            cursor.execute("""
                SELECT sentiment, COUNT(*) as count
                FROM news_labels
                WHERE news_time >= date('now', '-30 days')
                GROUP BY sentiment
            """)
            sentiment_dist = {row['sentiment']: row['count'] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            sentiment_dist = {'positive': 0, 'negative': 0, 'neutral': 0}

        # 事件影响排行
        try:
            cursor.execute("""
                SELECT stock_code, stock_name,
                       AVG(kline_change_pct) as avg_change,
                       COUNT(*) as event_count
                FROM event_kline_associations
                WHERE kline_start_date >= date('now', '-30 days')
                GROUP BY stock_code
                ORDER BY avg_change DESC
                LIMIT 10
            """)
            impact_ranking = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            impact_ranking = []

        conn.close()

        return {
            'recent_events': recent_events,
            'sentiment_distribution': sentiment_dist,
            'impact_ranking': impact_ranking
        }

    def get_event_news(self):
        """获取新闻标签列表"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM news_labels
                ORDER BY news_time DESC
                LIMIT 50
            """)
            news_list = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            news_list = []

        conn.close()

        return {'news': news_list}

    def get_range_analysis(self):
        """获取区间分析"""
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        stock_code = params.get('stock_code', [''])[0]
        start_date = params.get('start_date', [''])[0]
        end_date = params.get('end_date', [''])[0]

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM range_analysis
                WHERE (? = '' OR stock_code = ?)
                  AND (? = '' OR start_date >= ?)
                  AND (? = '' OR end_date <= ?)
                ORDER BY created_at DESC
                LIMIT 20
            """, (stock_code, stock_code, start_date, start_date, end_date, end_date))
            analysis_list = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            print(f"查询 range_analysis 表错误: {e}")
            analysis_list = []

        conn.close()

        return {'analysis': analysis_list}

    def get_event_history(self):
        """获取事件影响历史"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM event_impact_history
                ORDER BY verified_at DESC
                LIMIT 50
            """)
            history_list = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            history_list = []

        conn.close()

        return {'history': history_list}

    def get_html_template(self):
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 股票团队监控面板 v1.0.0</title>
    <script src="https://cdn.jsdelivr.net/npm/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * { -webkit-font-smoothing: antialiased; }
        body { background: #000; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0A0A0A; }
        ::-webkit-scrollbar-thumb { background: #1A1A1A; border-radius: 3px; }
        .card { background: #0A0A0A; border: 1px solid #1A1A1A; border-radius: 12px; }
        .text-green { color: #00CC66; }
        .text-red { color: #FF3333; }
        .text-yellow { color: #FFCC00; }
        .text-blue { color: #0066FF; }
        .tag { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body>
    <div id="app" class="min-h-screen">
        <nav class="fixed top-0 left-0 right-0 bg-black/80 backdrop-blur-xl border-b border-[#1A1A1A] z-50">
            <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center font-bold text-lg">AI</div>
                    <div>
                        <h1 class="text-lg font-semibold">AI 股票团队</h1>
                        <p class="text-xs text-gray-500">监控面板 v1.0.0</p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full" style="background: rgba(0,204,102,0.1)">
                        <div class="w-2 h-2 rounded-full pulse" style="background: #00CC66"></div>
                        <span class="text-sm" style="color: #00CC66">运行中</span>
                    </div>
                    <div class="text-sm text-gray-500">{{now}}</div>
                </div>
            </div>
        </nav>

        <main class="pt-20 px-6 pb-8 max-w-7xl mx-auto">
            <div class="flex gap-2 mb-6 overflow-x-auto pb-2">
                <button v-for="tab in tabs" :key="tab.id"
                    @click="currentTab = tab.id"
                    :style="currentTab === tab.id ? 'background: rgba(0,102,255,0.2); color: #0066FF; border-color: #0066FF' : 'background: #0A0A0A; color: #666'"
                    class="px-4 py-2 rounded-lg border border-transparent transition-colors whitespace-nowrap text-sm">
                    {{tab.name}}
                </button>
            </div>

            <!-- Agents -->
            <div v-if="currentTab === 'agents'" class="space-y-4">
                <div v-for="agent in agents" :key="agent.id" class="card p-6">
                    <div class="flex items-start justify-between mb-4">
                        <div>
                            <h3 class="text-xl font-bold">{{agent.name}}</h3>
                            <p class="text-gray-400">{{agent.role}}</p>
                        </div>
                        <span class="tag" style="background: rgba(0,102,255,0.2); color: #0066FF">{{agent.id.toUpperCase()}}</span>
                    </div>
                    <div class="grid md:grid-cols-2 gap-4">
                        <div>
                            <h4 class="text-sm text-gray-500 uppercase tracking-wider mb-2">职责</h4>
                            <ul class="space-y-1">
                                <li v-for="resp in agent.responsibilities" :key="resp" class="text-sm flex items-center gap-2">
                                    <span class="w-1 h-1 rounded-full" style="background: #0066FF"></span>
                                    {{resp}}
                                </li>
                            </ul>
                        </div>
                        <div>
                            <h4 class="text-sm text-gray-500 uppercase tracking-wider mb-2">KPI</h4>
                            <ul class="space-y-1">
                                <li v-for="(value, key) in agent.kpi" :key="key" class="text-sm flex items-center justify-between">
                                    <span class="text-gray-400">{{key}}</span>
                                    <span style="color: #0066FF">{{value}}</span>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Cron -->
            <div v-if="currentTab === 'cron'" class="space-y-4">
                <div class="card p-6 mb-6">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-lg font-bold">调度器状态</h3>
                        <span class="text-sm text-gray-400">总运行: {{cronStats.total_runs}} 次</span>
                    </div>
                    <p class="text-sm text-gray-400">启动时间: {{cronStats.scheduler_started_at || '未启动'}}</p>
                </div>
                
                <div v-for="task in cronTasks" :key="task.id" class="card p-6">
                    <div class="flex items-start justify-between mb-3">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <h3 class="text-lg font-bold">{{task.name}}</h3>
                                <span v-if="task.enabled" class="tag" style="background: rgba(0,204,102,0.2); color: #00CC66">启用</span>
                                <span v-else class="tag" style="background: rgba(255,51,51,0.2); color: #FF3333">禁用</span>
                            </div>
                            <p class="text-sm text-gray-400 mb-2">{{task.description}}</p>
                            <div class="flex items-center gap-4 text-xs text-gray-500">
                                <span>⏰ {{task.schedule}}</span>
                                <span>📜 {{task.script}}</span>
                            </div>
                        </div>
                        <div class="text-right">
                            <p class="text-sm text-gray-400">上次执行</p>
                            <p class="text-sm font-medium" :style="task.last_run ? 'color: #00CC66' : 'color: #666'">
                                {{task.last_run || '从未'}}
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Rules -->
            <div v-if="currentTab === 'rules'" class="space-y-6">
                <div v-for="(rules, category) in rulesData" :key="category" class="card p-6">
                    <h3 class="text-lg font-bold mb-4">
                        <span style="color: #0066FF">{{getCategoryIcon(category)}}</span>
                        {{getCategoryName(category)}}
                        <span class="text-sm text-gray-400">({{rules.length}} 条)</span>
                    </h3>
                    <div class="space-y-3">
                        <div v-for="rule in rules" :key="rule.id" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <div class="flex items-start justify-between mb-2">
                                <div class="flex-1">
                                    <p class="text-sm font-medium mb-1">{{rule.condition}}</p>
                                    <p class="text-xs text-gray-400">{{rule.prediction}}</p>
                                </div>
                                <div class="text-right">
                                    <span :style="rule.confidence_boost > 0 ? 'color: #00CC66' : 'color: #FF3333'" class="text-sm font-bold">
                                        {{rule.confidence_boost > 0 ? '+' : ''}}{{rule.confidence_boost}}%
                                    </span>
                                </div>
                            </div>
                            <div class="flex items-center gap-4 text-xs text-gray-500">
                                <span>来源: {{rule.source}}</span>
                                <span>样本: {{rule.samples}}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Validation Pool -->
            <div v-if="currentTab === 'validation'" class="space-y-6">
                <div class="card p-6 mb-6">
                    <div class="grid grid-cols-3 gap-4 text-center">
                        <div>
                            <p class="text-3xl font-bold" style="color: #0066FF">{{validationPool.total}}</p>
                            <p class="text-sm text-gray-400">总规则数</p>
                        </div>
                        <div>
                            <p class="text-3xl font-bold" style="color: #FFCC00">{{validationPool.by_status.validating || 0}}</p>
                            <p class="text-sm text-gray-400">验证中</p>
                        </div>
                        <div>
                            <p class="text-3xl font-bold" style="color: #00CC66">{{validationPool.by_status.verified || 0}}</p>
                            <p class="text-sm text-gray-400">已验证</p>
                        </div>
                    </div>
                </div>

                <div class="card p-6 mb-6">
                    <h3 class="text-lg font-bold mb-4">来源统计</h3>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div v-for="(count, source) in validationPool.by_source" :key="source" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <p class="text-sm text-gray-400 mb-1">{{source}}</p>
                            <p class="text-2xl font-bold">{{count}}</p>
                        </div>
                    </div>
                </div>

                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">规则列表</h3>
                    <div class="space-y-3 max-h-96 overflow-y-auto">
                        <div v-for="rule in validationPool.rules" :key="rule.id" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <div class="flex items-start justify-between mb-2">
                                <div class="flex-1">
                                    <div class="flex items-center gap-2 mb-1">
                                        <p class="text-sm font-medium">{{rule.rule}}</p>
                                        <span v-if="rule.auto_generated" class="tag" style="background: rgba(0,102,255,0.2); color: #0066FF">自动</span>
                                        <span v-if="rule.experience_based" class="tag" style="background: rgba(255,204,0,0.2); color: #FFCC00">实战</span>
                                    </div>
                                    <p class="text-xs text-gray-400">{{rule.testable_form}}</p>
                                </div>
                                <span class="tag" :style="{
                                    'background': rule.status === 'validating' ? 'rgba(255,204,0,0.2)' : rule.status === 'verified' ? 'rgba(0,204,102,0.2)' : 'rgba(255,51,51,0.2)',
                                    'color': rule.status === 'validating' ? '#FFCC00' : rule.status === 'verified' ? '#00CC66' : '#FF3333'
                                }">{{rule.status}}</span>
                            </div>
                            <div class="flex items-center gap-4 text-xs text-gray-500">
                                <span>📚 {{rule.source}}</span>
                                <span>分类: {{rule.category}}</span>
                                <span>置信度: {{(rule.confidence * 100).toFixed(0)}}%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Knowledge Base -->
            <div v-if="currentTab === 'knowledge'" class="space-y-6">
                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">📚 书籍学习</h3>
                    <div class="grid md:grid-cols-2 gap-4">
                        <div v-for="book in knowledgeBase.books" :key="book.id" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <h4 class="font-medium mb-1">{{book.title}}</h4>
                            <p class="text-sm text-gray-400 mb-2">{{book.author}}</p>
                            <div class="flex items-center justify-between text-xs">
                                <span class="text-gray-500">学习日期: {{book.learned_date}}</span>
                                <span style="color: #0066FF">{{book.key_points_count}} 个知识点</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">💡 知识条目</h3>
                    <div class="space-y-3">
                        <div v-for="item in knowledgeBase.items" :key="item.id" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <div class="flex items-start justify-between mb-2">
                                <div>
                                    <div class="flex items-center gap-2 mb-1">
                                        <span class="tag" style="background: rgba(0,102,255,0.2); color: #0066FF">{{item.type}}</span>
                                        <h4 class="font-medium">{{item.title}}</h4>
                                    </div>
                                    <p class="text-xs text-gray-400">{{item.content}}</p>
                                </div>
                                <span class="text-sm" style="color: #0066FF">{{item.rules_generated}} 规则</span>
                            </div>
                            <p class="text-xs text-gray-500">来源: {{item.source}} · {{item.collected_at}}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Event Analysis -->
            <div v-if="currentTab === 'event'" class="space-y-6">
                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">📰 近期重大事件</h3>
                    <div v-if="eventAnalysis.recent_events.length === 0" class="text-sm text-gray-500">
                        暂无事件数据
                    </div>
                    <div v-else class="space-y-3">
                        <div v-for="event in eventAnalysis.recent_events" :key="event.id" class="p-4 rounded-lg" style="background: #0F0F0F">
                            <div class="flex items-start justify-between mb-2">
                                <div class="flex-1">
                                    <div class="flex items-center gap-2 mb-1">
                                        <span class="tag" :style="event.sentiment === 'positive' ? 'background: rgba(0,204,102,0.2); color: #00CC66' : event.sentiment === 'negative' ? 'background: rgba(255,51,51,0.2); color: #FF3333' : 'background: rgba(255,204,0,0.2); color: #FFCC00'">{{event.sentiment}}</span>
                                        <h4 class="font-medium">{{event.title}}</h4>
                                    </div>
                                    <p class="text-xs text-gray-400 mb-1">
                                        {{event.stock_name}} ({{event.stock_code}}) | 日期: {{event.kline_start_date}}
                                    </p>
                                    <p class="text-xs text-gray-500">
                                        事件类型: {{ Array.isArray(event.event_types) ? event.event_types.join(', ') : event.event_types }} · 
                                        1日涨跌: {{ event.day1_change ? event.day1_change.toFixed(2) : 'N/A' }}% | 影响分数: {{ event.impact_score ? event.impact_score.toFixed(0) : 'N/A' }}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid md:grid-cols-2 gap-6">
                    <div class="card p-6">
                        <h3 class="text-lg font-bold mb-4">📊 事件情绪分布</h3>
                        <div v-if="Object.keys(eventAnalysis.sentiment_distribution).length === 0" class="text-sm text-gray-500">
                            暂无情绪数据
                        </div>
                        <div v-else class="space-y-4">
                            <div v-for="(count, sentiment) in eventAnalysis.sentiment_distribution" :key="sentiment">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-sm" :style="sentiment === 'positive' ? 'color: #00CC66' : sentiment === 'negative' ? 'color: #FF3333' : 'color: #FFCC00'">{{sentiment}}</span>
                                    <span class="text-sm font-bold">{{count}}</span>
                                </div>
                                <div class="h-2 rounded-full" style="background: #1A1A1A">
                                    <div class="h-2 rounded-full" :style="{
                                        width: (count / Math.max(...Object.values(eventAnalysis.sentiment_distribution)) * 100) + '%',
                                        background: sentiment === 'positive' ? '#00CC66' : sentiment === 'negative' ? '#FF3333' : '#FFCC00'
                                    }"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card p-6">
                        <h3 class="text-lg font-bold mb-4">📈 事件影响排行</h3>
                        <div v-if="eventAnalysis.impact_ranking.length === 0" class="text-sm text-gray-500">
                            暂无排行数据
                        </div>
                        <div v-else class="space-y-3">
                            <div v-for="(stock, index) in eventAnalysis.impact_ranking" :key="stock.stock_code" class="p-3 rounded-lg" style="background: #0F0F0F">
                                <div class="flex items-center justify-between">
                                    <div>
                                        <span class="text-xs text-gray-500">#{{index + 1}}</span>
                                        <span class="ml-2 font-medium">{{stock.stock_name}}</span>
                                        <span class="text-xs text-gray-400 ml-1">({{stock.stock_code}})</span>
                                    </div>
                                    <div class="text-right">
                                        <span class="font-bold" :style="stock.avg_change >= 0 ? 'color: #00CC66' : 'color: #FF3333'">{{stock.avg_change >= 0 ? '+' : ''}}{{stock.avg_change.toFixed(2)}}%</span>
                                        <div class="text-xs text-gray-500">{{stock.event_count}} 个事件</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Overview -->
            <div v-if="currentTab === 'overview'" class="space-y-6">
                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">💰 账户概览</h3>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p class="text-sm text-gray-400 mb-1">总资产</p>
                            <p class="text-2xl font-bold">{{formatMoney(account.total_asset)}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-400 mb-1">持仓市值</p>
                            <p class="text-2xl font-bold">{{formatMoney(account.market_value)}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-400 mb-1">现金</p>
                            <p class="text-2xl font-bold">{{formatMoney(account.cash)}}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-400 mb-1">总盈亏</p>
                            <p class="text-2xl font-bold" :style="account.total_profit >= 0 ? 'color: #00CC66' : 'color: #FF3333'">
                                {{formatMoney(account.total_profit)}}
                            </p>
                            <p class="text-sm" :style="account.total_profit_pct >= 0 ? 'color: #00CC66' : 'color: #FF3333'">
                                {{account.total_profit_pct.toFixed(2)}}%
                            </p>
                        </div>
                    </div>
                </div>

                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">🎯 预测准确率</h3>
                    <div class="grid grid-cols-4 gap-4 text-center">
                        <div>
                            <p class="text-3xl font-bold">{{accuracy.total}}</p>
                            <p class="text-sm text-gray-400">总预测</p>
                        </div>
                        <div>
                            <p class="text-3xl font-bold" style="color: #00CC66">{{accuracy.correct}}</p>
                            <p class="text-sm text-gray-400">正确</p>
                        </div>
                        <div>
                            <p class="text-3xl font-bold" style="color: #FFCC00">{{accuracy.partial}}</p>
                            <p class="text-sm text-gray-400">部分</p>
                        </div>
                        <div>
                            <p class="text-3xl font-bold" :style="accuracy.accuracy_rate >= 50 ? 'color: #00CC66' : 'color: #FF3333'">
                                {{accuracy.accuracy_rate.toFixed(1)}}%
                            </p>
                            <p class="text-sm text-gray-400">准确率</p>
                        </div>
                    </div>
                </div>

                <div class="card p-6">
                    <h3 class="text-lg font-bold mb-4">📊 持仓列表</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead class="text-left text-gray-400 border-b" style="border-color: #1A1A1A">
                                <tr>
                                    <th class="pb-3">股票</th>
                                    <th class="pb-3 text-right">现价</th>
                                    <th class="pb-3 text-right">盈亏</th>
                                    <th class="pb-3 text-right">涨跌幅</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="pos in account.positions" :key="pos.code" class="border-b" style="border-color: #1A1A1A">
                                    <td class="py-3">
                                        <p class="font-medium">{{pos.name}}</p>
                                        <p class="text-xs text-gray-400">{{pos.code}}</p>
                                    </td>
                                    <td class="py-3 text-right font-medium">{{pos.current_price.toFixed(2)}}</td>
                                    <td class="py-3 text-right">
                                        <p class="font-medium" :style="pos.profit >= 0 ? 'color: #00CC66' : 'color: #FF3333'">
                                            {{formatMoney(pos.profit)}}
                                        </p>
                                        <p class="text-xs" :style="pos.profit_pct >= 0 ? 'color: #00CC66' : 'color: #FF3333'">
                                            {{pos.profit_pct.toFixed(2)}}%
                                        </p>
                                    </td>
                                    <td class="py-3 text-right" :style="pos.change_pct >= 0 ? 'color: #00CC66' : 'color: #FF3333'">
                                        {{pos.change_pct >= 0 ? '+' : ''}}{{pos.change_pct.toFixed(2)}}%
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        const { createApp, ref, onMounted } = Vue;

        createApp({
            setup() {
                const currentTab = ref('overview');
                const tabs = [
                    { id: 'overview', name: '概览' },
                    { id: 'agents', name: 'Agents' },
                    { id: 'cron', name: 'Cron 任务' },
                    { id: 'rules', name: '规则库' },
                    { id: 'validation', name: '验证池' },
                    { id: 'knowledge', name: '知识库' },
                    { id: 'event', name: '事件分析' }
                ];
                
                const agents = ref([]);
                const cronTasks = ref([]);
                const cronStats = ref({});
                const rulesData = ref({});
                const validationPool = ref({ rules: [], by_status: {}, by_source: {}, total: 0 });
                const knowledgeBase = ref({ items: [], books: [], stats: {} });
                const account = ref({ positions: [] });
                const accuracy = ref({});
                const eventAnalysis = ref({ recent_events: [], sentiment_distribution: {}, impact_ranking: [] });
                const eventNews = ref([]);
                const rangeAnalysis = ref([]);
                const eventHistory = ref([]);
                const now = ref('');

                const formatMoney = (n) => {
                    if (!n) return '¥0';
                    if (n >= 10000) return '¥' + (n / 10000).toFixed(2) + '万';
                    return '¥' + n.toFixed(2);
                };

                const getCategoryIcon = (cat) => {
                    const icons = { direction: '🎯', magnitude: '📈', timing: '⏰', confidence: '💪' };
                    return icons[cat] || '📌';
                };

                const getCategoryName = (cat) => {
                    const names = { direction: '方向规则', magnitude: '幅度规则', timing: '时机规则', confidence: '置信度规则' };
                    return names[cat] || cat;
                };

                const updateClock = () => {
                    now.value = new Date().toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    });
                };

                const loadData = async () => {
                    try {
                        const [agentsRes, cronRes, rulesRes, poolRes, kbRes, accRes, accuracyRes, eventRes] = await Promise.all([
                            fetch('/api/agents'),
                            fetch('/api/cron'),
                            fetch('/api/rules'),
                            fetch('/api/validation-pool'),
                            fetch('/api/knowledge-base'),
                            fetch('/api/account'),
                            fetch('/api/accuracy'),
                            fetch('/api/event-analysis')
                        ]);

                        agents.value = (await agentsRes.json()).agents;
                        const cronData = await cronRes.json();
                        cronTasks.value = cronData.tasks;
                        cronStats.value = cronData;
                        rulesData.value = await rulesRes.json();
                        validationPool.value = await poolRes.json();
                        knowledgeBase.value = await kbRes.json();
                        account.value = await accRes.json();
                        accuracy.value = await accuracyRes.json();
                        eventAnalysis.value = await eventRes.json();
                    } catch (e) {
                        console.error('加载数据失败:', e);
                    }
                };

                onMounted(() => {
                    updateClock();
                    setInterval(updateClock, 1000);
                    loadData();
                    setInterval(loadData, 30000);
                });

                return {
                    currentTab,
                    tabs,
                    agents,
                    cronTasks,
                    cronStats,
                    rulesData,
                    validationPool,
                    knowledgeBase,
                    account,
                    accuracy,
                    eventAnalysis,
                    eventNews,
                    rangeAnalysis,
                    eventHistory,
                    now,
                    formatMoney,
                    getCategoryIcon,
                    getCategoryName
                };
            }
        }).mount('#app');
    </script>
</body>
</html>'''

def main():
    print("=" * 60)
    print("AI 股票团队监控面板 v1.0.0")
    print("=" * 60)
    print("功能:")
    print("  • 6个 Agents 详情（CIO/Quant/Trader/Risk/Researcher/Learning）")
    print("  • 7个 Cron 任务状态（预测/复盘/学习/监控）")
    print("  • 规则库（方向/幅度/时机/置信度 4类）")
    print("  • 验证池（来源统计/状态/置信率）")
    print("  • 知识库（3本书籍 + 知识条目）")
    print("  • 账户概览 + 预测准确率 + 持仓列表")
    print("=" * 60)
    print("访问地址: http://localhost:8082")
    print("=" * 60)
    
    server = HTTPServer(('0.0.0.0', 8082), DashboardHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n⏹️ 面板已停止")
        server.shutdown()

if __name__ == "__main__":
    main()
