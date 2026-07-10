from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    user_id: str = Field(..., min_length=1, max_length=50, description="登录工号/账号")
    password: str = Field(..., min_length=1, max_length=100, description="登录密码")


class UserInfo(BaseModel):
    """用户信息（返回给前端）"""
    id: int
    user_id: str
    username: str
    access_token: str | None = None


class LoginResponse(BaseModel):
    """登录响应"""
    code: int = 0
    message: str = "success"
    data: UserInfo | None = None
