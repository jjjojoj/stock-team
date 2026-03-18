-- 中国股市智能投资团队数据库

-- 投资提案表
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,           -- 股票代码 (如 000001)
    name TEXT,                      -- 股票名称
    direction TEXT NOT NULL,        -- buy/sell
    thesis TEXT,                    -- 投资逻辑
    target_price REAL,              -- 目标价
    stop_loss REAL,                 -- 止损价
    source_agent TEXT NOT NULL,     -- 来源智能体
    priority TEXT DEFAULT 'normal', -- low/normal/high/urgent
    status TEXT DEFAULT 'pending',  -- pending/quant_validated/risk_checked/approved/rejected/executed/cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    executed_at TIMESTAMP,
    metadata JSON                   -- 额外数据
);

-- 量化验证表
CREATE TABLE IF NOT EXISTS quant_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    ma5 REAL,
    ma10 REAL,
    ma20 REAL,
    ma60 REAL,
    macd TEXT,                      -- 金叉/死叉/多头/空头
    kdj TEXT,                       -- 超买/超卖/正常
    rsi REAL,
    volume_ratio REAL,              -- 量比
    technical_score INTEGER,        -- 技术评分 0-100
    recommendation TEXT,            -- strong_buy/buy/hold/sell/strong_sell
    analysis_result JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

-- 风险评估表
CREATE TABLE IF NOT EXISTS risk_assessment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    risk_level TEXT,                -- low/medium/high/very_high
    suggested_position REAL,        -- 建议仓位比例 (0-1)
    max_position REAL,              -- 最大仓位
    var_95 REAL,                    -- 95% VaR
    volatility REAL,                -- 波动率
    industry_concentration REAL,    -- 行业集中度
    correlation_market REAL,        -- 与市场相关性
    risk_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

-- 持仓表
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT,
    shares INTEGER,                 -- 持仓股数
    cost_price REAL,                -- 成本价
    current_price REAL,             -- 当前价
    market_value REAL,              -- 市值
    profit_loss REAL,               -- 浮动盈亏
    profit_loss_pct REAL,           -- 盈亏比例
    position_pct REAL,              -- 仓位比例
    stop_loss REAL,                 -- 止损价
    take_profit REAL,               -- 止盈价
    status TEXT DEFAULT 'holding',  -- holding/sold/stopped_out
    bought_at TIMESTAMP,
    sold_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 交易记录表
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name TEXT,
    direction TEXT NOT NULL,        -- buy/sell
    shares INTEGER,
    price REAL,
    amount REAL,                    -- 成交金额
    commission REAL,                -- 手续费
    reason TEXT,                    -- 交易原因
    proposal_id INTEGER,            -- 关联提案
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

-- 账户表
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,      -- YYYY-MM-DD
    total_asset REAL,               -- 总资产
    cash REAL,                      -- 现金
    market_value REAL,              -- 市值
    total_profit REAL,              -- 总盈亏
    total_profit_pct REAL,          -- 总收益率
    daily_profit REAL,              -- 日盈亏
    daily_profit_pct REAL,          -- 日收益率
    position_count INTEGER,         -- 持仓数
    max_drawdown REAL,              -- 最大回撤
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 监控列表
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT,
    industry TEXT,                  -- 所属行业
    reason TEXT,                    -- 关注原因
    target_price REAL,              -- 目标价
    alert_price_high REAL,          -- 高点提醒
    alert_price_low REAL,           -- 低点提醒
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 智能体日志
CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,            -- cio/researcher/quant/risk/trader
    event_type TEXT NOT NULL,       -- proposal/analysis/approval/trade/alert
    event_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 市场数据缓存
CREATE TABLE IF NOT EXISTS market_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name TEXT,
    price REAL,
    change_pct REAL,
    volume REAL,
    turnover REAL,
    pe REAL,
    pb REAL,
    market_cap REAL,
    industry TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 触发器配置
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    condition_type TEXT NOT NULL,   -- price_threshold/time_based/event_based
    condition_config JSON NOT NULL,
    action_agent TEXT NOT NULL,
    action_type TEXT NOT NULL,
    cooldown_minutes INTEGER DEFAULT 60,
    last_triggered_at TIMESTAMP,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_symbol ON proposals(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(executed_at);
CREATE INDEX IF NOT EXISTS idx_account_date ON account(date);
CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist(symbol);
CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent);
CREATE INDEX IF NOT EXISTS idx_market_cache_symbol ON market_cache(symbol);

-- 初始化账户（假设初始资金 100 万）
INSERT OR IGNORE INTO account (date, total_asset, cash, market_value, total_profit, total_profit_pct, position_count)
VALUES ('2026-03-02', 1000000, 1000000, 0, 0, 0, 0);

-- 初始化触发器
INSERT OR IGNORE INTO triggers (name, description, condition_type, condition_config, action_agent, action_type, cooldown_minutes)
VALUES 
('market_open', '开盘提醒', 'time_based', '{"time": "09:25"}', 'trader', 'alert', 1440),
('market_close', '收盘复盘', 'time_based', '{"time": "15:05"}', 'researcher', 'daily_summary', 1440),
('stop_loss_check', '止损检查', 'time_based', '{"interval": "5m"}', 'risk', 'check_positions', 5),
('position_update', '更新持仓', 'time_based', '{"interval": "15m"}', 'trader', 'update_prices', 15);
