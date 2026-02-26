-- OKK量化交易系统 - 数据库清理脚本
-- 执行方式: docker exec -it okk_postgres psql -U okk_user -d okk_quant -f clear_database.sql

BEGIN;

-- 1. 清空所有业务数据表
TRUNCATE TABLE backtest_trades CASCADE;
TRUNCATE TABLE backtests CASCADE;
TRUNCATE TABLE orders CASCADE;
TRUNCATE TABLE strategies CASCADE;
TRUNCATE TABLE api_configs CASCADE;
TRUNCATE TABLE risk_controls CASCADE;
TRUNCATE TABLE alerts CASCADE;
TRUNCATE TABLE risk_actions CASCADE;

-- 2. 询问是否清空K线数据（历史数据可能很大）
-- TRUNCATE TABLE klines CASCADE;  -- 取消注释此行来清空K线数据

-- 3. 重置所有序列
ALTER SEQUENCE strategies_id_seq RESTART WITH 1;
ALTER SEQUENCE api_configs_id_seq RESTART WITH 1;
ALTER SEQUENCE backtests_id_seq RESTART WITH 1;
ALTER SEQUENCE orders_id_seq RESTART WITH 1;
ALTER SEQUENCE alerts_id_seq RESTART WITH 1;
ALTER SEQUENCE risk_controls_id_seq RESTART WITH 1;
ALTER SEQUENCE risk_actions_id_seq RESTART WITH 1;

-- 4. 显示清理结果
DO $$
DECLARE
    table_name text;
    count int;
BEGIN
    FOR table_name IN VALUES ('strategies'), ('api_configs'), ('backtests'), ('orders'), ('alerts')
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I', table_name) INTO count;
        RAISE NOTICE '%: % 条记录', table_name, count;
    END LOOP;
END $$;

COMMIT;

-- 显示所有表
\dt

-- 显示完成消息
SELECT '✅ 数据库清理完成！' AS status;
