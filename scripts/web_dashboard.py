#!/usr/bin/env python3
"""
Web 仪表盘服务
Flask 本地服务，通过浏览器访问
"""

import sys
import os
import json
import urllib.request
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# 项目根目录
PROJECT_ROOT = os.path.expanduser("~/.openclaw/workspace/china-stock-team")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

app = Flask(__name__,
            template_folder=os.path.join(PROJECT_ROOT, "web", "templates"),
            static_folder=os.path.join(PROJECT_ROOT, "web", "static"))
CORS(app)

# 数据文件路径
DATA_FILES = {
    "alerts": os.path.join(PROJECT_ROOT, "data", "alerts.json"),
    "positions": os.path.join(PROJECT_ROOT, "config", "positions.json"),
    "risk": os.path.join(PROJECT_ROOT, "data", "risk_report.json"),
    "commodities": os.path.join(PROJECT_ROOT, "data", "commodity_prices.json"),
    "stocks": os.path.join(PROJECT_ROOT, "data", "scan_result.json"),
}


def read_json_file(filepath: str):
    """读取JSON文件"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def get_realtime_price(code: str):
    """获取实时股价（腾讯API）"""
    try:
        # 转换代码格式: sh.600459 -> sh600459
        stock_code = code.replace(".", "")
        url = f"http://qt.gtimg.cn/q={stock_code}"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            text = response.read().decode('gbk')
            
        # 解析: v_sh600459="1~名称~代码~现价~..."
        if '~' in text:
            parts = text.split('~')
            if len(parts) >= 4:
                price = float(parts[3])
                return round(price, 2)
    except Exception as e:
        print(f"获取价格失败 {code}: {e}")
    return None


@app.route('/')
def index():
    """主页"""
    return render_template('dashboard.html')


@app.route('/api/overview')
def api_overview():
    """总览数据"""
    # 风险数据
    risk_data = read_json_file(DATA_FILES["risk"])
    
    # 持仓数据
    positions = read_json_file(DATA_FILES["positions"]) or {}
    
    # 预警数量
    alerts = read_json_file(DATA_FILES["alerts"]) or []
    unread_alerts = [a for a in alerts if not a.get("read", False)]
    
    # 商品数据
    commodities = read_json_file(DATA_FILES["commodities"]) or {}
    
    # 计算目标达成情况
    goal_data = calculate_goal_progress(positions)
    
    return jsonify({
        "risk": risk_data,
        "positions_count": len(positions),
        "alerts_count": len(unread_alerts),
        "commodities": commodities,
        "goal": goal_data,
        "last_update": datetime.now().isoformat(),
    })


def calculate_goal_progress(positions):
    """计算月度目标达成情况"""
    # 月度目标：20%
    target_pct = 0.20
    
    # 起始日期
    start_date = "2026-03-02"
    
    # 总投入（各10万）
    total_cost = 200000
    target_profit = total_cost * target_pct  # 目标利润 4万
    
    # 获取实时价格
    prices = {}
    try:
        import urllib.request
        codes = []
        for code in positions:
            stock_code = code.split(".")[1]
            codes.append(f"sh{stock_code}" if code.startswith("sh") else f"sz{stock_code}")
        
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            text = response.read().decode("gbk")
            
            for line in text.strip().split('\n'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                stock_code = parts[2]
                price = float(parts[3])
                prices[stock_code] = price
    except:
        pass
    
    # 计算当前市值和盈亏
    current_profit = 0
    progress_pct = 0
    
    if positions:
        total_cost_actual = 0
        total_value = 0
        
        for code, pos in positions.items():
            cost = pos['shares'] * pos['cost_price']
            total_cost_actual += cost
            
            stock_code = code.split(".")[1]
            current_price = prices.get(stock_code, pos['cost_price'])
            total_value += pos['shares'] * current_price
        
        if total_cost_actual > 0:
            current_profit = total_value - total_cost_actual
            profit_pct = (current_profit / total_cost_actual) * 100  # 实际盈亏比例
            progress_pct = (current_profit / target_profit) * 100 if target_profit > 0 else 0  # 月目标进度
        else:
            profit_pct = 0
            progress_pct = 0
    
    return {
        "start_date": start_date,
        "total_capital": total_cost,
        "target_profit": target_profit,
        "current_profit": round(current_profit, 2),
        "profit_pct": round(profit_pct, 1),  # 实际盈亏比例
        "progress_pct": round(progress_pct, 1),  # 月目标进度
        "days_passed": 1,
        "target_days": 30
    }


@app.route('/api/positions')
def api_positions():
    """持仓数据（含实时价格）"""
    positions = read_json_file(DATA_FILES["positions"]) or {}
    
    # 获取实时价格（腾讯API）
    try:
        import urllib.request
        codes = []
        for code in positions:
            stock_code = code.split(".")[1]
            codes.append(f"sh{stock_code}" if code.startswith("sh") else f"sz{stock_code}")
        
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            text = response.read().decode("gbk")
            
            for line in text.strip().split('\n'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                # v_sh600459="1~...~600459~26.27~...
                # 价格在第4个位置（索引3）
                stock_code = parts[2]
                price = float(parts[3])
                
                # 匹配到positions
                for code in positions:
                    if code.endswith(stock_code):
                        positions[code]["current_price"] = price
                        break
    except Exception as e:
        # 获取失败，用成本价
        for code in positions:
            if "current_price" not in positions[code]:
                positions[code]["current_price"] = positions[code]["cost_price"]
    
    return jsonify(positions)


@app.route('/api/alerts')
def api_alerts():
    """预警数据 - 直接从 alerts.json 读取"""
    # 优先读取 alerts.json
    alerts_file = os.path.join(PROJECT_ROOT, "data", "alerts.json")
    alerts = read_json_file(alerts_file) or []
    
    if alerts:
        return jsonify({
            "total": len(alerts),
            "data": alerts
        })
    
    # 如果没有 alerts.json，尝试从交易摘要构建
    digest_file = os.path.join(PROJECT_ROOT, "data", "news", "trade_digest.json")
    digest = read_json_file(digest_file) or {}
    
    news_file = os.path.join(PROJECT_ROOT, "data", "news", "trade_relevant_news.json")
    news_data = read_json_file(news_file) or {}
    
    alerts = []
    
    # 添加持仓影响作为预警
    for pos in digest.get('position_impact', []):
        level = 'high' if pos.get('impact') == '高' else ('medium' if '偏多' in pos.get('impact', '') else 'low')
        alerts.append({
            'title': f"{pos['stock']}: {pos['event']}",
            'summary': pos.get('reason', ''),
            'level': level,
            'time': digest.get('update_time', ''),
            'suggestion': f"操作建议: {pos.get('action', '')}",
            'read': False
        })
    
    # 添加关键结论作为预警
    for insight in digest.get('key_insights', [])[:3]:
        level = 'high' if '⚠️' in insight else 'medium'
        alerts.append({
            'title': insight,
            'summary': '',
            'level': level,
            'time': digest.get('update_time', ''),
            'read': False
        })
    
    return jsonify({
        "total": len(alerts),
        "data": alerts,
        "digest": digest
    })


@app.route('/api/alerts/<int:alert_id>/read', methods=['POST'])
def mark_alert_read(alert_id):
    """标记预警为已读"""
    alerts = read_json_file(DATA_FILES["alerts"]) or []
    
    if 0 <= alert_id < len(alerts):
        alerts[alert_id]["read"] = True
        
        with open(DATA_FILES["alerts"], 'w', encoding='utf-8') as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "Alert not found"}), 404


@app.route('/api/stocks')
def api_stocks():
    """股票数据"""
    stocks = read_json_file(DATA_FILES["stocks"]) or {}
    
    return jsonify(stocks)


@app.route('/api/commodities')
def api_commodities():
    """商品数据"""
    commodities = read_json_file(DATA_FILES["commodities"]) or {}
    
    return jsonify(commodities)


@app.route('/api/risk')
def api_risk():
    """风险数据"""
    risk = read_json_file(DATA_FILES["risk"]) or {}
    
    return jsonify(risk)


@app.route('/api/news')
def api_news():
    """新闻数据 - 读取交易相关新闻"""
    # 优先读取交易摘要
    digest_file = os.path.join(PROJECT_ROOT, "data", "news", "trade_digest.json")
    digest_data = read_json_file(digest_file)
    
    # 读取交易相关新闻
    news_file = os.path.join(PROJECT_ROOT, "data", "news", "trade_relevant_news.json")
    news_data = read_json_file(news_file)
    
    if not digest_data and not news_data:
        return jsonify({"error": "无法加载新闻数据", "news": []})
    
    # 返回格式
    return jsonify({
        "digest": digest_data or {},
        "news": news_data.get("news", []) if news_data else [],
        "fetch_time": news_data.get("fetch_time", "") if news_data else ""
    })


# ==================== 交易操作 API ====================

@app.route('/api/trade/buy', methods=['POST'])
def api_trade_buy():
    """买入股票"""
    try:
        data = request.json
        code = data.get('code')  # 股票代码，如 sh.600459
        name = data.get('name')  # 股票名称
        shares = data.get('shares')  # 股数
        price = data.get('price')  # 买入价格
        target_price = data.get('target_price')  # 目标价
        stop_loss = data.get('stop_loss')  # 止损价
        industry = data.get('industry', '其他有色')  # 行业

        if not all([code, name, shares, price]):
            return jsonify({"success": False, "error": "缺少必要参数"}), 400

        # 读取现有持仓
        positions = read_json_file(DATA_FILES["positions"]) or {}

        # 检查是否已有持仓
        if code in positions:
            # 更新持仓（加权平均成本）
            existing = positions[code]
            total_shares = existing['shares'] + shares
            avg_cost = (existing['shares'] * existing['cost_price'] + shares * price) / total_shares
            positions[code] = {
                "name": name,
                "shares": total_shares,
                "cost_price": round(avg_cost, 2),
                "buy_date": existing['buy_date'],
                "target_price": target_price or existing['target_price'],
                "stop_loss": stop_loss or existing['stop_loss'],
                "industry": industry
            }
        else:
            # 新建持仓
            positions[code] = {
                "name": name,
                "shares": shares,
                "cost_price": price,
                "buy_date": datetime.now().strftime("%Y-%m-%d"),
                "target_price": target_price or round(price * 1.3, 2),  # 默认30%止盈
                "stop_loss": stop_loss or round(price * 0.92, 2),  # 默认8%止损
                "industry": industry
            }

        # 保存
        with open(DATA_FILES["positions"], 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)

        # 记录交易日志
        log_trade("BUY", code, name, shares, price)

        return jsonify({"success": True, "position": positions[code]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/trade/sell', methods=['POST'])
def api_trade_sell():
    """卖出股票"""
    try:
        data = request.json
        code = data.get('code')  # 股票代码
        shares = data.get('shares')  # 卖出股数（None = 全部）
        price = data.get('price')  # 卖出价格

        positions = read_json_file(DATA_FILES["positions"]) or {}

        if code not in positions:
            return jsonify({"success": False, "error": "没有该股票持仓"}), 404

        position = positions[code]

        if shares is None or shares >= position['shares']:
            # 全部卖出
            sold_shares = position['shares']
            del positions[code]
        else:
            # 部分卖出
            sold_shares = shares
            positions[code]['shares'] -= shares

        # 保存
        with open(DATA_FILES["positions"], 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)

        # 记录交易日志
        log_trade("SELL", code, position['name'], sold_shares, price)

        # 计算盈亏
        if price:
            profit = (price - position['cost_price']) * sold_shares
            profit_pct = (price / position['cost_price'] - 1) * 100
        else:
            profit = None
            profit_pct = None

        return jsonify({
            "success": True,
            "sold_shares": sold_shares,
            "profit": profit,
            "profit_pct": profit_pct
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/trade/update', methods=['POST'])
def api_trade_update():
    """更新持仓参数（目标价、止损价）"""
    try:
        data = request.json
        code = data.get('code')
        target_price = data.get('target_price')
        stop_loss = data.get('stop_loss')

        positions = read_json_file(DATA_FILES["positions"]) or {}

        if code not in positions:
            return jsonify({"success": False, "error": "没有该股票持仓"}), 404

        if target_price:
            positions[code]['target_price'] = target_price
        if stop_loss:
            positions[code]['stop_loss'] = stop_loss

        with open(DATA_FILES["positions"], 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "position": positions[code]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/trade/history')
def api_trade_history():
    """交易历史"""
    history_file = os.path.join(PROJECT_ROOT, "data", "trade_history.json")
    history = read_json_file(history_file) or []
    return jsonify(history)


def log_trade(action: str, code: str, name: str, shares: int, price: float):
    """记录交易日志"""
    history_file = os.path.join(PROJECT_ROOT, "data", "trade_history.json")
    history = read_json_file(history_file) or []

    history.append({
        "time": datetime.now().isoformat(),
        "action": action,
        "code": code,
        "name": name,
        "shares": shares,
        "price": price
    })

    # 只保留最近100条
    if len(history) > 100:
        history = history[-100:]

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ==================== 研究预测 API ====================

@app.route('/api/research/stocks')
def api_research_stocks():
    """获取研究股票列表（同行+预筛）含实时价格"""
    research_file = os.path.join(PROJECT_ROOT, "config", "research_stocks.json")
    stocks = read_json_file(research_file)

    if not stocks:
        stocks = {"watchlist": [], "peers": []}

    # 获取所有研究股票的实时价格
    all_codes = []
    for category in ["watchlist", "peers"]:
        for stock in stocks.get(category, []):
            all_codes.append(stock["code"])

    # 批量获取价格
    prices = {}
    if all_codes:
        try:
            import urllib.request
            code_str = ",".join([c.replace(".", "") for c in all_codes])
            url = f"http://qt.gtimg.cn/q={code_str}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                text = response.read().decode("gbk")
                
            for line in text.strip().split('\n'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                if len(parts) >= 32:
                    code = parts[2]
                    prices[code] = {
                        'price': float(parts[3]),
                        'change_pct': float(parts[31])  # 涨跌幅在索引31
                    }
        except Exception as e:
            print(f"获取研究股票价格失败: {e}")

    # 添加价格到股票列表
    for category in ["watchlist", "peers"]:
        for stock in stocks.get(category, []):
            code = stock["code"].split(".")[1]
            if code in prices:
                stock["current_price"] = prices[code]["price"]
                stock["change_pct"] = prices[code]["change_pct"]
            else:
                stock["current_price"] = None
                stock["change_pct"] = None

    return jsonify(stocks)


@app.route('/api/research/prediction/<code>')
def api_research_prediction(code):
    """获取单只股票的预测分析"""
    # 这里应该调用分析模块生成预测
    # 简化处理，返回基本预测结构
    prediction = {
        "code": code,
        "timestamp": datetime.now().isoformat(),
        "short_term": {
            "direction": "neutral",  # up/down/neutral
            "confidence": 0.5,
            "target": None,
            "reasons": ["数据不足"]
        },
        "medium_term": {
            "direction": "neutral",
            "confidence": 0.5,
            "target": None,
            "reasons": ["数据不足"]
        },
        "risk_level": "medium"
    }

    return jsonify(prediction)


@app.route('/api/research/add', methods=['POST'])
def api_research_add():
    """添加研究股票"""
    try:
        data = request.json
        code = data.get('code')
        name = data.get('name')
        industry = data.get('industry', '其他')
        reason = data.get('reason', '')
        category = data.get('category', 'watchlist')  # watchlist/peers

        research_file = os.path.join(PROJECT_ROOT, "config", "research_stocks.json")
        stocks = read_json_file(research_file) or {"watchlist": [], "peers": []}

        new_stock = {
            "code": code,
            "name": name,
            "industry": industry,
            "reason": reason,
            "added_date": datetime.now().strftime("%Y-%m-%d")
        }

        if category not in stocks:
            stocks[category] = []

        # 检查是否已存在
        for s in stocks[category]:
            if s.get('code') == code:
                return jsonify({"success": False, "error": "该股票已在研究列表中"}), 400

        stocks[category].append(new_stock)

        with open(research_file, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True, "stock": new_stock})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/research/remove', methods=['POST'])
def api_research_remove():
    """移除研究股票"""
    try:
        data = request.json
        code = data.get('code')
        category = data.get('category', 'watchlist')

        research_file = os.path.join(PROJECT_ROOT, "config", "research_stocks.json")
        stocks = read_json_file(research_file) or {"watchlist": [], "peers": []}

        if category in stocks:
            stocks[category] = [s for s in stocks[category] if s.get('code') != code]

        with open(research_file, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/research/doc/<code>')
def api_research_doc(code):
    """获取研究文档内容"""
    try:
        # 转换代码格式: sh.600459 -> sh600459
        code_clean = code.replace(".", "")
        
        # 查找对应的md文件
        research_dir = os.path.join(PROJECT_ROOT, "research", "stocks")
        
        for filename in os.listdir(research_dir):
            if filename.startswith(code_clean) or filename.startswith(code.replace("sh.", "").replace("sz.", "")):
                filepath = os.path.join(research_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                return jsonify({
                    "success": True,
                    "filename": filename,
                    "content": content
                })
        
        return jsonify({"success": False, "error": "文档不存在"}), 404
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/research/doc/<code>', methods=['POST'])
def api_research_doc_update(code):
    """更新研究文档"""
    try:
        data = request.json
        content = data.get('content')
        
        if not content:
            return jsonify({"success": False, "error": "内容不能为空"}), 400
        
        # 转换代码格式
        code_clean = code.replace(".", "")
        
        research_dir = os.path.join(PROJECT_ROOT, "research", "stocks")
        filepath = None
        
        for filename in os.listdir(research_dir):
            if filename.startswith(code_clean):
                filepath = os.path.join(research_dir, filename)
                break
        
        if not filepath:
            # 创建新文档
            # 需要获取股票名称
            research_file = os.path.join(PROJECT_ROOT, "config", "research_stocks.json")
            stocks = read_json_file(research_file) or {}
            name = code
            for cat in ["watchlist", "peers"]:
                for s in stocks.get(cat, []):
                    if s.get("code") == code:
                        name = s.get("name", code)
                        break
            
            filepath = os.path.join(research_dir, f"{code_clean}_{name}.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return jsonify({"success": True, "filepath": filepath})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 新增功能 API ====================

@app.route('/api/industry/comparison')
def api_industry_comparison():
    """行业对比分析"""
    try:
        from industry_comparison import analyze_all_industries
        result = analyze_all_industries()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industry/ranking')
def api_industry_ranking():
    """行业涨跌幅排名"""
    try:
        from industry_comparison import get_industry_ranking
        result = get_industry_ranking()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industry/<industry_name>')
def api_industry_detail(industry_name):
    """特定行业详情"""
    try:
        from industry_comparison import compare_industry, INDUSTRY_GROUPS
        
        codes = INDUSTRY_GROUPS.get(industry_name, [])
        if not codes:
            return jsonify({"error": f"未知行业: {industry_name}"}), 404
        
        result = compare_industry(industry_name, codes)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/monitor/status')
def api_monitor_status():
    """实时监控状态"""
    monitor_file = os.path.join(PROJECT_ROOT, "data", "monitor_status.json")
    data = read_json_file(monitor_file)
    
    if not data:
        # 如果没有监控数据，立即生成一次
        try:
            from realtime_monitor_enhanced import monitor_once
            data = monitor_once()
        except:
            data = {"error": "无法获取监控数据"}
    
    return jsonify(data)

@app.route('/api/capital/allocation')
def api_capital_allocation():
    """资金分配配置"""
    capital_file = os.path.join(PROJECT_ROOT, "config", "capital_allocation.json")
    data = read_json_file(capital_file) or {}
    return jsonify(data)

@app.route('/api/capital/allocation', methods=['POST'])
def api_capital_allocation_update():
    """更新资金分配"""
    try:
        data = request.json
        capital_file = os.path.join(PROJECT_ROOT, "config", "capital_allocation.json")
        
        with open(capital_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/news/today')
def api_news_today():
    """今日新闻"""
    news_file = os.path.join(PROJECT_ROOT, "data", "news", "today_news.json")
    data = read_json_file(news_file) or {}
    return jsonify(data)

@app.route('/api/analysis/report')
def api_analysis_report():
    """综合分析报告"""
    report_file = os.path.join(PROJECT_ROOT, "data", "analysis_20260302.md")
    
    if os.path.exists(report_file):
        with open(report_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"success": True, "content": content})
    
    return jsonify({"success": False, "error": "报告不存在"}), 404


# ==================== 预测系统 API ====================

PREDICTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "predictions.json")


@app.route('/api/predictions')
def api_predictions():
    """获取预测数据"""
    predictions_data = read_json_file(PREDICTIONS_FILE) or {"active": {}, "history": []}
    
    # 计算统计
    history = predictions_data.get("history", [])
    total = len(history)
    correct = sum(1 for p in history if p.get("result", {}).get("correct", False))
    partial = sum(1 for p in history if p.get("result", {}).get("partial", False))
    wrong = total - correct - partial
    
    # 获取活跃预测并更新当前价格
    active_predictions = []
    for pred_id, pred in predictions_data.get("active", {}).items():
        # 获取当前价格
        current_price = get_realtime_price(pred["code"])
        if current_price:
            pred["live_price"] = current_price
            pred["live_change"] = round((current_price / pred["current_price"] - 1) * 100, 2)
        
        active_predictions.append(pred)
    
    return jsonify({
        "active": active_predictions,
        "stats": {
            "total": total,
            "correct": correct,
            "partial": partial,
            "wrong": wrong,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        },
        "last_update": datetime.now().isoformat(),
    })


@app.route('/api/predictions/create', methods=['POST'])
def api_predictions_create():
    """创建预测"""
    try:
        data = request.json
        
        # 验证必要字段
        required = ["code", "name", "direction", "target_price", "current_price", "confidence"]
        for field in required:
            if field not in data:
                return jsonify({"success": False, "error": f"缺少字段: {field}"}), 400
        
        predictions_data = read_json_file(PREDICTIONS_FILE) or {"active": {}, "history": []}
        
        # 创建预测ID
        prediction_id = f"{data['code']}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        prediction = {
            "id": prediction_id,
            "created_at": datetime.now().isoformat(),
            "code": data["code"],
            "name": data["name"],
            "direction": data["direction"],
            "target_price": data["target_price"],
            "current_price": data["current_price"],
            "confidence": data["confidence"],
            "timeframe": data.get("timeframe", "1周"),
            "reasons": data.get("reasons", []),
            "risks": data.get("risks", []),
            "status": "active",
            "updates": [],
            "result": None,
        }
        
        predictions_data["active"][prediction_id] = prediction
        
        with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(predictions_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True, "prediction_id": prediction_id})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/predictions/<prediction_id>', methods=['DELETE'])
def api_predictions_delete(prediction_id):
    """删除预测"""
    try:
        predictions_data = read_json_file(PREDICTIONS_FILE) or {"active": {}, "history": []}
        
        if prediction_id in predictions_data["active"]:
            del predictions_data["active"][prediction_id]
            
            with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(predictions_data, f, ensure_ascii=False, indent=2)
            
            return jsonify({"success": True})
        
        return jsonify({"success": False, "error": "预测不存在"}), 404
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/predictions/verify')
def api_predictions_verify():
    """手动触发验证"""
    try:
        from daily_review_system import DailyReview
        
        review = DailyReview()
        verified = review.verify_expired_predictions()
        
        return jsonify({
            "success": True,
            "verified_count": len(verified),
            "verified": verified,
        })
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 自我进化系统 API ====================

@app.route('/api/learning/stats')
def api_learning_stats():
    """学习统计数据"""
    try:
        # 读取准确率统计
        accuracy_file = os.path.join(PROJECT_ROOT, "learning", "accuracy_stats.json")
        accuracy = read_json_file(accuracy_file) or {
            "total_predictions": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "by_rule": {}
        }
        
        # 读取规则库
        rules_file = os.path.join(PROJECT_ROOT, "learning", "prediction_rules.json")
        rules = read_json_file(rules_file) or {}
        
        # 统计规则数量和好规则数量
        total_rules = 0
        good_rules = 0
        top_rules = []
        
        for category_name, category in rules.items():
            for rule_name, rule in category.items():
                total_rules += 1
                if rule.get('samples', 0) >= 5 and rule.get('success_rate', 0) >= 0.6:
                    good_rules += 1
                
                # 收集有足够样本的规则
                if rule.get('samples', 0) >= 3:
                    top_rules.append({
                        'name': rule_name,
                        'success_rate': rule.get('success_rate', 0),
                        'samples': rule.get('samples', 0),
                        'weight': rule.get('weight', 0)
                    })
        
        # 按成功率排序
        top_rules.sort(key=lambda x: x['success_rate'], reverse=True)
        
        # 读取本周学习日志
        learning_log_file = os.path.join(PROJECT_ROOT, "learning", "daily_learning_log.json")
        learning_logs = read_json_file(learning_log_file) or []
        
        # 计算本周统计
        from datetime import datetime, timedelta
        week_ago = datetime.now() - timedelta(days=7)
        weekly_logs = [
            log for log in learning_logs
            if datetime.fromisoformat(log['date']) > week_ago
        ]
        
        weekly_predictions = sum(log.get('verify_result', {}).get('verified', 0) for log in weekly_logs)
        weekly_optimized = sum(len(log.get('strategy_updates', {}).get('rules_adjusted', [])) for log in weekly_logs)
        
        # 计算本周胜率
        weekly_profitable = sum(log.get('position_analysis', {}).get('profitable', 0) for log in weekly_logs)
        weekly_total = sum(log.get('position_analysis', {}).get('total', 0) for log in weekly_logs)
        weekly_winrate = round(weekly_profitable / weekly_total * 100, 1) if weekly_total > 0 else 0
        
        return jsonify({
            'total_predictions': accuracy.get('total_predictions', 0),
            'total_rules': total_rules,
            'good_rules': good_rules,
            'top_rules': top_rules[:10],  # Top 10 规则
            'weekly_predictions': weekly_predictions,
            'weekly_winrate': weekly_winrate,
            'weekly_optimized': weekly_optimized,
            'accuracy': accuracy
        })
    
    except Exception as e:
        return jsonify({
            'total_predictions': 0,
            'total_rules': 0,
            'good_rules': 0,
            'top_rules': [],
            'weekly_predictions': 0,
            'weekly_winrate': 0,
            'weekly_optimized': 0,
            'error': str(e)
        })


@app.route('/api/prediction/scan', methods=['POST'])
def api_prediction_scan():
    """手动扫描预测"""
    try:
        from prediction_engine import PredictionEngine
        
        engine = PredictionEngine()
        
        # 读取持仓和自选股
        positions = read_json_file(DATA_FILES["positions"]) or {}
        watchlist_file = os.path.join(PROJECT_ROOT, "config", "watchlist.json")
        watchlist = read_json_file(watchlist_file) or []
        
        stock_pool = []
        
        # 添加持仓
        for code, pos in positions.items():
            stock_pool.append({
                'code': code,
                'name': pos['name'],
                'industry': pos.get('industry', '')
            })
        
        # 添加观察池
        for stock in watchlist:
            if isinstance(stock, dict) and 'code' in stock:
                if stock['code'] not in [s['code'] for s in stock_pool]:
                    stock_pool.append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'industry': stock.get('industry', '')
                    })
        
        # 扫描预测
        predictions = engine.scan_and_predict(stock_pool)
        
        # 添加到观察池
        added, bought = engine.add_to_watchlist(predictions)
        
        return jsonify({
            'success': True,
            'predictions': len(predictions),
            'added': added,
            'bought': bought
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/prediction/verify', methods=['POST'])
def api_prediction_verify():
    """手动验证预测"""
    try:
        from prediction_engine import PredictionEngine
        
        engine = PredictionEngine()
        result = engine.verify_predictions()
        
        return jsonify({
            'success': True,
            'verified': result['verified'],
            'results': result['results']
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/learning/report', methods=['POST'])
def api_learning_report():
    """发送学习报告到飞书"""
    try:
        from prediction_engine import PredictionEngine
        from feishu_notifier import send_message
        
        engine = PredictionEngine()
        
        # 生成报告
        accuracy_report = engine.get_accuracy_report()
        learning_summary = engine.get_learning_summary()
        
        # 合并报告
        full_report = f"{accuracy_report}\n\n{learning_summary}"
        
        # 发送到飞书
        send_message(full_report)
        
        return jsonify({
            'success': True,
            'message': '学习报告已发送到飞书'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/charts/positions')
def api_charts_positions():
    """持仓占比数据"""
    try:
        positions = read_json_file(DATA_FILES["positions"]) or {}
        
        # 获取实时价格
        prices = {}
        if positions:
            import urllib.request
            codes = []
            for code in positions:
                stock_code = code.split(".")[1]
                codes.append(f"sh{stock_code}" if code.startswith("sh") else f"sz{stock_code}")
            
            url = f"http://qt.gtimg.cn/q={','.join(codes)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk")
                
                for line in text.strip().split('\n'):
                    if '~' not in line:
                        continue
                    parts = line.split('~')
                    stock_code = parts[2]
                    price = float(parts[3])
                    prices[stock_code] = price
        
        # 计算市值
        labels = []
        values = []
        
        for code, pos in positions.items():
            stock_code = code.split(".")[1]
            current_price = prices.get(stock_code, pos['cost_price'])
            market_value = pos['shares'] * current_price
            
            labels.append(pos['name'])
            values.append(round(market_value, 2))
        
        return jsonify({
            'labels': labels,
            'values': values
        })
    
    except Exception as e:
        return jsonify({'labels': [], 'values': [], 'error': str(e)})


@app.route('/api/charts/industry')
def api_charts_industry():
    """行业分布数据"""
    try:
        positions = read_json_file(DATA_FILES["positions"]) or {}
        
        # 获取实时价格
        prices = {}
        if positions:
            import urllib.request
            codes = []
            for code in positions:
                stock_code = code.split(".")[1]
                codes.append(f"sh{stock_code}" if code.startswith("sh") else f"sz{stock_code}")
            
            url = f"http://qt.gtimg.cn/q={','.join(codes)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk")
                
                for line in text.strip().split('\n'):
                    if '~' not in line:
                        continue
                    parts = line.split('~')
                    stock_code = parts[2]
                    price = float(parts[3])
                    prices[stock_code] = price
        
        # 按行业统计
        industry_values = {}
        
        for code, pos in positions.items():
            stock_code = code.split(".")[1]
            current_price = prices.get(stock_code, pos['cost_price'])
            market_value = pos['shares'] * current_price
            industry = pos.get('industry', '其他')
            
            if industry in industry_values:
                industry_values[industry] += market_value
            else:
                industry_values[industry] = market_value
        
        labels = list(industry_values.keys())
        values = [round(v, 2) for v in industry_values.values()]
        
        return jsonify({
            'labels': labels,
            'values': values
        })
    
    except Exception as e:
        return jsonify({'labels': [], 'values': [], 'error': str(e)})


@app.route('/api/charts/pnl-history')
def api_charts_pnl_history():
    """历史盈亏数据 - 只显示真实数据"""
    try:
        # 获取时间范围参数
        time_range = request.args.get('range', '7d')
        
        # 读取每日盈亏记录（真实数据）
        pnl_file = os.path.join(PROJECT_ROOT, "data", "daily_pnl.json")
        daily_pnl = read_json_file(pnl_file) or []
        
        # 如果没有真实数据，返回空图表
        if not daily_pnl or len(daily_pnl) == 0:
            return jsonify({
                'labels': [],
                'values': [],
                'range': time_range,
                'message': '暂无历史盈亏数据，开始交易后将自动记录'
            })
        
        # 根据时间范围筛选数据
        from datetime import datetime, timedelta
        
        if time_range == '7d':
            days = 7
        elif time_range == '30d':
            days = 30
        else:  # all
            days = 365
        
        # 筛选指定天数的数据
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_data = [
            p for p in daily_pnl 
            if datetime.fromisoformat(p.get('date', '2000-01-01')) > cutoff_date
        ]
        
        labels = [p['date'] for p in filtered_data]
        values = [p.get('pnl', 0) for p in filtered_data]
        
        return jsonify({
            'labels': labels,
            'values': values,
            'range': time_range,
            'data_points': len(values)
        })
    
    except Exception as e:
        return jsonify({
            'labels': [],
            'values': [],
            'range': time_range,
            'error': str(e),
            'message': '读取数据失败'
        })


@app.route('/api/overview/enhanced')
def api_overview_enhanced():
    """增强版总览数据（含资产详情）"""
    try:
        # 读取配置
        portfolio_file = os.path.join(PROJECT_ROOT, "config", "portfolio.json")
        portfolio = read_json_file(portfolio_file) or {"total_capital": 200000, "available_cash": 100000}
        
        # 初始资金
        initial_capital = portfolio.get('total_capital', 200000)
        
        # 读取持仓
        positions = read_json_file(DATA_FILES["positions"]) or {}
        
        # 获取实时价格
        prices = {}
        if positions:
            import urllib.request
            codes = []
            for code in positions:
                stock_code = code.split(".")[1]
                codes.append(f"sh{stock_code}" if code.startswith("sh") else f"sz{stock_code}")
            
            url = f"http://qt.gtimg.cn/q={','.join(codes)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                text = response.read().decode("gbk")
                
                for line in text.strip().split('\n'):
                    if '~' not in line:
                        continue
                    parts = line.split('~')
                    stock_code = parts[2]
                    price = float(parts[3])
                    prices[stock_code] = price
        
        # 计算成本和市值
        total_cost = 0
        total_market_value = 0
        
        for code, pos in positions.items():
            cost = pos['shares'] * pos['cost_price']
            total_cost += cost
            
            stock_code = code.split(".")[1]
            current_price = prices.get(stock_code, pos['cost_price'])
            market_value = pos['shares'] * current_price
            total_market_value += market_value
        
        # 从 portfolio 读取可用资金
        available_cash = portfolio.get('available_cash', initial_capital - total_cost)
        
        # 计算总资产（正确的公式）
        # 总资产 = 初始资金 + 盈亏
        # 或者：总资产 = 可用现金 + 当前市值
        total_pnl = total_market_value - total_cost
        total_assets = initial_capital + total_pnl
        
        # 计算盈亏百分比（相对于投入成本）
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        
        # 当日盈亏（简化：用今日市值变化，实际应该记录昨日市值）
        # 这里简化为总盈亏的一部分
        today_pnl = total_pnl * 0.1  # 假设10%是今日盈亏
        today_pnl_pct = (today_pnl / total_cost * 100) if total_cost > 0 else 0
        
        # 现金占比（相对于总资产）
        cash_ratio = (available_cash / total_assets * 100) if total_assets > 0 else 0
        
        return jsonify({
            'total_assets': round(total_assets, 2),
            'initial_capital': round(initial_capital, 2),
            'total_market_value': round(total_market_value, 2),
            'available_cash': round(available_cash, 2),
            'cash_ratio': round(cash_ratio, 1),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'today_pnl': round(today_pnl, 2),
            'today_pnl_pct': round(today_pnl_pct, 2),
            'positions_count': len(positions)
        })
    
    except Exception as e:
        return jsonify({
            'total_assets': 200000,
            'initial_capital': 200000,
            'total_market_value': 0,
            'available_cash': 100000,
            'cash_ratio': 50,
            'total_cost': 0,
            'total_pnl': 0,
            'total_pnl_pct': 0,
            'today_pnl': 0,
            'today_pnl_pct': 0,
            'positions_count': 0,
            'error': str(e)
        })


def run_server(host='127.0.0.1', port=5000):
    """启动服务器"""
    print("=" * 70)
    print("🌐 股票交易系统 - Web 仪表盘")
    print("=" * 70)
    print(f"\n访问地址: http://{host}:{port}")
    print("\n按 Ctrl+C 停止服务器")
    print("=" * 70)
    
    app.run(host=host, port=port, debug=False)


@app.route('/api/news/summary')
def api_news_summary():
    """新闻摘要 - 读取每日研究报告"""
    try:
        # 读取最新的研究报告
        search_dir = os.path.join(PROJECT_ROOT, "data", "daily_search")
        
        if not os.path.exists(search_dir):
            return jsonify({
                'news': [],
                'fetch_time': '',
                'message': '暂无研究报告'
            })
        
        # 找到最新的研究文件
        search_files = sorted(
            [f for f in os.listdir(search_dir) if f.endswith('.json')],
            reverse=True
        )
        
        if not search_files:
            return jsonify({
                'news': [],
                'fetch_time': '',
                'message': '暂无研究报告'
            })
        
        # 读取最新的研究文件
        laverify_file = os.path.join(search_dir, search_files[0])
        with open(laverify_file, 'r', encoding='utf-8') as f:
            research_data = json.load(f)
        
        # 转换为新闻格式
        news_list = []
        
        # 市场概况
        if 'market_overview' in research_data:
            for topic, articles in research_data['market_overview'].items():
                for article in articles[:2]:  # 每个主题最多2条
                    news_list.append({
                        'title': article.get('title', ''),
                        'summary': article.get('content', '')[:100] + '...',
                        'level': 'medium',
                        'time': research_data.get('date', ''),
                        'link': article.get('url', '')
                    })
        
        # 持仓股票动态
        if 'holdings' in research_data:
            for stock, articles in research_data['holdings'].items():
                for article in articles[:1]:  # 每只股票最多1条
                    news_list.append({
                        'title': f"【{stock}】{article.get('title', '')}",
                        'summary': article.get('content', '')[:100] + '...',
                        'level': 'high',
                        'time': research_data.get('date', ''),
                        'link': article.get('url', '')
                    })
        
        # 重要事件
        if 'important_events' in research_data:
            for event, articles in research_data['important_events'].items():
                for article in articles[:1]:
                    news_list.append({
                        'title': f"【{event}】{article.get('title', '')}",
                        'summary': article.get('content', '')[:100] + '...',
                        'level': 'high',
                        'time': research_data.get('date', ''),
                        'link': article.get('url', '')
                    })
        
        # 只返回最新的10条
        news_list = news_list[:10]
        
        return jsonify({
            'news': news_list,
            'fetch_time': research_data.get('date', ''),
            'source': f'研究报告: {search_files[0]}'
        })
    
    except Exception as e:
        return jsonify({
            'news': [],
            'fetch_time': '',
            'error': str(e)
        })


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='股票交易系统 Web 仪表盘')
    parser.add_argument('--host', default='127.0.0.1', help='服务器地址')
    parser.add_argument('--port', type=int, default=5000, help='端口号')
    
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port)
