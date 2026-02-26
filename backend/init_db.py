"""
数据库初始化脚本
执行方式: python init_db.py

功能:
- 创建所有数据库表结构
- 创建枚举类型
- 创建索引
- 插入默认管理员账户
"""
from sqlalchemy import text
from app.core.database import engine
import re


def init_database():
    """初始化数据库表结构"""
    print("="*60)
    print("OKK Quant System - Database Initialization")
    print("="*60)
    print()

    # 读取完整的 SQL 脚本
    sql_file = "init_complete.sql"

    try:
        with open(sql_file, "r", encoding="utf-8") as f:
            sql_script = f.read()

        # 移除 psql 特有的命令和注释块
        sql_script = re.sub(r'/\*.*?\*/', '', sql_script, flags=re.DOTALL)  # 移除块注释
        sql_script = re.sub(r'COMMENT ON .*?;', '', sql_script)  # 移除注释语句

        # 分割成独立语句
        statements = []
        current_statement = []
        in_do_block = False

        for line in sql_script.split('\n'):
            stripped = line.strip()

            # 跳过空行和单行注释
            if not stripped or stripped.startswith('--'):
                continue

            # 处理 DO 块
            if 'DO $$' in line or 'DO$$' in line.replace(' ', ''):
                in_do_block = True
                current_statement = [line]
                continue

            if in_do_block:
                current_statement.append(line)
                if 'END $$;' in line or 'END$$;' in line.replace(' ', ''):
                    statements.append('\n'.join(current_statement))
                    current_statement = []
                    in_do_block = False
                continue

            # 普通语句
            current_statement.append(line)

            # 检测语句结束
            if stripped.endswith(';'):
                full_statement = '\n'.join(current_statement).strip()
                if full_statement and not full_statement.startswith('SELECT'):
                    statements.append(full_statement)
                current_statement = []

        print(f"Found {len(statements)} SQL statements to execute")
        print()

        success_count = 0
        failed_count = 0
        important_operations = []

        # 逐个执行语句
        for i, statement in enumerate(statements, 1):
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                    success_count += 1

                    # 记录重要操作
                    statement_upper = statement.upper()
                    if 'CREATE TABLE' in statement_upper:
                        table_name = re.search(r'CREATE TABLE.*?(\w+)\s*\(', statement, re.IGNORECASE)
                        if table_name:
                            important_operations.append(f"  [TABLE] {table_name.group(1)}")
                    elif 'CREATE TYPE' in statement_upper:
                        type_name = re.search(r'CREATE TYPE\s+(\w+)', statement, re.IGNORECASE)
                        if type_name:
                            important_operations.append(f"  [TYPE]  {type_name.group(1)}")

            except Exception as e:
                error_msg = str(e)
                # 忽略已存在的错误
                if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                    success_count += 1
                else:
                    failed_count += 1
                    if failed_count <= 3:  # 只显示前3个错误
                        preview = statement[:80].replace('\n', ' ')
                        print(f"[ERROR] {preview}...")
                        print(f"        {error_msg[:100]}")

        print()
        print("="*60)
        print("Execution Summary:")
        print("="*60)
        print(f"Total statements:  {len(statements)}")
        print(f"Successful:        {success_count}")
        print(f"Failed/Skipped:    {failed_count}")
        print()

        if important_operations:
            print("Created Objects:")
            for op in important_operations:
                print(op)
            print()

        # 验证表创建
        print("Verifying database tables...")
        with engine.begin() as conn:
            result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ))
            tables = [row[0] for row in result]

        print(f"Total tables created: {len(tables)}")
        for table in tables:
            print(f"  - {table}")

        print()
        print("="*60)
        print("Initialization completed successfully!")
        print("="*60)
        print()
        print("Default Login Credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print()
        print("Next steps:")
        print("  1. Start backend:  python -m app.main")
        print("  2. Start frontend: npm run dev")
        print("  3. Open browser:   http://localhost:5174")
        print()

    except FileNotFoundError:
        print(f"ERROR: File not found - {sql_file}")
        print("Please ensure you are running this script from the backend directory")
    except Exception as e:
        print(f"ERROR: Initialization failed")
        print(f"Reason: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    init_database()
