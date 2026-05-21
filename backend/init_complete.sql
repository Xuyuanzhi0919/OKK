-- =============================================================================
-- OKK 量化交易系统 - 完整数据库初始化脚本
-- =============================================================================
-- 执行方式: psql -U postgres -h localhost -p 5433 -d okk_quant -f init_complete.sql
-- 或使用 Python: python init_db.py
--
-- 包含的表:
--   1. 核心表: users, strategies, orders, positions
--   2. API配置: api_configs
--   3. 告警系统: alerts
--   4. 风控系统: risk_controls, risk_actions
--   5. 回测系统: klines, backtests, backtest_trades
-- =============================================================================

-- =============================================================================
-- 清理旧表和类型 (可选 - 谨慎使用)
-- =============================================================================
-- 取消注释以下代码可完全重建数据库
/*
DROP TABLE IF EXISTS risk_actions CASCADE;
DROP TABLE IF EXISTS risk_controls CASCADE;
DROP TABLE IF EXISTS backtest_trades CASCADE;
DROP TABLE IF EXISTS backtests CASCADE;
DROP TABLE IF EXISTS klines CASCADE;
DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS api_configs CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS strategies CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP TYPE IF EXISTS strategy_status CASCADE;
DROP TYPE IF EXISTS strategy_type CASCADE;
DROP TYPE IF EXISTS order_side CASCADE;
DROP TYPE IF EXISTS order_type CASCADE;
DROP TYPE IF EXISTS order_status CASCADE;
*/

-- =============================================================================
-- 1. 创建枚举类型
-- =============================================================================

-- 策略状态
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'strategy_status') THEN
        CREATE TYPE strategy_status AS ENUM ('stopped', 'running', 'paused', 'error');
    END IF;
END $$;

-- 策略类型
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'strategy_type') THEN
        CREATE TYPE strategy_type AS ENUM (
            'grid',
            'swing_long',
            'swing_short',
            'ai_swing_long',
            'martin',
            'trend',
            'arbitrage',
            'order_book_imbalance',
            'dual_side',
            'custom'
        );
    END IF;
END $$;

ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'swing_long';
ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'swing_short';
ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'ai_swing_long';
ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'order_book_imbalance';
ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'dual_side';

-- 订单方向
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_side') THEN
        CREATE TYPE order_side AS ENUM ('buy', 'sell');
    END IF;
END $$;

-- 订单类型
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_type') THEN
        CREATE TYPE order_type AS ENUM ('limit', 'market', 'ioc', 'post_only', 'stop_limit', 'stop_market');
    END IF;
END $$;

ALTER TYPE order_type ADD VALUE IF NOT EXISTS 'ioc';
ALTER TYPE order_type ADD VALUE IF NOT EXISTS 'post_only';

-- 订单状态
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        CREATE TYPE order_status AS ENUM ('pending', 'submitted', 'partial_filled', 'filled', 'canceled', 'failed');
    END IF;
END $$;

-- =============================================================================
-- 2. 核心业务表
-- =============================================================================

-- 用户表
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

COMMENT ON TABLE users IS '用户表';
COMMENT ON COLUMN users.username IS '用户名';
COMMENT ON COLUMN users.email IS '邮箱';
COMMENT ON COLUMN users.is_active IS '账户是否激活';
COMMENT ON COLUMN users.is_superuser IS '是否超级管理员';

-- 策略表
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
    position_in_position BOOLEAN DEFAULT FALSE,
    position_side VARCHAR(10) DEFAULT '',
    position_entry_price NUMERIC DEFAULT 0.0,
    position_qty NUMERIC DEFAULT 0.0,
    position_open_time NUMERIC DEFAULT 0.0,
    position_highest_price NUMERIC DEFAULT 0.0,
    position_trail_stop_px NUMERIC DEFAULT 0.0,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    stopped_at TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE strategies IS '策略表';
COMMENT ON COLUMN strategies.type IS '策略类型: grid(网格), martin(马丁), trend(趋势), arbitrage(套利), custom(自定义)';
COMMENT ON COLUMN strategies.status IS '策略状态: stopped(已停止), running(运行中), paused(已暂停), error(错误)';
COMMENT ON COLUMN strategies.parameters IS '策略参数(JSON格式)';

-- 订单表
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

COMMENT ON TABLE orders IS '订单表';
COMMENT ON COLUMN orders.order_id IS '交易所订单ID';
COMMENT ON COLUMN orders.side IS '订单方向: buy(买入), sell(卖出)';
COMMENT ON COLUMN orders.order_type IS '订单类型: limit(限价), market(市价), stop_limit(止损限价), stop_market(止损市价)';
COMMENT ON COLUMN orders.status IS '订单状态';

