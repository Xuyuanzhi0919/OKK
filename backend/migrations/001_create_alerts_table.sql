-- 创建告警记录表
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

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_strategy_id ON alerts(strategy_id);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);

-- 添加注释
COMMENT ON TABLE alerts IS '告警记录表';
COMMENT ON COLUMN alerts.alert_type IS '告警类型: stop_loss(止损), take_profit(止盈), risk_warning(风险警告), system_error(系统错误)';
COMMENT ON COLUMN alerts.severity IS '告警级别: info, warning, error, success';
COMMENT ON COLUMN alerts.is_read IS '是否已读';
COMMENT ON COLUMN alerts.is_handled IS '是否已处理';
