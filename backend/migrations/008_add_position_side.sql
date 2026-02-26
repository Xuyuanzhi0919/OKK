-- 迁移: 008_add_position_side.sql
-- 用途: 为 strategies 表添加 position_side 字段，支持多空双向持仓状态恢复

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS position_side VARCHAR(10) NOT NULL DEFAULT '';

COMMENT ON COLUMN strategies.position_side IS '持仓方向: long=多仓, short=空仓, 空字符串=无仓';
