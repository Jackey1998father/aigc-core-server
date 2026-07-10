"""
自动执行 MySQL 建表迁移

用法：
    poetry run python sql/migrate.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.db import get_cursor


def run_migration(sql_file: str = "sql/init_users.sql"):
    """执行 SQL 迁移文件"""
    # 相对于项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = os.path.join(project_root, sql_file)

    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # 按分号拆分语句（简单处理，CREATE TABLE 语句自身不能有分号）
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    with get_cursor(commit=True) as cursor:
        for stmt in statements:
            cursor.execute(stmt)
            print(f"✅ 执行: {stmt[:60].replace(chr(10), ' ')}...")

    print("\n🎉 迁移完成！")


if __name__ == "__main__":
    run_migration()
