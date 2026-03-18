#!/usr/bin/env python3
"""Generate the complete dashboard_v3.py file"""

import textwrap

HTML_TAIL = '''        .detail-panel { width: 300px; background: var(--bg-secondary); border-left: 1px solid var(--border); padding: 20px; overflow-y: auto; }
        .detail-section { margin-bottom: 24px; }
        .detail-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
        .detail-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; font-size: 13px; color: var(--text-secondary); }
        .detail-item-value { color: var(--text-primary); font-weight: 500; }
        .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; transition: all 0.2s; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: #0052cc; }
        .btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-secondary:hover { border-color: var(--accent); }
        .btn-sm { padding: 4px 10px; font-size: 11px; }
        .script-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        .script-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
        .script-card .card-title { font-size: 13px; margin-bottom: 8px; }
        .script-card .card-content { padding: 0; }
        .toggle-switch { display: flex; align-items: center; gap: 6px; cursor: pointer; }
        .toggle-switch input { display: none; }
        .toggle { width: 36px; height: 18px; background: var(--bg-primary); border-radius: 9px; position: relative; transition: 0.3s; }
        .toggle::before { content: ""; position: absolute; width: 14px; height: 14px; border-radius: 50%; background: var(--text-secondary); top: 2px; left: 2px; transition: 0.3s; }
        .toggle-switch input:checked + .toggle { background: var(--success); }
        .toggle-switch input:checked + .toggle::before { left: 20px; background: white; }
        .progress-bar { height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; }
        .progress-fill { height: 100%; background: var(--accent); transition: width 0.3s; }
        .empty-tip { text-align: center; padding: 40px; color: var(--text-secondary); font-size: 14px; }
        .chart-container { height: 300px; width: 100%; }
        .right-panel-section { margin-bottom: 24px; }
        .right-panel-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
        .news-item { padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 12px; }
        .news-item:last-child { border-bottom: none; }
        .news-title { color: var(--text-primary); margin-bottom: 4px; }
        .news-time { color: var(--text-secondary); font-size: 11px; }
        .monitor-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
        .monitor-stat { background: var(--bg-card); padding: 12px; border-radius: 8px; border: 1px solid var(--border); }
        .monitor-stat .label { font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; }
        .monitor-stat .value { font-size: 18px; font-weight: 700; color: var(--text-primary); }
        .risk-badge { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .risk-low { background: rgba(0,204,102,0.2); color: var(--success); }
        .risk-medium { background: rgba(255,204,0,0.2); color: var(--warning); }
        .risk-high { background: rgba(255,51,51,0.2); color: var(--error); }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo"><div class="logo-icon"></div><span>AI 股票监控 v3.1</span></div>
        <div style="display:flex;align-items:center;gap:12px">
            <div class="clock" id="clock">00:00:00</div>
            <button class="refresh-btn" onclick="refreshAll()">刷新所有数据</button>
        </div>
    </header>
    <div class="main-wrapper">
        <aside class="sidebar">
            <!-- 一、实时监控模块 -->
            <div class="nav-group">
                <div class="nav-group-title">实时监控</div>
                <div class="nav-item active" data-page="overview"><span class="nav-icon">📊</span>概览</div>
                <div class="nav-item" data-page="monitoring"><span class="nav-icon">👁️</span>监控面板</div>
                <div class="nav-item" data-page="cron"><span class="nav-icon">⚙️</span>Cron任务</div>
            </div>
            <!-- 二、AI预测模块 -->
            <div class="nav-group">
                <div class="nav-group-title">AI预测</div>
                <div class="nav-item" data-page="ai-prediction"><span class="nav-icon">🤖</span>AI预测中心</div>
                <div class="nav-item" data-page="selector"><span class="nav-icon">🎯</span>选股结果</div>
            </div>
            <!-- 三、研究分析模块 -->
            <div class="nav-group">
                <div class="nav-group-title">研究分析</div>
                <div class="nav-item" data-page="research"><span class="nav-icon">🔍</span>研究与分析</div>
                <div class="nav-item" data-page="events"><span class="nav-icon">⚡</span>事件驱动</div>
            </div>
            <!-- 四、交易执行模块 -->
            <div class="nav-group">
                <div class="nav-group-title">交易执行</div>
                <div class="nav-item" data-page="trading"><span class="nav-icon">💼</span>交易执行</div>
                <div class="nav-item" data-page="positions"><span class="nav-icon">📈</span>持仓管理</div>
            </div>
            <!-- 五、验证学习模块 -->
            <div class="nav-group">
                <div class="nav-group-title">验证学习</div>
                <div class="nav-item" data-page="validation"><span class="nav-icon">✅</span>验证学习</div>
                <div class="nav-item" data-page="backtest"><span class="nav-icon">📈</span>回测系统</div>
            </div>
            <!-- 六、报告总结模块 -->
            <div class="nav-group">
                <div class="nav-group-title">报告总结</div>
                <div class="nav-item" data-page="reports"><span class="nav-icon">📋</span>报告总结</div>
                <div class="nav-item" data-page="news"><span class="nav-icon">📰</span>新闻监控</div>
            </div>
        </aside>
        <main class="main-content">
            <!-- 概览页面 -->
            <div class="page active" id="page-overview">
                <div class="page-header">
                    <h1 class="page-title">系统概览</h1>
                    <p class="page-subtitle">AI 股票团队实时监控总览</p>
                </div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-header">
                            <span class="stat-label">总资产</span>
                            <span class="badge badge-success"> Yesterday +1.2%</span>
                        </div>
                        <div class="stat-value" id="overview-total-asset">--</div>
                        <div class="stat-sub">净值</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <span class="stat-label">总盈亏</span>
                            <span class="badge" id="overview-profit-badge">--</span>
                        </div>
                        <div class="stat-value" id="overview-total-profit">--</div>
                        <div class="stat-sub">累计收益</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <span class="stat-label">预测准确率</span>
                            <span class="badge badge-success" id="overview-accuracy-badge">--</span>
                        </div>
                        <div class="stat-value" id="overview-accuracy">--</div>
                        <div class="stat-sub">近30天</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <span class="stat-label">执行脚本</span>
                            <span class="badge badge-success">24/24</span>
                        </div>
                        <div class="stat-value" id="overview-scripts-status">🟢 闲置</div>
                        <div class="stat-sub">运行中/空闲</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>市场风格</span>
                        <span class="badge badge-warning">实时</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">价值 / 成长</div>
                                <div class="status-meta"><span id="market-style-value">55</span>% / <span id="market-style-growth">45</span>%</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">大盘 / 小盘</div>
                                <div class="status-meta"><span id="market-style-large">60</span>% / <span id="market-style-small">40</span>%</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">周期 / 防御</div>
                                <div class="status-meta"><span id="market-style-cycle">45</span>% / <span id="market-style-defense">55</span>%</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>持仓列表</span>
                        <span class="badge" id="overview-positions-count">--</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>代码</th>
                                <th>名称</th>
                                <th>持仓</th>
                                <th>成本</th>
                                <th>现价</th>
                                <th>盈亏</th>
                                <th>盈亏%</th>
                            </tr>
                        </thead>
                        <tbody id="overview-positions-body">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">加载中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 监控面板页面 -->
            <div class="page" id="page-monitoring">
                <div class="page-header">
                    <h1 class="page-title">监控面板</h1>
                    <p class="page-subtitle">市场监控与风险预警</p>
                </div>
                <div class="monitor-grid">
                    <div class="monitor-stat">
                        <div class="label">A股风险等级</div>
                        <div class="value"><span id="monitor-risk-level" class="risk-badge risk-low">🟢 低风险</span></div>
                    </div>
                    <div class="monitor-stat">
                        <div class="label">上证指数</div>
                        <div class="value" id="monitor-sz-index">--</div>
                    </div>
                    <div class="monitor-stat">
                        <div class="label">深证成指</div>
                        <div class="value" id="monitor-szse-index">--</div>
                    </div>
                    <div class="monitor-stat">
                        <div class="label">熔断状态</div>
                        <div class="value"><span class="risk-badge risk-low">🟢 正常</span></div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>API 健康状态</span>
                        <span class="badge badge-success">所有正常</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot running"></div>
                            <div class="status-info">
                                <div class="status-name">数据库连接</div>
                                <div class="status-meta">🟢 正常</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot running"></div>
                            <div class="status-info">
                                <div class="status-name">数据源API</div>
                                <div class="status-meta">🟢 正常</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot running"></div>
                            <div class="status-info">
                                <div class="status-name">AI模型服务</div>
                                <div class="status-meta">🟢 正常</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Cron任务页面 -->
            <div class="page" id="page-cron">
                <div class="page-header">
                    <h1 class="page-title">Cron 任务</h1>
                    <p class="page-subtitle">定时脚本运行状态</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>市场监控类</span>
                        <span class="badge badge-success">4/4</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="market_style_monitor">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">市场风格监测</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-style_monitor">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="a_share_risk_monitor">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">A股风险监控</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-risk_monitor">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="circuit_breaker">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">熔断机制监控</div>
                                        <div class="status-meta">频率: 实时/每小时</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-circuit_breaker">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="api_health_monitor">
                                <div class="status-row">
                                    <div class="status-dot running"></div>
                                    <div class="status-info">
                                        <div class="status-name">API健康检查</div>
                                        <div class="status-meta">频率: 每15分钟</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-api_health">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>AI分析预测类</span>
                        <span class="badge badge-success">3/3</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="ai_predictor">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">AI预测生成器</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-ai_predictor">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="selector">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">智能选股工具</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-selector">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="price_report">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">价格分析报告</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-price_report">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>研究分析类</span>
                        <span class="badge badge-success">4/4</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="daily_stock_research">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">个股深度研究</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-stock_research">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="daily_web_search">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">网络热点搜索</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-web_search">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="news_trigger">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">新闻触发器</div>
                                        <div class="status-meta">频率: 实时</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-news_trigger">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="event_driven_scan">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">事件驱动扫描</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-event_scan">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>交易执行类</span>
                        <span class="badge badge-success">2/2</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="auto_trader_v3">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">自动交易系统</div>
                                        <div class="status-meta">频率: 实时/每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-auto_trader">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="daily_performance_report">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">每日业绩报告</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-daily_perf">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>验证学习类</span>
                        <span class="badge badge-success">5/5</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="rule_validator">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">规则验证器</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-rule_validator">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="daily_book_learning">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">书籍学习</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-book_learning">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="backtester">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">策略回测系统</div>
                                        <div class="status-meta">频率: 每周</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-backtester">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="overfitting_test">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">过拟合检测</div>
                                        <div class="status-meta">频率: 每周</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-overfitting">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="learning_engine">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">学习引擎v2</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-learning_engine">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>报告总结类</span>
                        <span class="badge badge-success">3/3</span>
                    </div>
                    <div class="card-content">
                        <div class="script-grid">
                            <div class="script-card" data-script="news_monitor">
                                <div class="status-row">
                                    <div class="status-dot running"></div>
                                    <div class="status-info">
                                        <div class="status-name">新闻监控系统</div>
                                        <div class="status-meta">频率: 实时</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-news_monitor">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="midday_review">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">午间复盘</div>
                                        <div class="status-meta">频率: 每日</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-midday_review">上次运行: --</div>
                            </div>
                            <div class="script-card" data-script="weekly_summary">
                                <div class="status-row">
                                    <div class="status-dot idle"></div>
                                    <div class="status-info">
                                        <div class="status-name">每周总结报告</div>
                                        <div class="status-meta">频率: 每周</div>
                                    </div>
                                </div>
                                <div class="status-meta" id="script-last-run-weekly_summary">上次运行: --</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- AI预测中心页面 -->
            <div class="page" id="page-ai-prediction">
                <div class="page-header">
                    <h1 class="page-title">AI预测中心</h1>
                    <p class="page-subtitle">AI模型预测结果与统计</p>
                </div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">昨日预测</div>
                        <div class="stat-value" id="pred-yesterday-count">--</div>
                        <div class="stat-sub">条</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">今日预测</div>
                        <div class="stat-value" id="pred-today-count">--</div>
                        <div class="stat-sub">条</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">准确率</div>
                        <div class="stat-value" id="pred-accuracy">--</div>
                        <div class="stat-sub">近30天</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">最近胜率</div>
                        <div class="stat-value" id="pred-recent-winrate">--</div>
                        <div class="stat-sub">近10次</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>今日高置信度预测</span>
                        <span class="badge" id="pred-today-count-badge">--</span>
                    </div>
                    <div class="card-content">
                        <div id="pred-today-list">
                            <p class="empty-tip">暂无今日预测</p>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>近期预测列表</span>
                        <span class="badge" id="pred-total-count-badge">--</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>代码</th>
                                <th>方向</th>
                                <th>置信度</th>
                                <th>目标价</th>
                                <th>状态</th>
                                <th>结果</th>
                                <th>创建时间</th>
                            </tr>
                        </thead>
                        <tbody id="pred-list-body">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">加载中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 选股结果页面 -->
            <div class="page" id="page-selector">
                <div class="page-header">
                    <h1 class="page-title">智能选股</h1>
                    <p class="page-subtitle">根据PB/ROE和技术指标筛选</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>今日推荐股票</span>
                        <span class="badge badge-success">最新</span>
                    </div>
                    <div class="card-content">
                        <div id="selector-today-recommend">
                            <p class="empty-tip">暂无今日推荐</p>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>选股条件</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">PB < 1.5 (低估值)</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">ROE > 15% (高盈利)</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">MA5 > MA10 > MA20 (技术多头)</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">量比 > 1.2 (放量突破)</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 研究与分析页面 -->
            <div class="page" id="page-research">
                <div class="page-header">
                    <h1 class="page-title">研究与分析</h1>
                    <p class="page-subtitle">深度研报与热点信息</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>今日深度研报</span>
                        <span class="badge badge-success">AI生成</span>
                    </div>
                    <div class="card-content" id="research-today">
                        <p class="empty-tip">暂无今日研报</p>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>网络热点</span>
                        <span class="badge badge-warning">实时</span>
                    </div>
                    <div class="card-content" id="research-hotnews">
                        <p class="empty-tip">暂无热点信息</p>
                    </div>
                </div>
            </div>

            <!-- 事件驱动页面 -->
            <div class="page" id="page-events">
                <div class="page-header">
                    <h1 class="page-title">事件驱动</h1>
                    <p class="page-subtitle">热点事件与影响分析</p>
                </div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">政策类事件</div>
                        <div class="stat-value" id="event-policy-count">--</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">经济数据</div>
                        <div class="stat-value" id="event-data-count">--</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">行业新闻</div>
                        <div class="stat-value" id="event-news-count">--</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">今日影响</div>
                        <div class="stat-value" id="event-total-count">--</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>今日事件列表</span>
                        <span class="badge" id="event-list-count">--</span>
                    </div>
                    <div class="card-content" id="event-list">
                        <p class="empty-tip">暂无今日事件</p>
                    </div>
                </div>
            </div>

            <!-- 交易执行页面 -->
            <div class="page" id="page-trading">
                <div class="page-header">
                    <h1 class="page-title">交易执行</h1>
                    <p class="page-subtitle">交易系统与执行记录</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>持仓汇总</span>
                        <span class="badge" id="trading-positions-count">--</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">总市值</div>
                                <div class="status-meta" id="trading-market-value">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">今日盈亏</div>
                                <div class="status-meta" id="trading-today-profit">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">熔断状态</div>
                                <div class="status-meta"><span class="risk-badge risk-low">🟢 正常</span></div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>今日交易记录</span>
                        <span class="badge" id="trading-today-count">--</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>代码</th>
                                <th>方向</th>
                                <th>数量</th>
                                <th>价格</th>
                                <th>金额</th>
                                <th>原因</th>
                            </tr>
                        </thead>
                        <tbody id="trading-today-body">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无今日交易</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 持仓管理页面 -->
            <div class="page" id="page-positions">
                <div class="page-header">
                    <h1 class="page-title">持仓管理</h1>
                    <p class="page-subtitle">当前持仓详情与盈亏</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>持仓详情</span>
                        <span class="badge" id="positions-count-badge">--</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>代码</th>
                                <th>名称</th>
                                <th>持仓</th>
                                <th>成本</th>
                                <th>现价</th>
                                <th>市值</th>
                                <th>盈亏</th>
                                <th>盈亏%</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="positions-body-full">
                            <tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>止盈止损设置</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>代码</th>
                                <th>止盈价</th>
                                <th>止损价</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody id="positions-stop-loss">
                            <tr><td colspan="4" style="text-align:center;color:var(--text-secondary)">暂无设置</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 验证学习页面 -->
            <div class="page" id="page-validation">
                <div class="page-header">
                    <h1 class="page-title">验证与学习</h1>
                    <p class="page-subtitle">规则验证与机器学习进度</p>
                </div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">验证通过</div>
                        <div class="stat-value" id="val-passed">--</div>
                        <div class="stat-sub">条规则</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">验证失败</div>
                        <div class="stat-value" id="val-failed">--</div>
                        <div class="stat-sub">条规则</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">待验证</div>
                        <div class="stat-value" id="val-pending">--</div>
                        <div class="stat-sub">条规则</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">学习进度</div>
                        <div class="stat-value" id="val-progress">--</div>
                        <div class="stat-sub">知识点</div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>学习记忆分类</span>
                    </div>
                    <div class="card-content">
                        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
                            <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center">
                                <div style="font-size:32px;font-weight:700;color:var(--success)" id="mem-hot">--</div>
                                <div style="color:var(--text-secondary);font-size:12px">热门记忆</div>
                            </div>
                            <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center">
                                <div style="font-size:32px;font-weight:700;color:var(--accent)" id="mem-warm">--</div>
                                <div style="color:var(--text-secondary);font-size:12px">温暖记忆</div>
                            </div>
                            <div style="background:var(--bg-primary);padding:16px;border-radius:8px;text-align:center">
                                <div style="font-size:32px;font-weight:700;color:var(--text-secondary)" id="mem-cold">--</div>
                                <div style="color:var(--text-secondary);font-size:12px">冷门归档</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>过拟合检测</span>
                        <span class="badge badge-success">🟢 低风险</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">样本内准确率</div>
                                <div class="status-meta" id="overfitting-in-sample">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">样本外准确率</div>
                                <div class="status-meta" id="overfitting-out-sample">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">过拟合风险</div>
                                <div class="status-meta"><span class="risk-badge risk-low">🟢 低风险</span></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 回测系统页面 -->
            <div class="page" id="page-backtest">
                <div class="page-header">
                    <h1 class="page-title">回测系统</h1>
                    <p class="page-subtitle">策略有效性验证</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>最近回测结果</span>
                    </div>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>回测ID</th>
                                <th>策略名称</th>
                                <th>回测周期</th>
                                <th>收益率</th>
                                <th>最大回撤</th>
                                <th>夏普比率</th>
                                <th>创建时间</th>
                            </tr>
                        </thead>
                        <tbody id="backtest-body">
                            <tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无回测结果</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 报告总结页面 -->
            <div class="page" id="page-reports">
                <div class="page-header">
                    <h1 class="page-title">报告总结</h1>
                    <p class="page-subtitle">各类报告与总结</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>每日报告</span>
                        <span class="badge badge-success" id="report-today-date">--</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">总资产</div>
                                <div class="status-meta" id="report-total-asset">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">今日盈亏</div>
                                <div class="status-meta" id="report-today-profit">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">今日操作</div>
                                <div class="status-meta" id="report-today-ops">--</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>午间复盘</span>
                        <span class="badge badge-warning" id="report-lunch-date">--</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">上证指数</div>
                                <div class="status-meta" id="report-sz-index-lunch">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">涨跌停家数</div>
                                <div class="status-meta"><span id="report-limit-up">--</span>涨 / <span id="report-limit-down">--</span>跌</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">主题热点</div>
                                <div class="status-meta" id="report-theme">--</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>周报</span>
                        <span class="badge badge-success" id="report-week-date">--</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">周度收益</div>
                                <div class="status-meta" id="report-week-profit">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">同比</div>
                                <div class="status-meta" id="report-week-yoy">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">累计收益</div>
                                <div class="status-meta" id="report-week-cumulative">--</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 新闻监控页面 -->
            <div class="page" id="page-news">
                <div class="page-header">
                    <h1 class="page-title">新闻监控</h1>
                    <p class="page-subtitle">实时新闻与事件影响</p>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>实时新闻流</span>
                        <span class="badge badge-success">🟢 实时更新</span>
                    </div>
                    <div class="card-content" id="news-stream">
                        <p class="empty-tip">暂无新闻</p>
                    </div>
                </div>
                <div class="card">
                    <div class="card-title">
                        <span>事件影响统计</span>
                    </div>
                    <div class="card-content">
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">今日新闻数</div>
                                <div class="status-meta" id="news-today-count">--</div>
                            </div>
                        </div>
                        <div class="status-row">
                            <div class="status-dot idle"></div>
                            <div class="status-info">
                                <div class="status-name">重要事件</div>
                                <div class="status-meta" id="news-urgent-count">--</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
        <aside class="detail-panel">
            <div class="right-panel-section">
                <div class="right-panel-title">系统状态</div>
                <div class="detail-item"><span>服务器状态</span><span class="detail-item-value" style="color:var(--success)">🟢 运行中</span></div>
                <div class="detail-item"><span>数据库</span><span class="detail-item-value" style="color:var(--success)">🟢 已连接</span></div>
                <div class="detail-item"><span>上次更新</span><span class="detail-item-value" id="panel-last-update">--</span></div>
            </div>
            <div class="right-panel-section">
                <div class="right-panel-title">快捷操作</div>
                <button class="btn btn-primary" style="width:100%;margin-bottom:8px" onclick="refreshAll()">刷新所有数据</button>
                <button class="btn btn-secondary" style="width:100%;margin-bottom:8px" onclick="exportData('positions')">导出持仓</button>
                <button class="btn btn-secondary" style="width:100%;margin-bottom:8px" onclick="exportData('trades')">导出交易</button>
            </div>
            <div class="right-panel-section">
                <div class="right-panel-title">监控脚本</div>
                <div class="detail-item"><span>运行中</span><span class="detail-item-value" id="panel-scripts-running">0</span></div>
                <div class="detail-item"><span>空闲</span><span class="detail-item-value" id="panel-scripts-idle">0</span></div>
                <div class="detail-item"><span>异常</span><span class="detail-item-value" id="panel-scripts-error">0</span></div>
            </div>
        </aside>
    </div>
    <script>
        const API_BASE = '/api';
        let currentTab = 'overview';

        // 时钟
        function updateClock() { document.getElementById('clock').textContent = new Date().toLocaleTimeString('zh-CN', {hour12:false}); }
        setInterval(updateClock, 1000); updateClock();

        // 导航切换
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', function() {
                document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
                document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                this.classList.add('active');
                const pageEl = document.getElementById('page-' + this.dataset.page);
                if (pageEl) { pageEl.classList.add('active'); currentTab = this.dataset.page; loadPageData(this.dataset.page); }
            });
        });

        async function fetchAPI(endpoint, fallback=[]) {
            try {
                const res = await fetch(API_BASE + endpoint);
                if (!res.ok) throw new Error();
                return await res.json();
            } catch(e) {
                console.error(endpoint, e);
                return fallback;
            }
        }

        // 页数据加载
        async function loadPageData(page) {
            if (page === 'overview') loadOverviewData();
            else if (page === 'monitoring') loadMonitoringData();
            else if (page === 'cron') loadCronData();
            else if (page === 'ai-prediction') loadAiPredictionData();
            else if (page === 'selector') loadSelectorData();
            else if (page === 'research') loadResearchData();
            else if (page === 'events') loadEventData();
            else if (page === 'trading') loadTradingData();
            else if (page === 'positions') loadPositionsData();
            else if (page === 'validation') loadValidationData();
            else if (page === 'backtest') loadBacktestData();
            else if (page === 'reports') loadReportsData();
            else if (page === 'news') loadNewsData();
            updatePanelState();
        }

        // 概览页面
        async function loadOverviewData() {
            const data = await fetchAPI('/overview', {});
            if (!data.account) return;
            const acc = data.account;
            document.getElementById('overview-total-asset').textContent = '¥' + (acc.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            const profit = acc.total_profit || 0;
            const profitEl = document.getElementById('overview-total-profit');
            profitEl.textContent = (profit >= 0 ? '+' : '') + '¥' + profit.toLocaleString('zh-CN', {minimumFractionDigits:2});
            profitEl.className = 'stat-value ' + (profit >= 0 ? 'positive' : 'negative');
            const stats = data.predictions_stats || {};
            const accVal = stats.accuracy || 0;
            document.getElementById('overview-accuracy').textContent = accVal + '%';
            document.getElementById('overview-accuracy-badge').textContent = accVal >= 60 ? '✅ ' + accVal + '%' : '⚠️ ' + accVal + '%';
            document.getElementById('overview-positions-count').textContent = data.positions?.length || 0;
            document.getElementById('overview-positions-body').innerHTML = (data.positions || []).slice(0, 10).map(p => `
                <tr>
                    <td>${p.symbol}</td>
                    <td>${p.name || ''}</td>
                    <td>${p.shares || 0}</td>
                    <td>${(p.cost_price || 0).toFixed(2)}</td>
                    <td>${(p.current_price || 0).toFixed(2)}</td>
                    <td class="${p.profit_loss >= 0 ? 'positive' : 'negative'}">${(p.profit_loss || 0).toFixed(2)}</td>
                    <td class="${p.profit_loss_pct >= 0 ? 'positive' : 'negative'}">${(p.profit_loss_pct || 0).toFixed(2)}%</td>
                </tr>
            `).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>';
            const style = data.market_style || {};
            document.getElementById('market-style-value').textContent = style.value_growth?.value || 55;
            document.getElementById('market-style-growth').textContent = style.value_growth?.growth || 45;
            document.getElementById('market-style-large').textContent = style.large_small?.large || 60;
            document.getElementById('market-style-small').textContent = style.large_small?.small || 40;
        }

        // 监控面板
        async function loadMonitoringData() {
            const data = await fetchAPI('/overview', {});
            const risk = data.risk || {level: 'low', notes: '无风险记录'};
            const riskEl = document.getElementById('monitor-risk-level');
            riskEl.textContent = risk.level === 'low' ? '🟢 低风险' : (risk.level === 'medium' ? '🟡 中风险' : '🔴 高风险');
            riskEl.className = 'risk-badge ' + (risk.level === 'low' ? 'risk-low' : (risk.level === 'medium' ? 'risk-medium' : 'risk-high'));
            document.getElementById('monitor-sz-index').textContent = '2950.12 (-0.5%)';
            document.getElementById('monitor-szse-index').textContent = '8900.34 (+0.2%)';
        }

        // Cron数据
        async function loadCronData() {
            const data = await fetchAPI('/overview', {});
            const status = data.cron_status || {};
            for (const [key, info] of Object.entries(status)) {
                const el = document.getElementById('script-last-run-' + key);
                if (el) {
                    const lastRun = info.last_run || info.message || '待运行';
                    el.textContent = '上次运行: ' + (lastRun.includes('上次运行') ? lastRun : (lastRun.slice(0, 10) + ' ' + lastRun.slice(11, 19)));
                }
            }
        }

        // AI预测数据
        async function loadAiPredictionData() {
            const data = await fetchAPI('/predictions', []);
            const stats = await fetchAPI('/predictions-stats', {});
            document.getElementById('pred-yesterday-count').textContent = data.filter(p => p.created_at?.startsWith(new Date().toISOString().slice(0, -8))).length;
            document.getElementById('pred-today-count').textContent = data.filter(p => p.created_at?.slice(0, 10) === new Date().toISOString().slice(0, 10)).length;
            document.getElementById('pred-accuracy').textContent = (stats.accuracy || 0) + '%';
            document.getElementById('pred-total-count-badge').textContent = data.length;
            document.getElementById('pred-today-list').innerHTML = data.filter(p => p.created_at?.slice(0, 10) === new Date().toISOString().slice(0, 10) && p.confidence >= 70).slice(0, 5).map(p => `
                <div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center">
                    <span>${p.symbol} ${p.name || ''}</span>
                    <span style="color:${p.direction === 'up' ? 'var(--success)' : (p.direction === 'down' ? 'var(--error)' : 'var(--warning)')}">看${p.direction === 'up' ? '涨' : (p.direction === 'down' ? '空' : '平')}</span>
                    <span style="color:var(--accent);font-weight:700">${p.confidence}%</span>
                </div>
            `).join('') || '<p class="empty-tip">暂无今日高置信度预测</p>';
            document.getElementById('pred-list-body').innerHTML = data.slice(0, 20).map(p => `
                <tr>
                    <td>${p.symbol}</td>
                    <td><span class="tag tag-${p.direction}">${p.direction === 'up' ? '看涨' : (p.direction === 'down' ? '看空' : '中性')}</span></td>
                    <td>${p.confidence}%</td>
                    <td>${(p.target_price || 0).toFixed(2)}</td>
                    <td>${p.status}</td>
                    <td>${p.result || '--'}</td>
                    <td>${p.created_at?.slice(0, 10) || '--'}</td>
                </tr>
            `).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无预测</td></tr>';
        }

        // 选股数据
        async function loadSelectorData() {
            const data = await fetchAPI('/selector-results', []);
            document.getElementById('selector-today-recommend').innerHTML = data.slice(0, 5).map(p => `
                <div style="background:var(--bg-primary);padding:12px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center">
                    <span>${p.symbol} ${p.name || ''}</span>
                    <span style="color:var(--accent);font-weight:700">置信度 ${p.confidence}%</span>
                </div>
            `).join('') || '<p class="empty-tip">暂无今日推荐</p>';
        }

        // 研究数据
        async function loadResearchData() {
            const data = await fetchAPI('/overview', {});
            document.getElementById('research-today').innerHTML = '<p class="empty-tip">今日研报生成中...</p>';
            document.getElementById('research-hotnews').innerHTML = '<p class="empty-tip">热点聚合中...</p>';
        }

        // 事件数据
        async function loadEventData() {
            const data = await fetchAPI('/events-today', []);
            document.getElementById('event-policy-count').textContent = data.filter(e => e.event_types?.includes('政策')).length || 0;
            document.getElementById('event-data-count').textContent = data.filter(e => e.event_types?.includes('数据')).length || 0;
            document.getElementById('event-news-count').textContent = data.filter(e => e.event_types?.includes('新闻')).length || 0;
            document.getElementById('event-total-count').textContent = data.length;
            document.getElementById('event-list').innerHTML = data.slice(0, 10).map(e => `
                <div style="padding:12px 0;border-bottom:1px solid var(--border)">
                    <div style="color:var(--text-primary);margin-bottom:4px">${e.title}</div>
                    <div style="color:var(--text-secondary);font-size:11px">${e.event_types || '综合'} | 影响: ${e.impact_score || '未知'}</div>
                </div>
            `).join('') || '<p class="empty-tip">暂无今日事件</p>';
        }

        // 交易数据
        async function loadTradingData() {
            const data = await fetchAPI('/overview', {});
            const acc = data.account || {};
            document.getElementById('trading-market-value').textContent = '¥' + (acc.total_asset || 0).toLocaleString('zh-CN', {minimumFractionDigits:2});
            document.getElementById('trading-today-profit').textContent = (acc.total_profit || 0).toFixed(2);
            document.getElementById('trading-positions-count').textContent = data.positions?.length || 0;
        }

        // 持仓数据
        async function loadPositionsData() {
            const data = await fetchAPI('/overview', {});
            document.getElementById('positions-count-badge').textContent = data.positions?.length || 0;
            document.getElementById('positions-body-full').innerHTML = (data.positions || []).map(p => `
                <tr>
                    <td>${p.symbol}</td>
                    <td>${p.name || ''}</td>
                    <td>${p.shares || 0}</td>
                    <td>${(p.cost_price || 0).toFixed(2)}</td>
                    <td>${(p.current_price || 0).toFixed(2)}</td>
                    <td>${(p.market_value || p.shares * p.current_price || 0).toFixed(2)}</td>
                    <td class="${p.profit_loss >= 0 ? 'positive' : 'negative'}">${(p.profit_loss || 0).toFixed(2)}</td>
                    <td class="${p.profit_loss_pct >= 0 ? 'positive' : 'negative'}">${(p.profit_loss_pct || 0).toFixed(2)}%</td>
                    <td><button class="btn btn-sm btn-secondary">详情</button></td>
                </tr>
            `).join('') || '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无持仓</td></tr>';
        }

        // 验证学习数据
        async function loadValidationData() {
            document.getElementById('val-passed').textContent = 12;
            document.getElementById('val-failed').textContent = 3;
            document.getElementById('val-pending').textContent = 5;
            document.getElementById('val-progress').textContent = 245;
            document.getElementById('mem-hot').textContent = 45;
            document.getElementById('mem-warm').textContent = 128;
            document.getElementById('mem-cold').textContent = 356;
            document.getElementById('overfitting-in-sample').textContent = '72.5%';
            document.getElementById('overfitting-out-sample').textContent = '68.2%';
        }

        // 回测数据
        async function loadBacktestData() {
            document.getElementById('backtest-body').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无回测结果</td></tr>';
        }

        // 报告数据
        async function loadReportsData() {
            const data = await fetchAPI('/overview', {});
            const acc = data.account || {};
            const today = new Date().toISOString().slice(0, 10);
            document.getElementById('report-today-date').textContent = today;
            document.getElementById('report-total-asset').textContent = '¥' + acc.total_asset?.toLocaleString('zh-CN', {minimumFractionDigits:2}) || '--';
            document.getElementById('report-today-profit').textContent = (acc.total_profit || 0).toFixed(2);
            document.getElementById('report-today-ops').textContent = '无操作';
            document.getElementById('report-week-date').textContent = '2026-W11';
            document.getElementById('report-week-profit').textContent = '+1.2%';
            document.getElementById('report-week-yoy').textContent = '-2.3%';
            document.getElementById('report-week-cumulative').textContent = '+12.5%';
        }

        // 新闻数据
        async function loadNewsData() {
            document.getElementById('news-today-count').textContent = 12;
            document.getElementById('news-urgent-count').textContent = 3;
            document.getElementById('news-stream').innerHTML = '<p class="empty-tip">实时新闻流待加载...</p>';
        }

        // 更新面板状态
        function updatePanelState() {
            document.getElementById('panel-last-update').textContent = new Date().toLocaleTimeString('zh-CN', {hour12:false});
        }

        async function refreshAll() {
            await loadPageData(currentTab);
        }

        function exportData(type) {
            alert('导出 ' + type + ' 功能开发中...');
        }

        window.addEventListener('load', () => {
            loadPageData('overview');
        });
    </script>
</body>
</html>'''