-- 持仓表
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

COMMENT ON TABLE positions IS '持仓表';
COMMENT ON COLUMN positions.available_amount IS '可用数量';
COMMENT ON COLUMN positions.frozen_amount IS '冻结数量';
COMMENT ON COLUMN positions.unrealized_pnl IS '未实现盈亏';
COMMENT ON COLUMN positions.realized_pnl IS '已实现盈亏';

-- 账户净值快照表
CREATE TABLE IF NOT EXISTS account_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    total_equity NUMERIC NOT NULL,
    available_balance NUMERIC DEFAULT 0.0,
    unrealized_pnl NUMERIC DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_account_snapshots_user_id ON account_snapshots(user_id);
CREATE INDEX IF NOT EXISTS ix_account_snapshots_created_at ON account_snapshots(created_at);

COMMENT ON TABLE account_snapshots IS '账户净值历史快照表';

-- =============================================================================
-- 3. API 配置表
-- =============================================================================

CREATE TABLE IF NOT EXISTS api_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- API配置信息
    name VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL DEFAULT 'OKX',
    api_key VARCHAR(255) NOT NULL,
    secret_key TEXT NOT NULL,
    passphrase VARCHAR(255) NOT NULL,

    -- 配置属性
    is_simulated BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT FALSE,
    proxy VARCHAR(255),

    -- 状态信息
    is_valid BOOLEAN DEFAULT TRUE,
    last_verified_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE api_configs IS 'API配置表 - 存储用户的交易所API密钥';
COMMENT ON COLUMN api_configs.name IS '配置名称,如"实盘配置"/"模拟盘配置"';
COMMENT ON COLUMN api_configs.is_simulated IS '是否为模拟盘';
COMMENT ON COLUMN api_configs.is_active IS '是否为当前激活配置';

-- AI 配置表
CREATE TABLE IF NOT EXISTS ai_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    provider VARCHAR(50) DEFAULT 'deepseek',
    api_key VARCHAR(255) NOT NULL,
    model VARCHAR(100) DEFAULT 'deepseek-chat',
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_ai_configs_user_id ON ai_configs(user_id);

COMMENT ON TABLE ai_configs IS 'AI服务配置表';

-- =============================================================================
-- 4. 告警系统表
-- =============================================================================

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

COMMENT ON TABLE alerts IS '告警记录表';
COMMENT ON COLUMN alerts.alert_type IS '告警类型: stop_loss(止损), take_profit(止盈), risk_warning(风险警告), system_error(系统错误)';
COMMENT ON COLUMN alerts.severity IS '告警级别: info, warning, error, success';

-- =============================================================================
-- 5. 风控系统表
-- =============================================================================

-- 风控配置表
CREATE TABLE IF NOT EXISTS risk_controls (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,

    -- 风控级别和类型
    level VARCHAR(20) NOT NULL DEFAULT 'strategy',
    risk_type VARCHAR(50) NOT NULL,

    -- 基本信息
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT TRUE,

    -- 资金风控参数
    min_available_balance FLOAT,
    max_position_value FLOAT,
    max_order_amount FLOAT,

    -- 盈亏风控参数
    max_drawdown_percent FLOAT,
    daily_loss_limit FLOAT,
    total_loss_limit FLOAT,
    max_consecutive_losses INTEGER,

    -- 持仓风控参数
    max_position_per_symbol FLOAT,
    max_concentration_ratio FLOAT,

    -- 交易频率风控参数
    max_trades_per_period INTEGER,
    period_seconds INTEGER,

    -- 风控动作配置
    action_on_trigger VARCHAR(20) NOT NULL DEFAULT 'warn',
    warning_threshold FLOAT DEFAULT 0.8,
    auto_resume BOOLEAN DEFAULT FALSE,

    -- 状态跟踪
    is_triggered BOOLEAN DEFAULT FALSE,
    trigger_count INTEGER DEFAULT 0,
    last_trigger_at TIMESTAMP WITH TIME ZONE,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE risk_controls IS '风控配置表';
COMMENT ON COLUMN risk_controls.level IS '风控级别: global(全局), strategy(策略级), order(订单级)';
COMMENT ON COLUMN risk_controls.risk_type IS '风控类型: capital(资金), position(持仓), loss(亏损), drawdown(回撤), frequency(频率)';
COMMENT ON COLUMN risk_controls.action_on_trigger IS '触发动作: warn(警告), limit(限制), pause(暂停), close(平仓)';

-- 风控动作日志表
CREATE TABLE IF NOT EXISTS risk_actions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    risk_control_id INTEGER REFERENCES risk_controls(id) ON DELETE SET NULL,

    -- 动作信息
    action_type VARCHAR(20) NOT NULL,
    trigger_reason TEXT NOT NULL,
    risk_metrics TEXT,

    -- 执行结果
    execution_status VARCHAR(20) NOT NULL DEFAULT 'success',
    execution_details TEXT,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE risk_actions IS '风控动作日志表';
COMMENT ON COLUMN risk_actions.action_type IS '动作类型: warn(警告), limit(限制), pause(暂停), close(平仓), resume(恢复)';

-- =============================================================================
-- 6. 回测系统表
-- =============================================================================

-- K线数据表
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
COMMENT ON COLUMN klines.interval IS 'K线周期: 1m/5m/15m/30m/1H/4H/1D';
COMMENT ON COLUMN klines.timestamp IS 'K线开始时间戳(毫秒)';
COMMENT ON COLUMN klines.confirm IS '是否确认: 0=未确认, 1=已确认';

-- 回测记录表
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
COMMENT ON COLUMN backtests.status IS '状态: pending(待运行), running(运行中), completed(已完成), failed(失败)';
COMMENT ON COLUMN backtests.total_return IS '总收益率';
COMMENT ON COLUMN backtests.max_drawdown IS '最大回撤';
COMMENT ON COLUMN backtests.sharpe_ratio IS '夏普比率';

-- 回测交易记录表
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
COMMENT ON COLUMN backtest_trades.pnl IS '本次交易盈亏';

-- =============================================================================
-- 7. 创建索引
-- =============================================================================

-- 核心表索引
CREATE INDEX IF NOT EXISTS idx_strategies_user_id ON strategies(user_id);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_strategy_id ON orders(strategy_id);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);

