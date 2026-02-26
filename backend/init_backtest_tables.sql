-- 回测系统数据库初始化脚本
-- 用于创建K线数据表、回测记录表和回测交易表

-- ============================================
-- 1. K线数据表 (时序数据)
-- ============================================
CREATE TABLE IF NOT EXISTS klines (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp BIGINT NOT NULL,
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(30, 8) NOT NULL,
    volume_currency NUMERIC(30, 8) NOT NULL,
    confirm INTEGER DEFAULT 1,
    CONSTRAINT uix_symbol_interval_timestamp UNIQUE (symbol, interval, timestamp)
);

COMMENT ON TABLE klines IS 'K线数据表 - 用于回测和历史数据分析';
COMMENT ON COLUMN klines.symbol IS '交易对，如 BTC-USDT';
COMMENT ON COLUMN klines.interval IS 'K线周期：1m/5m/15m/30m/1H/4H/1D';
COMMENT ON COLUMN klines.timestamp IS 'K线开始时间戳(毫秒)';
COMMENT ON COLUMN klines.open IS '开盘价';
COMMENT ON COLUMN klines.high IS '最高价';
COMMENT ON COLUMN klines.low IS '最低价';
COMMENT ON COLUMN klines.close IS '收盘价';
COMMENT ON COLUMN klines.volume IS '成交量(币)';
COMMENT ON COLUMN klines.volume_currency IS '成交额(USDT)';
COMMENT ON COLUMN klines.confirm IS '是否确认：0=未确认,1=已确认';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_klines_symbol ON klines(symbol);
CREATE INDEX IF NOT EXISTS idx_klines_interval ON klines(interval);
CREATE INDEX IF NOT EXISTS idx_klines_timestamp ON klines(timestamp);
CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval_timestamp ON klines(symbol, interval, timestamp);

-- 如果使用TimescaleDB，转换为超表（可选）
-- SELECT create_hypertable('klines', 'timestamp', chunk_time_interval => 86400000, if_not_exists => TRUE);


-- ============================================
-- 2. 回测记录表
-- ============================================
CREATE TABLE IF NOT EXISTS backtests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    start_time BIGINT NOT NULL,
    end_time BIGINT NOT NULL,
    initial_capital NUMERIC(20, 2) NOT NULL DEFAULT 10000,
    parameters JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    final_capital NUMERIC(20, 2),
    total_return NUMERIC(10, 4),
    annualized_return NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(10, 4),
    profit_factor NUMERIC(10, 4),
    total_fee NUMERIC(20, 8),
    equity_curve JSONB,
    trade_history JSONB,
    position_history JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

COMMENT ON TABLE backtests IS '回测记录表';
COMMENT ON COLUMN backtests.user_id IS '用户ID';
COMMENT ON COLUMN backtests.name IS '回测名称';
COMMENT ON COLUMN backtests.strategy_type IS '策略类型：grid/martin/trend等';
COMMENT ON COLUMN backtests.symbol IS '交易对，如 BTC-USDT';
COMMENT ON COLUMN backtests.interval IS 'K线周期';
COMMENT ON COLUMN backtests.start_time IS '回测开始时间戳(毫秒)';
COMMENT ON COLUMN backtests.end_time IS '回测结束时间戳(毫秒)';
COMMENT ON COLUMN backtests.initial_capital IS '初始资金(USDT)';
COMMENT ON COLUMN backtests.parameters IS '策略参数';
COMMENT ON COLUMN backtests.status IS '状态：pending/running/completed/failed';
COMMENT ON COLUMN backtests.final_capital IS '最终资金(USDT)';
COMMENT ON COLUMN backtests.total_return IS '总收益率';
COMMENT ON COLUMN backtests.annualized_return IS '年化收益率';
COMMENT ON COLUMN backtests.max_drawdown IS '最大回撤';
COMMENT ON COLUMN backtests.sharpe_ratio IS '夏普比率';
COMMENT ON COLUMN backtests.win_rate IS '胜率';
COMMENT ON COLUMN backtests.profit_factor IS '盈亏比';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_backtests_user_id ON backtests(user_id);
CREATE INDEX IF NOT EXISTS idx_backtests_status ON backtests(status);
CREATE INDEX IF NOT EXISTS idx_backtests_created_at ON backtests(created_at);


-- ============================================
-- 3. 回测交易记录表
-- ============================================
CREATE TABLE IF NOT EXISTS backtest_trades (
    id SERIAL PRIMARY KEY,
    backtest_id INTEGER NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
    timestamp BIGINT NOT NULL,
    side VARCHAR(10) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8) NOT NULL,
    position_before NUMERIC(20, 8),
    position_after NUMERIC(20, 8),
    capital_before NUMERIC(20, 2),
    capital_after NUMERIC(20, 2),
    pnl NUMERIC(20, 8),
    pnl_percent NUMERIC(10, 4)
);

COMMENT ON TABLE backtest_trades IS '回测交易记录表';
COMMENT ON COLUMN backtest_trades.backtest_id IS '回测ID';
COMMENT ON COLUMN backtest_trades.timestamp IS '交易时间戳(毫秒)';
COMMENT ON COLUMN backtest_trades.side IS '方向：buy/sell';
COMMENT ON COLUMN backtest_trades.price IS '成交价格';
COMMENT ON COLUMN backtest_trades.amount IS '成交数量';
COMMENT ON COLUMN backtest_trades.fee IS '手续费';
COMMENT ON COLUMN backtest_trades.pnl IS '本次交易盈亏';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_timestamp ON backtest_trades(timestamp);
