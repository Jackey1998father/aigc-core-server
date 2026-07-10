"""
MySQL 数据库连接池（DBUtils.PooledDB + pymysql）
"""
import pymysql
from contextlib import contextmanager
from dbutils.pooled_db import PooledDB

from app.core.config import settings

# 全局连接池（模块加载时创建，进程内共享）
_pool: PooledDB | None = None


def _get_pool() -> PooledDB:
    """懒加载创建连接池（确保 settings 已加载后再初始化）"""
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,                 # 使用 pymysql 作为连接工厂
            maxconnections=20,               # 池中最大连接数（加大以支持并发）
            mincached=2,                     # 启动时最少空闲连接
            maxcached=10,                    # 池中最多空闲连接
            blocking=True,                   # 连接耗尽时阻塞等待（而非抛异常）
            ping=4,                          # 4=使用连接前先 ping 检查有效性
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            charset="utf8mb4",
            connect_timeout=5,
        )
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    """
    从连接池获取连接 → 创建游标 → 执行操作 → 归还连接。

    用法:
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM aigc_users WHERE id = %s", (1,))
            row = cursor.fetchone()

        with get_cursor(commit=True) as cursor:
            cursor.execute("UPDATE ...")
    """
    pool = _get_pool()
    conn = pool.connection()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        yield cursor
        if commit:
            conn.commit()
    finally:
        cursor.close()
        conn.close()  # PooledDB 的 close() 是将连接归还池中，而非真正关闭
