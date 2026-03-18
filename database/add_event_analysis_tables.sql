-- ============================================================
-- 事件驱动分析模块新增表
-- 创建时间: 2026-03-16
-- 说明: 新增表，不影响现有表
-- ============================================================

-- 1. 新闻标签表
CREATE TABLE IF NOT EXISTS news_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT,
    source TEXT,
    news_url TEXT,
    
    sentiment TEXT NOT NULL,
    sentiment_confidence REAL,
    sentiment_reason TEXT,
    
    event_types TEXT,
    affected_sectors TEXT,
    affected_stocks TEXT,
    
    impact_score REAL,
    urgency TEXT,
    
    news_time TIMESTAMP,
    labeled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    ai_model TEXT DEFAULT 'claude',
    metadata TEXT
);

-- 2. 事件-K线关联表
CREATE TABLE IF NOT EXISTS event_kline_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    
    association_type TEXT,
    association_strength REAL,
    
    kline_start_date TEXT NOT NULL,
    kline_end_date TEXT NOT NULL,
    kline_open REAL,
    kline_close REAL,
    kline_high REAL,
    kline_low REAL,
    kline_change_pct REAL,
    
    pre_event_close REAL,
    post_event_high REAL,
    post_event_low REAL,
    post_event_days INTEGER,
    max_gain REAL,
    max_drawdown REAL,
    
    ai_analysis TEXT,
    confidence_score REAL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(news_id, stock_code, kline_start_date)
);

-- 3. 框选区间分析表
CREATE TABLE IF NOT EXISTS range_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    session_id TEXT,
    
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    
    start_price REAL,
    end_price REAL,
    high_price REAL,
    low_price REAL,
    total_return REAL,
    volatility REAL,
    
    event_count INTEGER,
    positive_events INTEGER,
    negative_events INTEGER,
    event_summary TEXT,
    
    ai_summary TEXT,
    ai_insights TEXT,
    key_events TEXT,
    recommendations TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 事件影响历史表
CREATE TABLE IF NOT EXISTS event_impact_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    
    predicted_direction TEXT,
    actual_direction TEXT,
    predicted_impact REAL,
    actual_impact REAL,
    
    day1_change REAL,
    day3_change REAL,
    day5_change REAL,
    day10_change REAL,
    
    prediction_accuracy REAL,
    lesson_learned TEXT,
    rule_suggestion TEXT,
    
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_news_labels_sentiment ON news_labels(sentiment);
CREATE INDEX IF NOT EXISTS idx_news_labels_time ON news_labels(news_time);
CREATE INDEX IF NOT EXISTS idx_event_kline_news ON event_kline_associations(news_id);
CREATE INDEX IF NOT EXISTS idx_event_kline_stock ON event_kline_associations(stock_code);
CREATE INDEX IF NOT EXISTS idx_range_stock ON range_analysis(stock_code);
CREATE INDEX IF NOT EXISTS idx_range_date ON range_analysis(start_date, end_date);
