-- Create strategy event timeline table for strategy explainability and replay.

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

CREATE INDEX IF NOT EXISTS idx_strategy_events_user_id
    ON strategy_events(user_id);

CREATE INDEX IF NOT EXISTS idx_strategy_events_strategy_id_created_at
    ON strategy_events(strategy_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_events_event_type
    ON strategy_events(event_type);

COMMENT ON TABLE strategy_events IS '策略运行事件时间线';
COMMENT ON COLUMN strategy_events.event_type IS '事件类型: start/signal/open_position/close_position/risk_pause/stop/error';
COMMENT ON COLUMN strategy_events.parameter_snapshot IS '事件发生时的策略参数快照';
