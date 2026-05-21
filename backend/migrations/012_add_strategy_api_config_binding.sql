-- Bind each strategy to a specific API configuration so simulated and live
-- strategies can run at the same time without relying on one global active config.

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS api_config_id INTEGER;

ALTER TABLE strategies
    DROP CONSTRAINT IF EXISTS strategies_api_config_id_fkey;

ALTER TABLE strategies
    ADD CONSTRAINT strategies_api_config_id_fkey
    FOREIGN KEY (api_config_id)
    REFERENCES api_configs(id)
    ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_strategies_api_config_id
    ON strategies(api_config_id);

COMMENT ON COLUMN strategies.api_config_id IS '绑定的API配置ID；为空时兼容旧逻辑使用当前激活配置';
