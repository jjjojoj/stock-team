-- 补充缺失的数据库表

-- 智能体（团队成员）表
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,           -- CIO/Quant/Trader/Risk/Research/Learning
    role TEXT NOT NULL,                  -- 角色
    status TEXT DEFAULT 'active',         -- active/inactive/eliminated
    skills JSON,                         -- 技能列表
    performance_score REAL DEFAULT 50,   -- 综合评分
    warning_count INTEGER DEFAULT 0,     -- 警告次数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 预测表
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,                -- 股票代码
    name TEXT,                           -- 股票名称
    direction TEXT NOT NULL,             -- up/down/neutral
    current_price REAL,                   -- 当前价格
    target_price REAL,                    -- 目标价格
    confidence INTEGER,                  -- 置信度 0-100
    timeframe TEXT,                      -- 时间周期（1周/1月等）
    reasons TEXT,                         -- 看多/看空原因
    risks TEXT,                           -- 风险因素
    source_agent TEXT,                    -- 来源智能体
    status TEXT DEFAULT 'active',         -- active/verified/expired/cancelled
    result TEXT,                          -- correct/incorrect/pending
    actual_end_price REAL,                -- 实际结束价格
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at);

-- 初始化团队成员
INSERT OR IGNORE INTO agents (name, role, skills, performance_score) VALUES
('CIO', '首席投资官', '["决策", "风控", "团队管理"]', 85),
('Quant', '量化分析师', '["数据分析", "技术分析", "建模"]', 75),
('Trader', '交易员', '["交易执行", "市场监控", "风险管理"]', 80),
('Risk', '风控官', '["风险评估", "预警", "合规"]', 70),
('Research', '研究员', '["基本面分析", "行业研究", "公司分析"]', 65),
('Learning', '学习官', '["复盘", "知识提取", "规则生成"]', 60);

-- 初始化示例提案
INSERT OR IGNORE INTO proposals (symbol, name, direction, thesis, target_price, stop_loss, source_agent, priority, status) VALUES
('sz.000792', '盐湖股份', 'buy', '青海国资委锂业龙头，全球最大盐湖提锂企业，受益于新能源产业发展', 44.22, 33.9, 'Research', 'high', 'approved'),
('sh.600459', '贵研铂业', 'buy', '美伊冲突升级，战略金属涨价预期，技术面超跌反弹', 28.00, 24.00, 'Research', 'normal', 'pending'),
('sz.000002', '万科A', 'buy', '地产政策放松，优质龙头估值修复', 12.50, 10.80, 'Research', 'normal', 'pending');

-- 初始化交易记录（与 positions.json 同步）
INSERT OR IGNORE INTO trades (symbol, name, direction, shares, price, amount, reason, executed_at) VALUES
('sz.000792', '盐湖股份', 'buy', 800, 36.85, 29480, '青海国资委锂业', '2026-03-03 10:00:00');

-- 初始化 agent_logs
INSERT OR IGNORE INTO agent_logs (agent, event_type, event_data) VALUES
('Research', 'proposal', '{"symbol": "sz.000792", "name": "盐湖股份", "action": "创建提案"}'),
('CIO', 'approval', '{"symbol": "sz.000792", "decision": "approved", "reason": "基本面优秀"}'),
('Trader', 'trade', '{"symbol": "sz.000792", "action": "买入", "shares": 800, "price": 36.85}'),
('Risk', 'alert', '{"type": "position_update", "symbol": "sz.000792", "status": "monitoring"}');
