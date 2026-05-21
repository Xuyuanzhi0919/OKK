-- OKK Quant System full initialization script (PostgreSQL)
-- Execution: psql -U postgres -d okk_quant -f init_all.sql

-- =========================
-- Optional clean start
-- =========================
-- WARNING: Uncomment only if you want to drop existing objects.
-- DROP TABLE IF EXISTS risk_actions CASCADE;
-- DROP TABLE IF EXISTS risk_controls CASCADE;
-- DROP TABLE IF EXISTS alerts CASCADE;
-- DROP TABLE IF EXISTS api_configs CASCADE;
-- DROP TABLE IF EXISTS backtest_trades CASCADE;
-- DROP TABLE IF EXISTS backtests CASCADE;
-- DROP TABLE IF EXISTS klines CASCADE;
-- DROP TABLE IF EXISTS positions CASCADE;
-- DROP TABLE IF EXISTS orders CASCADE;
-- DROP TABLE IF EXISTS strategies CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;
--
-- DROP TYPE IF EXISTS strategy_status CASCADE;
-- DROP TYPE IF EXISTS strategy_type CASCADE;
-- DROP TYPE IF EXISTS order_side CASCADE;
-- DROP TYPE IF EXISTS order_type CASCADE;
-- DROP TYPE IF EXISTS order_status CASCADE;

-- =========================
-- Enum types (idempotent)
-- =========================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'strategy_status') THEN
        CREATE TYPE strategy_status AS ENUM ('stopped', 'running', 'paused', 'error');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'strategy_type') THEN
        CREATE TYPE strategy_type AS ENUM ('grid', 'martin', 'trend', 'arbitrage', 'custom');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_side') THEN
        CREATE TYPE order_side AS ENUM ('buy', 'sell');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_type') THEN
        CREATE TYPE order_type AS ENUM ('limit', 'market', 'stop_limit', 'stop_market');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        CREATE TYPE order_status AS ENUM ('pending', 'submitted', 'partial_filled', 'filled', 'canceled', 'failed');
    END IF;
END $$;

-- =========================
-- Core tables
-- =========================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    okx_api_key VARCHAR(255),
    okx_secret_key VARCHAR(255),
    okx_passphrase VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    type strategy_type NOT NULL,
    status strategy_status DEFAULT 'stopped',
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10),
    parameters JSONB,
    max_position NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    total_profit NUMERIC DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    win_rate NUMERIC DEFAULT 0.0,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    order_id VARCHAR(100) UNIQUE,
    symbol VARCHAR(50) NOT NULL,
    side order_side NOT NULL,
    order_type order_type NOT NULL,
    status order_status DEFAULT 'pending',
    price NUMERIC,
    amount NUMERIC NOT NULL,
    filled_amount NUMERIC DEFAULT 0.0,
    avg_price NUMERIC,
    fee NUMERIC DEFAULT 0.0,
    fee_currency VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP WITH TIME ZONE,
    filled_at TIMESTAMP WITH TIME ZONE,
    canceled_at TIMESTAMP WITH TIME ZONE,
    note VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    symbol VARCHAR(50) NOT NULL,
    amount NUMERIC NOT NULL,
    available_amount NUMERIC NOT NULL,
    frozen_amount NUMERIC DEFAULT 0.0,
    avg_price NUMERIC NOT NULL,
    total_cost NUMERIC NOT NULL,
    unrealized_pnl NUMERIC DEFAULT 0.0,
    realized_pnl NUMERIC DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Core indexes
CREATE INDEX IF NOT EXISTS idx_strategies_user_id ON strategies(user_id);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_strategy_id ON orders(strategy_id);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);

-- Seed admin user (password: admin123)
INSERT INTO users (username, email, hashed_password, is_superuser)
VALUES ('admin', 'admin@okk.com', '$2b$12$XZfL2JOv0K1ytph5pt9fO.bTak9m.H6GN20KFYkd4wKoJSqK4a9ia', TRUE)
ON CONFLICT (username) DO UPDATE SET
    hashed_password = EXCLUDED.hashed_password,
    is_superuser = TRUE;

