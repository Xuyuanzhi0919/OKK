-- 风控系统数据库迁移脚本
-- 创建日期: 2025-10-27
-- 描述: 创建风控配置表和风控动作日志表

-- ========== 风控配置表 ==========
CREATE TABLE IF NOT EXISTS risk_controls (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,

    -- 风控级别和类型
    level VARCHAR(20) NOT NULL DEFAULT 'strategy',  -- global, strategy, order
    risk_type VARCHAR(50) NOT NULL,  -- capital, position, loss, drawdown, frequency

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
    action_on_trigger VARCHAR(20) NOT NULL DEFAULT 'warn',  -- warn, limit, pause, close
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

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_risk_controls_user_id ON risk_controls(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_strategy_id ON risk_controls(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_controls_level ON risk_controls(level);
CREATE INDEX IF NOT EXISTS idx_risk_controls_risk_type ON risk_controls(risk_type);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_enabled ON risk_controls(is_enabled);
CREATE INDEX IF NOT EXISTS idx_risk_controls_is_triggered ON risk_controls(is_triggered);

-- 添加注释
COMMENT ON TABLE risk_controls IS '风控配置表';
COMMENT ON COLUMN risk_controls.level IS '风控级别: global(全局), strategy(策略级), order(订单级)';
COMMENT ON COLUMN risk_controls.risk_type IS '风控类型: capital(资金), position(持仓), loss(亏损), drawdown(回撤), frequency(频率)';
COMMENT ON COLUMN risk_controls.action_on_trigger IS '触发动作: warn(警告), limit(限制), pause(暂停), close(平仓)';


-- ========== 风控动作日志表 ==========
CREATE TABLE IF NOT EXISTS risk_actions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    risk_control_id INTEGER REFERENCES risk_controls(id) ON DELETE SET NULL,

    -- 动作信息
    action_type VARCHAR(20) NOT NULL,  -- warn, limit, pause, close, resume
    trigger_reason TEXT NOT NULL,
    risk_metrics TEXT,

    -- 执行结果
    execution_status VARCHAR(20) NOT NULL DEFAULT 'success',  -- success, failed, partial
    execution_details TEXT,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_risk_actions_user_id ON risk_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_strategy_id ON risk_actions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_risk_control_id ON risk_actions(risk_control_id);
CREATE INDEX IF NOT EXISTS idx_risk_actions_action_type ON risk_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_risk_actions_created_at ON risk_actions(created_at DESC);

-- 添加注释
COMMENT ON TABLE risk_actions IS '风控动作日志表';
COMMENT ON COLUMN risk_actions.action_type IS '风控动作类型: warn(警告), limit(限制), pause(暂停), close(平仓), resume(恢复)';
COMMENT ON COLUMN risk_actions.execution_status IS '执行结果: success(成功), failed(失败), partial(部分成功)';


-- ========== 创建默认风控规则（可选）==========
-- 全局资金风控：最小可用资金1000 USDT
INSERT INTO risk_controls (user_id, level, risk_type, name, description, min_available_balance, action_on_trigger, is_enabled)
SELECT
    id,
    'global',
    'capital',
    '全局资金安全线',
    '账户可用资金低于1000 USDT时发出警告',
    1000.0,
    'warn',
    FALSE  -- 默认禁用，用户需要手动启用
FROM users
ON CONFLICT DO NOTHING;

-- 输出
SELECT '风控系统表创建完成！' AS message;
SELECT 'risk_controls 表: 风控配置' AS info;
SELECT 'risk_actions 表: 风控动作日志' AS info;
