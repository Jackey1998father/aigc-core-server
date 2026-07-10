"""
认证依赖注入

从请求头 Authorization: Bearer <token> 中解析用户标识。
Token 通过 HMAC-SHA256 签名，由 login 接口签发。
"""
from fastapi import Request, HTTPException

from app.utils.token import verify_token


def get_current_user(request: Request) -> str:
    """
    从 Authorization: Bearer <token> 头中解析当前用户。

    返回 user_id 字符串；token 无效或缺失时抛 401。
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或 token 格式错误")

    token = header[7:]  # 去掉 "Bearer " 前缀
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    return user_id
