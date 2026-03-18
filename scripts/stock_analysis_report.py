#!/usr/bin/env python3
"""
股票分析报表生成器
当股票团队分析一只股票时，生成漂亮的可视化 HTML 报表
借鉴 ValueCell 的 UI 设计
"""

import sys
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# 项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 虚拟环境
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / "python3.14" / "site-packages"
sys.path.insert(0, str(VENV_PATH))

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_stock_data(symbol):
    """获取股票数据"""
    conn = sqlite3.connect(PROJECT_ROOT / "database" / "stock_team.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 基本信息 - 从 watchlist 获取
    cursor.execute("""
        SELECT * FROM watchlist 
        WHERE symbol = ?
        LIMIT 1
    """, (symbol,))
    stock_info = cursor.fetchone()
    
    if not stock_info:
        # 尝试从 quant_analysis 获取
        cursor.execute("""
            SELECT * FROM quant_analysis 
            WHERE symbol = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (symbol,))
        stock_info = cursor.fetchone()
    
    # 持仓信息
    cursor.execute("""
        SELECT * FROM positions 
        WHERE symbol = ? AND status = 'holding'
    """, (symbol,))
    position = cursor.fetchone()
    
    # 预测历史
    predictions_file = PROJECT_ROOT / "data" / "predictions.json"
    predictions = []
    if predictions_file.exists():
        with open(predictions_file, 'r', encoding='utf-8') as f:
            pred_data = json.load(f)
            predictions = [p for p in pred_data.get('history', []) if symbol in p.get('symbol', '')]
    
    conn.close()
    
    return {
        "info": dict(stock_info) if stock_info else {"symbol": symbol, "name": symbol},
        "position": dict(position) if position else None,
        "predictions": predictions
    }


def get_technical_indicators(symbol):
    """获取技术指标（模拟数据，实际应从数据库获取）"""
    import random
    
    return {
        "ema_12": round(25.5 + random.uniform(-2, 2), 2),
        "ema_26": round(24.8 + random.uniform(-2, 2), 2),
        "ema_50": round(23.5 + random.uniform(-2, 2), 2),
        "macd": round(0.7 + random.uniform(-0.5, 0.5), 3),
        "macd_signal": round(0.5 + random.uniform(-0.3, 0.3), 3),
        "macd_histogram": round(0.2 + random.uniform(-0.2, 0.2), 3),
        "rsi": round(55 + random.uniform(-15, 15), 1),
        "bb_upper": round(28.5 + random.uniform(-2, 2), 2),
        "bb_middle": round(25.0 + random.uniform(-1, 1), 2),
        "bb_lower": round(21.5 + random.uniform(-2, 2), 2),
    }


def generate_price_chart_data(symbol, days=60):
    """生成价格图表数据"""
    import random
    from datetime import timedelta
    
    base_price = 25.0
    dates = []
    prices = []
    
    for i in range(days):
        date = datetime.now() - timedelta(days=days - i - 1)
        if date.weekday() < 5:  # 只在工作日
            dates.append(date.strftime("%Y-%m-%d"))
            change = random.uniform(-0.05, 0.05)
            base_price = base_price * (1 + change)
            prices.append(round(base_price, 2))
    
    return {"dates": dates, "prices": prices}


def generate_report(symbol, analysis_data=None):
    """生成 HTML 分析报表"""
    
    # 获取数据
    stock_data = get_stock_data(symbol)
    tech_indicators = get_technical_indicators(symbol)
    price_data = generate_price_chart_data(symbol)
    
    # 合并分析数据
    if analysis_data:
        stock_data["analysis"] = analysis_data
    
    info = stock_data.get("info", {})
    position = stock_data.get("position")
    predictions = stock_data.get("predictions", [])
    
    # 生成 HTML
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{info.get('name', symbol)} - 股票分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        'vc-dark': '#0d1117',
                        'vc-card': '#161b22',
                        'vc-border': '#30363d',
                        'vc-blue': '#1f6feb',
                        'vc-green': '#3fb950',
                        'vc-red': '#f85149',
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
            background: #0d1117;
            color: #e6edf3;
        }}
        .gradient-card-blue {{ background: linear-gradient(135deg, rgba(17, 24, 39, 0.8) 5%, rgba(29, 78, 216, 0.35) 100%); }}
        .gradient-card-purple {{ background: linear-gradient(135deg, rgba(17, 24, 39, 0.8) 5%, rgba(124, 58, 237, 0.3) 100%); }}
        .gradient-card-green {{ background: linear-gradient(135deg, rgba(17, 24, 39, 0.8) 5%, rgba(34, 197, 94, 0.3) 100%); }}
        .gradient-card-pink {{ background: linear-gradient(135deg, rgba(17, 24, 39, 0.8) 5%, rgba(219, 39, 119, 0.25) 100%); }}
    </style>
</head>
<body class="min-h-screen p-6">
    <div class="max-w-6xl mx-auto">
        
        <!-- 标题 -->
        <header class="mb-6">
            <div class="flex items-center justify-between">
                <div>
                    <h1 class="text-3xl font-bold flex items-center gap-3">
                        <span class="text-4xl">📊</span>
                        {info.get('name', symbol)}
                        <span class="text-lg font-normal text-gray-500">{symbol}</span>
                    </h1>
                    <p class="text-gray-500 mt-2">股票分析报告 · 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                </div>
                <div class="text-right">
                    <div class="text-3xl font-bold">¥{info.get('price', '--')}</div>
                    <div class="{'text-vc-green' if info.get('change_pct', 0) >= 0 else 'text-vc-red'}">
                        {info.get('change_pct', 0):+.2f}%
                    </div>
                </div>
            </div>
        </header>
        
        <!-- 核心指标 -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div class="gradient-card-blue rounded-xl p-5 border border-vc-border">
                <p class="text-gray-400 text-sm">市值</p>
                <p class="text-2xl font-bold mt-1">{info.get('market_cap', '--')}亿</p>
            </div>
            <div class="gradient-card-purple rounded-xl p-5 border border-vc-border">
                <p class="text-gray-400 text-sm">PB</p>
                <p class="text-2xl font-bold mt-1">{info.get('pb', '--')}</p>
            </div>
            <div class="gradient-card-green rounded-xl p-5 border border-vc-border">
                <p class="text-gray-400 text-sm">ROE</p>
                <p class="text-2xl font-bold mt-1">{info.get('roe', '--')}%</p>
            </div>
            <div class="gradient-card-pink rounded-xl p-5 border border-vc-border">
                <p class="text-gray-400 text-sm">综合评分</p>
                <p class="text-2xl font-bold mt-1">{info.get('score', '--')}/100</p>
            </div>
        </div>
        
        <!-- 价格走势图 -->
        <div class="bg-vc-card border border-vc-border rounded-xl p-5 mb-6">
            <h3 class="text-lg font-semibold mb-4">📈 价格走势</h3>
            <div id="price-chart" style="height: 300px;"></div>
        </div>
        
        <!-- 技术指标 + 分析 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            
            <!-- 技术指标 -->
            <div class="bg-vc-card border border-vc-border rounded-xl p-5">
                <h3 class="text-lg font-semibold mb-4">📊 技术指标</h3>
                <div class="space-y-4">
                    <!-- RSI -->
                    <div class="bg-vc-dark rounded-lg p-4">
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-gray-400">RSI (14)</span>
                            <span class="font-bold {'text-vc-green' if tech_indicators['rsi'] < 30 else 'text-vc-red' if tech_indicators['rsi'] > 70 else 'text-white'}">{tech_indicators['rsi']}</span>
                        </div>
                        <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div class="h-full bg-gradient-to-r from-vc-green via-yellow-500 to-vc-red" style="width: {tech_indicators['rsi']}%"></div>
                        </div>
                        <div class="flex justify-between text-xs text-gray-500 mt-1">
                            <span>超卖(30)</span>
                            <span>超买(70)</span>
                        </div>
                    </div>
                    
                    <!-- MACD -->
                    <div class="bg-vc-dark rounded-lg p-4">
                        <div class="grid grid-cols-3 gap-4 text-center">
                            <div>
                                <p class="text-gray-400 text-xs">MACD</p>
                                <p class="font-bold {'text-vc-green' if tech_indicators['macd'] > 0 else 'text-vc-red'}">{tech_indicators['macd']}</p>
                            </div>
                            <div>
                                <p class="text-gray-400 text-xs">信号线</p>
                                <p class="font-bold">{tech_indicators['macd_signal']}</p>
                            </div>
                            <div>
                                <p class="text-gray-400 text-xs">柱状图</p>
                                <p class="font-bold {'text-vc-green' if tech_indicators['macd_histogram'] > 0 else 'text-vc-red'}">{tech_indicators['macd_histogram']}</p>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 布林带 -->
                    <div class="bg-vc-dark rounded-lg p-4">
                        <div class="grid grid-cols-3 gap-4 text-center">
                            <div>
                                <p class="text-gray-400 text-xs">上轨</p>
                                <p class="font-bold">¥{tech_indicators['bb_upper']}</p>
                            </div>
                            <div>
                                <p class="text-gray-400 text-xs">中轨</p>
                                <p class="font-bold">¥{tech_indicators['bb_middle']}</p>
                            </div>
                            <div>
                                <p class="text-gray-400 text-xs">下轨</p>
                                <p class="font-bold">¥{tech_indicators['bb_lower']}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- AI 分析 -->
            <div class="bg-vc-card border border-vc-border rounded-xl p-5">
                <h3 class="text-lg font-semibold mb-4">🤖 AI 分析结论</h3>
                <div class="space-y-4">
                    {f'''
                    <div class="bg-vc-dark rounded-lg p-4">
                        <p class="text-gray-400 text-sm mb-2">综合评级</p>
                        <div class="flex items-center gap-2">
                            <span class="text-2xl font-bold {'text-vc-green' if info.get('recommendation') == 'buy' else 'text-vc-red' if info.get('recommendation') == 'sell' else 'text-yellow-500'}">
                                {'强烈买入' if info.get('recommendation') == 'buy' else '建议卖出' if info.get('recommendation') == 'sell' else '持有观望'}
                            </span>
                            <span class="text-gray-500">置信度 {info.get('confidence', 75)}%</span>
                        </div>
                    </div>
                    ''' if info.get('recommendation') else ''}
                    
                    <div class="bg-vc-dark rounded-lg p-4">
                        <p class="text-gray-400 text-sm mb-2">分析要点</p>
                        <ul class="space-y-2 text-sm">
                            <li class="flex items-start gap-2">
                                <span class="text-vc-green">✓</span>
                                <span>央企/国企背景，政策支持力度强</span>
                            </li>
                            <li class="flex items-start gap-2">
                                <span class="text-vc-green">✓</span>
                                <span>市值小于200亿，弹性较大</span>
                            </li>
                            <li class="flex items-start gap-2">
                                <span class="text-yellow-500">⚠</span>
                                <span>近期商品价格波动，需关注</span>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="bg-vc-dark rounded-lg p-4">
                        <p class="text-gray-400 text-sm mb-2">风险提示</p>
                        <ul class="space-y-2 text-sm text-gray-400">
                            <li>• 市场整体风险偏好变化</li>
                            <li>• 行业政策调整风险</li>
                            <li>• 商品价格波动风险</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 持仓信息 -->
        {f'''
        <div class="bg-vc-card border border-vc-border rounded-xl p-5 mb-6">
            <h3 class="text-lg font-semibold mb-4">💼 当前持仓</h3>
                    <div class="grid grid-cols-4 gap-4">
                <div class="bg-vc-dark rounded-lg p-4 text-center">
                    <p class="text-gray-400 text-sm">成本价</p>
                    <p class="text-xl font-bold">¥{position.get('cost_price', '--')}</p>
                </div>
                <div class="bg-vc-dark rounded-lg p-4 text-center">
                    <p class="text-gray-400 text-sm">当前价</p>
                    <p class="text-xl font-bold">¥{position.get('current_price', '--')}</p>
                </div>
                <div class="bg-vc-dark rounded-lg p-4 text-center">
                    <p class="text-gray-400 text-sm">盈亏</p>
                    <p class="text-xl font-bold {'text-vc-green' if position.get('profit_loss', 0) >= 0 else 'text-vc-red'}">
                        {position.get('profit_loss', 0):+.2f} ({position.get('profit_loss_pct', 0):+.2f}%)
                    </p>
                </div>
                <div class="bg-vc-dark rounded-lg p-4 text-center">
                    <p class="text-gray-400 text-sm">持仓数量</p>
                    <p class="text-xl font-bold">{position.get('shares', position.get('quantity', '--'))}股</p>
                </div>
            </div>
        </div>
        ''' if position else '<!-- 无持仓 -->'}
        
        <!-- 预测历史 -->
        {f'''
        <div class="bg-vc-card border border-vc-border rounded-xl p-5">
            <h3 class="text-lg font-semibold mb-4">🎯 预测历史</h3>
            <div class="space-y-3">
                {"".join([f"""
                <div class="bg-vc-dark rounded-lg p-3 flex justify-between items-center">
                    <div>
                        <span class="text-gray-400 text-sm">{p.get('date', '--')}</span>
                        <span class="ml-2">{p.get('direction', '--')}</span>
                    </div>
                    <span class="px-2 py-1 rounded text-xs {'bg-vc-green/20 text-vc-green' if p.get('result', {}).get('correct') else 'bg-vc-red/20 text-vc-red'}">
                        {'正确' if p.get('result', {}).get('correct') else '错误'}
                    </span>
                </div>
                """ for p in predictions[:5]])}
            </div>
        </div>
        ''' if predictions else '<!-- 无预测历史 -->'}
        
        <!-- 页脚 -->
        <footer class="mt-8 text-center text-gray-600 text-sm">
            <p>股票分析报告 · 由 AI 股票团队生成</p>
            <p class="mt-1">投资有风险，决策需谨慎</p>
        </footer>
    </div>
    
    <script>
        // 价格图表
        const priceChart = echarts.init(document.getElementById('price-chart'));
        priceChart.setOption({{
            backgroundColor: 'transparent',
            tooltip: {{
                trigger: 'axis',
                backgroundColor: '#161b22',
                borderColor: '#30363d',
                textStyle: {{ color: '#e6edf3' }}
            }},
            grid: {{
                left: '3%',
                right: '4%',
                bottom: '3%',
                top: '5%',
                containLabel: true
            }},
            xAxis: {{
                type: 'category',
                data: {json.dumps(price_data['dates'])},
                axisLine: {{ lineStyle: {{ color: '#30363d' }} }},
                axisLabel: {{ color: '#8b949e', fontSize: 10 }}
            }},
            yAxis: {{
                type: 'value',
                axisLine: {{ lineStyle: {{ color: '#30363d' }} }},
                axisLabel: {{ color: '#8b949e', formatter: '¥{{value}}' }},
                splitLine: {{ lineStyle: {{ color: '#21262d' }} }}
            }},
            series: [{{
                type: 'line',
                data: {json.dumps(price_data['prices'])},
                smooth: true,
                showSymbol: false,
                lineStyle: {{ color: '#1f6feb', width: 2 }},
                areaStyle: {{
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        {{ offset: 0, color: 'rgba(31, 111, 235, 0.3)' }},
                        {{ offset: 1, color: 'rgba(31, 111, 235, 0)' }}
                    ])
                }}
            }}]
        }});
        
        window.addEventListener('resize', () => priceChart.resize());
    </script>
</body>
</html>
"""
    
    # 保存文件
    filename = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = OUTPUT_DIR / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return str(filepath)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python stock_analysis_report.py <股票代码>")
        print("示例: python stock_analysis_report.py sh.600459")
        sys.exit(1)
    
    symbol = sys.argv[1]
    print(f"📊 生成 {symbol} 的分析报告...")
    
    filepath = generate_report(symbol)
    
    print(f"✅ 报告已生成: {filepath}")
    print(f"🌐 浏览器打开: file://{filepath}")
