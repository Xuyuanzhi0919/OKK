-- 添加 swing_long 到 strategy_type 枚举
ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'swing_long';

-- 验证枚举值
SELECT enumlabel FROM pg_enum WHERE enumtypid = 'strategy_type'::regtype ORDER BY enumsortorder;
