-- 为 trades 表添加 prediction_id 字段
-- 用于关联交易和预测，实现闭环验证

-- 添加 prediction_id 列
ALTER TABLE trades ADD COLUMN prediction_id TEXT;

-- 创建索引以加速查询
CREATE INDEX IF NOT EXISTS idx_trades_prediction_id ON trades(prediction_id);

-- 创建复合索引用于预测-交易关联分析
CREATE INDEX IF NOT EXISTS idx_trades_symbol_prediction ON trades(symbol, prediction_id);
