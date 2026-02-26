-- 修改strategies表，将枚举类型改为VARCHAR类型
-- 执行方式: psql -U postgres -d okk_quant -f alter_tables_to_string.sql

-- 修改strategies表的type和status列为VARCHAR
ALTER TABLE strategies
    ALTER COLUMN type TYPE VARCHAR(50),
    ALTER COLUMN status TYPE VARCHAR(50);

-- 修改orders表的side, order_type, status列为VARCHAR
ALTER TABLE orders
    ALTER COLUMN side TYPE VARCHAR(50),
    ALTER COLUMN order_type TYPE VARCHAR(50),
    ALTER COLUMN status TYPE VARCHAR(50);

\echo 'Tables altered successfully! Enum columns converted to VARCHAR.'
