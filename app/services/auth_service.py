"""
登录认证服务
"""
from app.schemas.auth import LoginRequest, UserInfo
from app.utils.db import get_cursor
from app.utils.password import verify_password
from app.utils.token import generate_token


class AuthService:

    @staticmethod
    def login(req: LoginRequest) -> UserInfo:
        """
        验证工号和密码。

        成功：返回 UserInfo（含 access_token）
        失败：抛出 ValueError
        """
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, username, password, status "
                "FROM aigc_users WHERE user_id = %s",
                (req.user_id,),
            )
            row = cursor.fetchone()

        if not row:
            raise ValueError("账号或密码错误")

        if row["status"] != 1:
            raise ValueError("该账号已被禁用，请联系管理员")

        if not verify_password(req.password, row["password"]):
            raise ValueError("账号或密码错误")

        return UserInfo(
            id=row["id"],
            user_id=row["user_id"],
            username=row["username"],
            access_token=generate_token(row["user_id"]),
        )