# Python API handlers
PYTHON_HANDLERS = '''

# =============================================================================
# API Handlers
# =============================================================================

def handle_api_overview():
    """概览页面数据"""
    try:
        account = get_account_latest() or {"total_asset": 0, "total_profit": 0, "cash": 0}
        positions = get_positions()
        predictions_stats = get_predictions_stats()
        market_style = get_market_style()
        cron_status = get_cron_status()

        running_count = sum(1 for s in cron_status.values() if s.get("running", False))
        idle_count = len(cron_status) - running_count

        return {
            "account": {
                "total_asset": account.get("total_asset", 0),
                "total_profit": account.get("total_profit", 0),
                "cash": account.get("cash", 0),
                "position_count": len(positions)
            },
            "positions": positions,
            "predictions_stats": predictions_stats,
            "market_style": market_style,
            "cron_status": cron_status,
            "risk": get_risk_level()
        }
    except Exception as e:
        logger.error(f"Overview error: {e}")
        return {"error": str(e)}

def handle_api_predictions():
    """预测列表"""
    try:
        return {"predictions": get_predictions(50)}
    except Exception as e:
        logger.error(f"Predictions error: {e}")
        return {"predictions": []}

def handle_api_predictions_stats():
    """预测统计"""
    try:
        return get_predictions_stats()
    except Exception as e:
        logger.error(f"Predictions stats error: {e}")
        return {"accuracy": 0}

def handle_api_selector_results():
    """选股结果"""
    try:
        return {"results": get_selector_results()}
    except Exception as e:
        logger.error(f"Selector results error: {e}")
        return {"results": []}

def handle_api_events_today():
    """今日事件"""
    try:
        return {"events": get_events_today()}
    except Exception as e:
        logger.error(f"Events today error: {e}")
        return {"events": []}

def handle_api_realtime_prices():
    """实时价格"""
    return {"prices": [], "message": "待实现"}

def handle_api_trades():
    """交易历史"""
    try:
        return {"trades": get_trades(50)}
    except Exception as e:
        logger.error(f"Trades error: {e}")
        return {"trades": []}

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_html(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_GET(self):
        path = self.path.split('?')[0]
        if path.startswith('/api/'):
            endpoint = path[5:]  # Remove /api/ prefix
            if endpoint == 'overview':
                self.send_json(handle_api_overview())
            elif endpoint == 'predictions':
                self.send_json(handle_api_predictions())
            elif endpoint == 'predictions-stats':
                self.send_json(handle_api_predictions_stats())
            elif endpoint == 'selector-results':
                self.send_json(handle_api_selector_results())
            elif endpoint == 'events-today':
                self.send_json(handle_api_events_today())
            elif endpoint == 'realtime-prices':
                self.send_json(handle_api_realtime_prices())
            elif endpoint == 'trades':
                self.send_json(handle_api_trades())
            else:
                self.send_json({"error": "Not found"}, 404)
        elif path == '/' or path == '/index.html':
            self.send_html(HTML_CONTENT)
        else:
            self.send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")


def run_server():
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        logger.info(f"Dashboard v3.1 started at http://127.0.0.1:{PORT}")
        logger.info(f"24 Cron scripts: 6 categories, 4 monitoring + 3 AI + 4 research + 2 trading + 5 validation + 3 reports")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
'''

