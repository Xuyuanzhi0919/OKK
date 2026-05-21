-- OKK量化交易系统 PostgreSQL数据库初始化脚本
-- 执行方式: psql -U postgres -d okk_quant -f init_postgresql.sql

-- 删除已存在的表和类型（如果需要重新创建）
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS strategies CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP TYPE IF EXISTS strategy_status CASCADE;
DROP TYPE IF EXISTS strategy_type CASCADE;
DROP TYPE IF EXISTS order_side CASCADE;
DROP TYPE IF EXISTS order_type CASCADE;
DROP TYPE IF EXISTS order_status CASCADE;

-- 创建枚举类型（使用小写值，与Python模型一致）
CREATE TYPE strategy_status AS ENUM ('stopped', 'running', 'paused', 'error');
CREATE TYPE strategy_type AS ENUM ('grid', 'martin', 'trend', 'arbitrage', 'custom');
CREATE TYPE order_side AS ENUM ('buy', 'sell');
CREATE TYPE order_type AS ENUM ('limit', 'market', 'stop_limit', 'stop_market');
CREATE TYPE order_status AS ENUM ('pending', 'submitted', 'partial_filled', 'filled', 'canceled', 'failed');

-- 创建用户表
CREATE TABLE users (
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

-- 创建策略表
CREATE TABLE strategies (
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

-- 创建订单表
CREATE TABLE orders (
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

-- 创建持仓表
CREATE TABLE positions (
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

-- 创建索引
CREATE INDEX idx_strategies_user_id ON strategies(user_id);
CREATE INDEX idx_strategies_status ON strategies(status);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_strategy_id ON orders(strategy_id);
CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_positions_user_id ON positions(user_id);
CREATE INDEX idx_positions_symbol ON positions(symbol);

CREATE TABLE IF NOT EXISTS strategy_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    message TEXT,
    data JSONB,
    parameter_snapshot JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_events_user_id ON strategy_events(user_id);
CREATE INDEX IF NOT EXISTS idx_strategy_events_strategy_id_created_at ON strategy_events(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_events_event_type ON strategy_events(event_type);

-- 插入测试用户（密码: admin123）
INSERT INTO users (username, email, hashed_password, is_superuser)
VALUES ('admin', 'admin@okk.com', '$2b$12$XZfL2JOv0K1ytph5pt9fO.bTak9m.H6GN20KFYkd4wKoJSqK4a9ia', TRUE)
ON CONFLICT (username) DO UPDATE SET
    hashed_password = EXCLUDED.hashed_password,
    is_superuser = TRUE;

-- 显示创建结果
\echo '====================================='
\echo 'Database tables created successfully!'
\echo '====================================='
\echo ''
\echo 'Enum types:'
SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname;
\echo ''
\echo 'Tables:'
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
\echo ''
\echo '====================================='
