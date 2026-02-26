"""
添加 swing_long 策略类型到数据库
"""
from sqlalchemy import text, create_engine
from app.core.config import settings

def migrate():
    # 创建同步引擎
    sync_engine = create_engine(
        settings.DATABASE_URL.replace('+psycopg', ''),
        echo=True
    )

    with sync_engine.begin() as conn:
        # 添加 swing_long 到枚举
        try:
            conn.execute(text("""
                ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'swing_long';
            """))
            print("SUCCESS: Added swing_long to strategy_type enum")
        except Exception as e:
            print(f"WARNING: Error adding enum value (may already exist): {e}")

        # 验证枚举值
        result = conn.execute(text("""
            SELECT enumlabel FROM pg_enum
            WHERE enumtypid = 'strategy_type'::regtype
            ORDER BY enumsortorder;
        """))

        print("\nCurrent strategy_type enum values:")
        for row in result:
            print(f"  - {row[0]}")

if __name__ == "__main__":
    migrate()