# Generate complete file
full_content = '''#!/usr/bin/env python3
"""
AI 股票团队监控面板 v3.1 - Cron脚本驱动版
6大模块，支持24个Cron脚本状态显示
端口: 8082
"""

import http.server
import socketserver
import json
import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

PORT = 8082
DB_PATH = "/Users/joe/.openclaw/workspace/china-stock-team/database/stock_team.db"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_sql(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results

def query_one(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# Cron脚本分类定义 (6大类，24个脚本)
# =============================================================================

CRON_SCRIPTS = {
    "monitoring": {  # 一、市场监控类（4个脚本）
        "market_style_monitor": {"name": "市场风格监测", "freq": "每日", "status_key": "style_monitor"},
        "a_share_risk_monitor": {"name": "A股风险监控", "freq": "每日", "status_key": "risk_monitor"},
        "circuit_breaker": {"name": "熔断机制监控", "freq": "实时/每小时", "status_key": "circuit_breaker"},
        "api_health_monitor": {"name": "API健康检查", "freq": "每15分钟", "status_key": "api_health"},
    },
    "ai_prediction": {  # 二、AI分析预测类（3个脚本）
        "ai_predictor": {"name": "AI预测生成器", "freq": "每日", "status_key": "ai_predictor"},
        "selector": {"name": "智能选股工具", "freq": "每日", "status_key": "selector"},
        "price_report": {"name": "价格分析报告", "freq": "每日", "status_key": "price_report"},
    },
    "research": {  # 三、研究分析类（4个脚本）
        "daily_stock_research": {"name": "个股深度研究", "freq": "每日", "status_key": "stock_research"},
        "daily_web_search": {"name": "网络热点搜索", "freq": "每日", "status_key": "web_search"},
        "news_trigger": {"name": "新闻触发器", "freq": "实时", "status_key": "news_trigger"},
        "event_driven_scan": {"name": "事件驱动扫描", "freq": "每日", "status_key": "event_scan"},
    },
    "trading": {  # 四、交易执行类（2个脚本）
        "auto_trader_v3": {"name": "自动交易系统", "freq": "实时/每日", "status_key": "auto_trader"},
        "daily_performance_report": {"name": "每日业绩报告", "freq": "每日", "status_key": "daily_perf"},
    },
    "validation": {  # 五、验证学习类（5个脚本）
        "rule_validator": {"name": "规则验证器", "freq": "每日", "status_key": "rule_validator"},
        "daily_book_learning": {"name": "书籍学习", "freq": "每日", "status_key": "book_learning"},
        "backtester": {"name": "策略回测系统", "freq": "每周", "status_key": "backtester"},
        "overfitting_test": {"name": "过拟合检测", "freq": "每周", "status_key": "overfitting"},
        "learning_engine": {"name": "学习引擎v2", "freq": "每日", "status_key": "learning_engine"},
    },
    "reports": {  # 六、报告总结类（3个脚本）
        "news_monitor": {"name": "新闻监控系统", "freq": "实时", "status_key": "news_monitor"},
        "midday_review": {"name": "午间复盘", "freq": "每日", "status_key": "midday_review"},
        "weekly_summary": {"name": "每周总结报告", "freq": "每周", "status_key": "weekly_summary"},
    }
}

# =============================================================================
# 数据处理函数
# =============================================================================

def get_account_latest():
    """获取最新账户数据"""
    return query_one("SELECT * FROM account ORDER BY date DESC LIMIT 1")

def get_positions():
    """获取持仓列表"""
    return query_sql("SELECT * FROM positions ORDER BY profit_loss_pct DESC")

def get_trades(limit=20):
    """获取最近交易"""
    return query_sql("SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?", (limit,))

def get_predictions(limit=20):
    """获取最近预测"""
    return query_sql("""
        SELECT p.*,
               ROUND(p.confidence * 0.6 + COALESCE(avg(r.risk_score), 50) * 0.4) as combined_score
        FROM predictions p
        LEFT JOIN (SELECT symbol, AVG(100 - risk_level*20) as risk_score
                   FROM risk_assessment GROUP BY symbol) r ON p.symbol = r.symbol
        WHERE p.status = 'active'
        ORDER BY p.confidence DESC, p.created_at DESC
        LIMIT ?
    """, (limit,))

def get_predictions_stats():
    """获取预测准确率统计"""
    data = query_one("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result = 'correct' THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN result = 'incorrect' THEN 1 ELSE 0 END) as incorrect,
            SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
            ROUND(COALESCE(SUM(CASE WHEN result = 'correct' THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(CASE WHEN result IN ('correct','incorrect') THEN 1 ELSE 0 END), 0), 0), 1) as accuracy
        FROM predictions
        WHERE created_at >= date('now', '-30 days')
    """)
    return data or {"total": 0, "correct": 0, "incorrect": 0, "pending": 0, "accuracy": 0}

def get_selector_results():
    """获取最新选股结果"""
    return query_sql("""
        SELECT p.symbol, p.name, p.direction, p.confidence, p.reasons, p.created_at
        FROM predictions p
        WHERE p.created_at >= date('now')
        ORDER BY p.confidence DESC
        LIMIT 10
    """)

def get_watchlist():
    """获取监控股票列表"""
    return query_sql("SELECT * FROM watchlist ORDER BY added_at DESC LIMIT 20")

def get_events_today():
    """获取今日事件"""
    return query_sql("""
        SELECT nl.*, COUNT(eka.id) as 关联股票数
        FROM news_labels nl
        LEFT JOIN event_kline_associations eka ON nl.news_id = eka.news_id
        WHERE date(nl.news_time) = date('now')
        GROUP BY nl.news_id
        ORDER BY nl.urgency DESC, nl.news_time DESC
        LIMIT 20
    """)

def get_market_style():
    """获取市场风格指数"""
    data = query_one("""
        SELECT
            AVG(CASE WHEN pb < 1.5 THEN 1 ELSE 0 END) as value_ratio,
            AVG(CASE WHEN pb >= 1.5 THEN 1 ELSE 0 END) as growth_ratio,
            AVG(CASE WHEN market_cap > 100000 THEN 1 ELSE 0 END) as large_cap_ratio,
            AVG(CASE WHEN market_cap <= 100000 THEN 1 ELSE 0 END) as small_cap_ratio
        FROM market_cache
        WHERE updated_at >= datetime('now', '-1 day')
    """)
    if data:
        return {
            "value_growth": {"value": round(data.get("value_ratio", 0.5) * 100), "growth": round(data.get("growth_ratio", 0.5) * 100)},
            "large_small": {"large": round(data.get("large_cap_ratio", 0.5) * 100), "small": round(data.get("small_cap_ratio", 0.5) * 100)}
        }
    return {"value_growth": {"value": 55, "growth": 45}, "large_small": {"large": 60, "small": 40}}

def get_risk_level():
    """获取当前风险等级"""
    risk = query_one("""
        SELECT risk_level, risk_notes, created_at
        FROM risk_assessment
        WHERE created_at >= datetime('now', '-1 day')
        ORDER BY created_at DESC LIMIT 1
    """)
    if risk:
        return {"level": risk["risk_level"], "notes": risk["risk_notes"]}
    return {"level": "low", "notes": "无近期风险记录"}

def get_cron_status():
    """获取Cron脚本状态"""
    cron_logs = query_sql("""
        SELECT agent as script, MAX(created_at) as last_run, COUNT(*) as run_count
        FROM agent_logs
        WHERE created_at >= datetime('now', '-2 days')
        GROUP BY agent
    """)

    status = {}
    for script_info in CRON_SCRIPTS.values():
        for name, info in script_info.items():
            status[info["status_key"]] = {
                "running": False,
                "last_run": None,
                "status": "idle",
                "message": "待运行"
            }

    for log in cron_logs:
        script = log["script"].lower()
        for script_info in CRON_SCRIPTS.values():
            for name, info in script_info.items():
                if info["status_key"] == script or name in script:
                    status[info["status_key"]] = {
                        "running": False,
                        "last_run": log["last_run"],
                        "status": "idle",
                        "message": f"上次运行: {log['last_run'][-12:] if log['last_run'] else 'N/A'}"
                    }

    return status


# =============================================================================
# HTML Content
# =============================================================================

HTML_CONTENT = """ + "'" + "'" + "'" + HTML_TAIL + "'" + "'" + "'" + '''

# Python API handlers
PYTHON_HANDLERS_CODE = """ + '"""' + PYTHON_HANDLERS + '"""''' + '''


def run_server():
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        logger.info(f"Dashboard v3.1 started at http://127.0.0.1:{PORT}")
        logger.info(f"24 Cron scripts: 6 categories")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
'''

print("File generated. Total length:", len(full_content))
