-- 迁移: 007_add_strategy_position_state.sql
-- 用途: 为 strategies 表添加持仓状态字段，用于后端重启后恢复持仓信息
-- 背景: 后端重启后内存中的持仓状态会丢失，导致策略认为无持仓而重复开仓

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS position_in_position   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS position_entry_price   FLOAT   NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_qty           FLOAT   NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_open_time     FLOAT   NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_highest_price FLOAT   NOT NULL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_trail_stop_px FLOAT   NOT NULL DEFAULT 0.0;

COMMENT ON COLUMN strategies.position_in_position   IS '是否有持仓（重启恢复用）';
COMMENT ON COLUMN strategies.position_entry_price   IS '开仓均价（重启恢复用）';
COMMENT ON COLUMN strategies.position_qty           IS '持仓数量，合约张数或币数（重启恢复用）';
COMMENT ON COLUMN strategies.position_open_time     IS '开仓时间戳unix秒（重启恢复用）';
COMMENT ON COLUMN strategies.position_highest_price IS '持仓期间最高价，移动止损用（重启恢复用）';
COMMENT ON COLUMN strategies.position_trail_stop_px IS '当前移动止损触发价（重启恢复用）';
