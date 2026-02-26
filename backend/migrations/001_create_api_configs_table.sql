-- 创建 API 配置表
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

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_api_configs_user_id ON api_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_api_configs_is_active ON api_configs(is_active);

-- 添加注释
COMMENT ON TABLE api_configs IS 'API配置表 - 存储用户的交易所API密钥配置';
COMMENT ON COLUMN api_configs.name IS '配置名称,如实盘配置/模拟盘配置';
COMMENT ON COLUMN api_configs.exchange IS '交易所名称';
COMMENT ON COLUMN api_configs.api_key IS 'API Key';
COMMENT ON COLUMN api_configs.secret_key IS 'Secret Key (加密存储)';
COMMENT ON COLUMN api_configs.passphrase IS 'API Passphrase';
COMMENT ON COLUMN api_configs.is_simulated IS '是否为模拟盘';
COMMENT ON COLUMN api_configs.is_active IS '是否为当前激活配置';
COMMENT ON COLUMN api_configs.proxy IS '代理地址';
COMMENT ON COLUMN api_configs.is_valid IS '配置是否有效';
COMMENT ON COLUMN api_configs.last_verified_at IS '最后验证时间';
COMMENT ON COLUMN api_configs.error_message IS '错误信息';
