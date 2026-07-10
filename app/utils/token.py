"""
Token 工具：基于 HMAC-SHA256 的签名 token（无额外依赖）
"""
import base64
import hashlib
import hmac
import time

from app.core.config import settings


def generate_token(user_id: str) -> str:
    """
    生成签名的认证 token。

    格式: base64(user_id : timestamp : signature)
    有效期 7 天（由验证方检查时间戳）。
    """
    ts = str(int(time.time()))
    payload = f"{user_id}:{ts}"
    sig = _sign(payload)
    token = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_token(token: str) -> str | None:
    """
    验证 token 并返回 user_id。
    
    验证失败（签名不匹配、格式错误）返回 None。
    不在此处检查过期，调用方可自行判断。
    """
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.rsplit(":", 2)  # user_id : timestamp : signature
        if len(parts) != 3:
            return None
        user_id, ts, sig = parts
        payload = f"{user_id}:{ts}"
        expected = _sign(payload)
        if not hmac.compare_digest(sig, expected):
            return None
        return user_id
    except Exception:
        return None


def _sign(payload: str) -> str:
    """对 payload 做 HMAC-SHA256 签名"""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
