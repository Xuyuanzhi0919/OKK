"""激活用户的API配置"""
import psycopg

conn_str = "postgresql://postgres:root@localhost:5433/okk_quant"

with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        # 检查当前配置状态
        cur.execute("SELECT id, user_id, api_key, is_active FROM api_configs WHERE user_id = 1")
        before = cur.fetchone()

        if before:
            print(f"修改前: ID={before[0]}, UserID={before[1]}, APIKey={before[2][:20]}..., Active={before[3]}")
        else:
            print("未找到用户1的API配置!")
            exit(1)

        # 激活配置
        cur.execute("""
            UPDATE api_configs
            SET is_active = true, updated_at = NOW()
            WHERE user_id = 1 AND id = %s
        """, (before[0],))

        conn.commit()

        # 检查修改后的状态
        cur.execute("SELECT id, user_id, api_key, is_active FROM api_configs WHERE user_id = 1")
        after = cur.fetchone()

        print(f"修改后: ID={after[0]}, UserID={after[1]}, APIKey={after[2][:20]}..., Active={after[3]}")
        print("\n✅ API配置已激活!")
