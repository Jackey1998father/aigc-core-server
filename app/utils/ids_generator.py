"""
UUID 批量生成工具
"""
import uuid


def generate_unique_uuids(count: int, prefix: str = "") -> list[str]:
    """
    批量生成指定数量的 UUID hex 字符串。

    Args:
        count: 生成数量
        prefix: 可选前缀（用于区分不同用途）

    Returns:
        UUID 字符串列表
    """
    return [f"{prefix}{uuid.uuid4().hex}" for _ in range(count)]