-- =========================
-- API configs
-- =========================
CREATE TABLE IF NOT EXISTS api_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL DEFAULT 'OKX',
    api_key VARCHAR(255) NOT NULL,
    secret_key TEXT NOT NULL,
    passphrase VARCHAR(255) NOT NULL,

    is_simulated BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT FALSE,
    proxy VARCHAR(255),

    is_valid BOOLEAN DEFAULT TRUE,
    last_verified_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_configs_user_id ON api_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_api_configs_is_active ON api_configs(is_active);

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS api_config_id INTEGER;
ALTER TABLE strategies
    DROP CONSTRAINT IF EXISTS strategies_api_config_id_fkey;
ALTER TABLE strategies
    ADD CONSTRAINT strategies_api_config_id_fkey
    FOREIGN KEY (api_config_id) REFERENCES api_configs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_strategies_api_config_id ON strategies(api_config_id);

-- =========================
-- Alerts
-- =========================
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    data TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    is_handled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    handled_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_strategy_id ON alerts(strategy_id);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);

-- =========================
-- Risk control
-- =========================
CREATE TABLE IF NOT EXISTS risk_controls (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,

    level VARCHAR(20) NOT NULL DEFAULT 'strategy',
    risk_type VARCHAR(50) NOT NULL,

    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT TRUE,

    min_available_balance FLOAT,
    max_position_value FLOAT,
    max_order_amount FLOAT,

    max_drawdown_percent FLOAT,
    daily_loss_limit FLOAT,
    total_loss_limit FLOAT,
    max_consecutive_losses INTEGER,

    max_position_per_symbol FLOAT,
    max_concentration_ratio FLOAT,

    max_trades_per_period INTEGER,
    period_seconds INTEGER,

    action_on_trigger VARCHAR(20) NOT NULL DEFAULT 'warn',
    warning_threshold FLOAT DEFAULT 0.8,
    auto_resume BOOLEAN DEFAULT FALSE,

    is_triggered BOOLEAN DEFAULT FALSE,
    trigger_count INTEGER DEFAULT 0,
    last_trigger_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_controls_user_id ON risk_controls(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_strategy_id ON risk_controls(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_level ON risk_controls(level);
CREATE INDEX IF NOT EXISTS idx_risk_controls_risk_type ON risk_controls(risk_type);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_enabled ON risk_controls(is_enabled);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_triggered ON risk_controls(is_triggered);

CREATE TABLE IF NOT EXISTS risk_actions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    risk_control_id INTEGER REFERENCES risk_controls(id) ON DELETE SET NULL,

    action_type VARCHAR(20) NOT NULL,
    trigger_reason TEXT NOT NULL,
    risk_metrics TEXT,

    execution_status VARCHAR(20) NOT NULL DEFAULT 'success',
    execution_details TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_actions_user_id ON risk_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_strategy_id ON risk_actions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_risk_control_id ON risk_actions(risk_control_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_action_type ON risk_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_risk_actions_created_at ON risk_actions(created_at DESC);

-- Optional default risk control (disabled by default)
INSERT INTO risk_controls (
    user_id,
    level,
    risk_type,
    name,
    description,
    min_available_balance,
    action_on_trigger,
    is_enabled
)
SELECT
    id,
    'global',
    'capital',
    'Global capital safety line',
    'Warn when available balance drops below 1000 USDT',
    1000.0,
    'warn',
    FALSE
FROM users
ON CONFLICT DO NOTHING;

-- =========================
-- Backtest data
-- =========================
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

CREATE INDEX IF NOT EXISTS idx_klines_symbol ON klines(symbol);
CREATE INDEX IF NOT EXISTS idx_klines_interval ON klines(interval);
CREATE INDEX IF NOT EXISTS idx_klines_timestamp ON klines(timestamp);
CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval_timestamp ON klines(symbol, interval, timestamp);

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

CREATE INDEX IF NOT EXISTS idx_backtests_user_id ON backtests(user_id);
CREATE INDEX IF NOT EXISTS idx_backtests_status ON backtests(status);
CREATE INDEX IF NOT EXISTS idx_backtests_created_at ON backtests(created_at);

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

CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_timestamp ON backtest_trades(timestamp);

-- =========================
-- Done
-- =========================
SELECT '=====================================' AS message;
SELECT 'All database tables created successfully!' AS message;
SELECT '=====================================' AS message;
SELECT '' AS message;
SELECT 'Enum types:' AS message;
SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname;
SELECT '' AS message;
SELECT 'Tables:' AS message;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT '' AS message;
SELECT '=====================================' AS message;
