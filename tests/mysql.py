"""
MySQL 连通性测试

用法：
    python tss/mysql.py

依赖：
    pip install pymysql cryptography
"""
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from app.core.config import settings


def ts_connection() -> bool:
    """测试 MySQL 连接连通性"""
    print("=" * 60)
    print("MySQL 连通性测试")
    print("=" * 60)
    print(f"  Host    : {settings.MYSQL_HOST}")
    print(f"  Port    : {settings.MYSQL_PORT}")
    print(f"  User    : {settings.MYSQL_USER}")
    print(f"  Database: {settings.MYSQL_DATABASE}")
    print("-" * 60)

    try:
        conn = pymysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            connect_timeout=5,
        )
        print("✅ 连接成功！")

        # 测试查询
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"  MySQL 版本: {version[0]}")

        # 查看所有表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"  表数量: {len(tables)}")
        for table in tables:
            print(f"    - {table[0]}")

        cursor.close()
        conn.close()
        return True

    except pymysql.err.OperationalError as e:
        print(f"❌ 连接失败 (OperationalError)")
        print(f"   错误码: {e.args[0]}")
        print(f"   详情: {e.args[1]}")
        return False
    except Exception as e:
        print(f"❌ 连接失败 ({type(e).__name__})")
        print(f"   详情: {e}")
        return False


if __name__ == "__main__":
    ok = ts_connection()
    print("=" * 60)
    if ok:
        print("测试通过 ✅")
    else:
        print("测试失败 ❌")
    sys.exit(0 if ok else 1)
