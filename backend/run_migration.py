"  ✅ 成功: {statement[:80]}..."
                    print(f"  ❌ 失败: {e}")
                    # Fixed: Removed replace('\n', ' ')
                    print(f"     SQL: {statement[:120]}...")
                    file_has_failures = True
                    failed_statements += 1
            
            if not file_has_failures:
                successful_migrations += 1
                print(f"--- 文件 {filename} 执行完毕 (成功) ---")
            else:
                print(f"--- 文件 {filename} 执行完毕 (包含失败) ---")

        conn.commit()
        print("\n=== 数据库迁移结果 ===")
        print(f"✅ 成功执行文件数: {successful_migrations} (指没有语句失败的文件)")
        print(f"❌ 失败语句总数: {failed_statements}")
        if failed_statements == 0:
            print("🎉 所有迁移成功完成！")
        else:
            print("⚠️ 某些迁移语句执行失败，请检查日志。 ")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行数据库迁移脚本")
    parser.add_argument(
        "--database_url",
        type=str,
        help="数据库连接字符串"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用SQLAlchemy的echo模式，打印所有执行的SQL语句"
    )
    args = parser.parse_args()

    run_migrations(args.database_url, args.debug)