-- API配置索引
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

-- 告警系统索引
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_strategy_id ON alerts(strategy_id);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);

-- 风控系统索引
CREATE INDEX IF NOT EXISTS idx_risk_controls_user_id ON risk_controls(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_strategy_id ON risk_controls(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_level ON risk_controls(level);
CREATE INDEX IF NOT EXISTS idx_risk_controls_risk_type ON risk_controls(risk_type);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_enabled ON risk_controls(is_enabled);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_triggered ON risk_controls(is_triggered);

CREATE INDEX IF NOT EXISTS idx_risk_actions_user_id ON risk_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_strategy_id ON risk_actions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_risk_control_id ON risk_actions(risk_control_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_action_type ON risk_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_risk_actions_created_at ON risk_actions(created_at DESC);

-- 回测系统索引
CREATE INDEX IF NOT EXISTS idx_klines_symbol ON klines(symbol);
CREATE INDEX IF NOT EXISTS idx_klines_interval ON klines(interval);
CREATE INDEX IF NOT EXISTS idx_klines_timestamp ON klines(timestamp);
CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval_timestamp ON klines(symbol, interval, timestamp);

CREATE INDEX IF NOT EXISTS idx_backtests_user_id ON backtests(user_id);
CREATE INDEX IF NOT EXISTS idx_backtests_status ON backtests(status);
CREATE INDEX IF NOT EXISTS idx_backtests_created_at ON backtests(created_at);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_timestamp ON backtest_trades(timestamp);

-- =============================================================================
-- 8. 插入初始数据
-- =============================================================================

-- 创建默认管理员账户 (用户名: admin, 密码: admin123)
INSERT INTO users (username, email, hashed_password, is_superuser)
VALUES ('admin', 'admin@okk.com', '$2b$12$XZfL2JOv0K1ytph5pt9fO.bTak9m.H6GN20KFYkd4wKoJSqK4a9ia', TRUE)
ON CONFLICT (username) DO UPDATE SET
    hashed_password = EXCLUDED.hashed_password,
    is_superuser = TRUE;

-- 为所有用户创建默认全局风控规则 (默认禁用)
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
    '全局资金安全线',
    '账户可用资金低于1000 USDT时发出警告',
    1000.0,
    'warn',
    FALSE
FROM users
ON CONFLICT DO NOTHING;

-- =============================================================================
-- 9. 完成提示
-- =============================================================================

SELECT '=====================================' AS message;
SELECT 'Database initialization completed!' AS message;
SELECT '=====================================' AS message;
SELECT '' AS message;
SELECT 'Created enum types:' AS message;
SELECT typname FROM pg_type WHERE typtype = 'e' ORDER BY typname;
SELECT '' AS message;
SELECT 'Created tables:' AS message;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT '' AS message;
SELECT 'Default credentials:' AS message;
SELECT '  Username: admin' AS info;
SELECT '  Password: admin123' AS info;
SELECT '' AS message;
SELECT '=====================================' AS message;
