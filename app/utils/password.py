"""
密码哈希工具（pbkdf2_hmac，纯 Python 内置，无需额外依赖）
"""
import hashlib
import secrets


def hash_password(password: str) -> str:
    """
    将明文密码转为哈希字符串。
    格式：$pbkdf2-sha256$iterations$salt$hash
    """
    iterations = 600_000
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"$pbkdf2-sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    验证明文密码是否匹配哈希字符串。
    """
    try:
        _, algorithm, iterations, salt, stored_hash = hashed.split("$")
        iterations = int(iterations)
        dk = hashlib.pbkdf2_hmac(
            algorithm.replace("pbkdf2-", ""),
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return secrets.compare_digest(dk.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False


if __name__ == "__main__":
    # 快速生成密码哈希（用于手动插入数据库）
    import sys
    pwd = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    print(f"明文密码: {pwd}")
    print(f"哈希结果: {hash_password(pwd)}")
