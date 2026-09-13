"""
多模态消息构建工具

视觉模型（Qwen-VL / DeepSeek-VL 等）的 OpenAI 兼容接口要求：
当用户消息带图片时，content 不能是纯字符串，而是一个 parts 列表：
    [{"type": "text", "text": "..."},
     {"type": "image_url", "image_url": {"url": "..."}}]

图片 url 支持：
    - data URL（前端把图片读成 base64 直接塞进来，最省事）
    - http(s) 公网 URL（上游视觉模型能直接拉取的地址）
"""
from typing import List, Union


def build_user_content(text: str, images: List[str]) -> Union[str, List[dict]]:
    """
    构造一条 user 消息的 content。

    无图片 → 返回纯文本（保持原有行为，兼容纯文本模型）
    有图片 → 返回多模态 parts 列表（视觉模型用）
    """
    if not images:
        return text

    parts: List[dict] = [{"type": "text", "text": text}]
    for url in images:
        if not url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts
