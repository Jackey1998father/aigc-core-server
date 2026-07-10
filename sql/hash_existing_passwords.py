"""
批量哈希数据库中的明文密码。

用法：
    poetry run python sql/hash_existing_passwords.py

说明：
    只处理尚未哈希的密码（不以 $pbkdf2 开头）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.db import get_cursor
from app.utils.password import hash_password


def hash_all_passwords():
    with get_cursor() as cursor:
        cursor.execute("SELECT id, user_id, password FROM aigc_users")
        rows = cursor.fetchall()

    if not rows:
        print("没有需要处理的用户")
        return

    for row in rows:
        pwd = row["password"]
        if pwd and not pwd.startswith("$"):
            hashed = hash_password(pwd)
            with get_cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE aigc_users SET password = %s WHERE id = %s",
                    (hashed, row["id"]),
                )
            print(f"✅ 已哈希 {row['user_id']} 的密码")
        else:
            print(f"⏭️  {row['user_id']} 已哈希，跳过")

    print("\n🎉 处理完成")


if __name__ == "__main__":
    hash_all_passwords()
