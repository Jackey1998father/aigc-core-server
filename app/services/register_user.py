"""
手动注册/创建用户脚本

用法：
    poetry run python app/services/register_user.py
    poetry run python app/services/register_user.py admin 张三 123456

如果参数不足则交互式输入。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.db import get_cursor
from app.utils.password import hash_password


def register(user_id: str, username: str, password: str):
    """创建用户（密码自动哈希）"""
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM aigc_users WHERE user_id = %s", (user_id,))
        if cursor.fetchone():
            print(f"❌ 账号 {user_id} 已存在，请更换 user_id")
            return

    hashed = hash_password(password)

    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO aigc_users (user_id, username, password) VALUES (%s, %s, %s)",
            (user_id, username, hashed),
        )

    print(f"\n✅ 用户创建成功！")
    print(f"   账号: {user_id}")
    print(f"   姓名: {username}")
    print(f"   密码: {password}（明文仅供当前确认，数据库已存哈希）")


if __name__ == "__main__":
    if len(sys.argv) == 4:
        # 命令行参数：register_user.py <user_id> <username> <password>
        register(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        # 交互式输入
        print("=" * 40)
        print("AIGC 用户注册")
        print("=" * 40)
        user_id = input("登录账号 (user_id): ").strip()
        username = input("真实姓名 (username): ").strip()
        password = input("登录密码         : ").strip()

        if not user_id or not username or not password:
            print("❌ 所有字段都不能为空")
            sys.exit(1)

        register(user_id, username, password)
