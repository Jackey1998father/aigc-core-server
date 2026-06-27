"""
对话服务：管理 LLM 实例 + 对话上下文窗口

核心设计：
1. 前端传入完整 messages，后端自动裁剪到最近 N 轮
2. system 消息始终保留
3. 支持流式/非流式输出
"""

import json
import time
import uuid
from typing import List, Generator

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings
from app.schemas.chat import Message


# ==================== 上下文窗口裁剪 ====================

def trim_messages(messages: List[Message], max_rounds: int) -> List[dict]:
    """
    裁剪消息列表，保留最近 N 轮对话。

    规则：
    - system 消息始终保留
    - 从末尾开始向前取 max_rounds * 2 条 user/assistant 消息
    - 最终结果按原始顺序排列

    返回：可直接发给 LLM 的 dict 列表
    """
    system_msgs = [m for m in messages if m.role == "system"]
    # 保留最后一条 system 消息（如果有）
    system_prompt = system_msgs[-1] if system_msgs else None

    # 取出所有非 system 消息
    non_system = [m for m in messages if m.role != "system"]

    # 从末尾截取最近 max_rounds * 2 条（1 轮 = user + assistant）
    window_size = max_rounds * 2
    recent = non_system[-window_size:] if len(non_system) > window_size else non_system

    # 构建最终消息列表
    result = []
    if system_prompt:
        result.append(system_prompt.model_dump())

    for m in recent:
        result.append(m.model_dump())

    return result


# ==================== LLM 实例 ====================

def _create_llm(model: str | None = None, streaming: bool = False) -> ChatOpenAI:
    """创建 ChatOpenAI 实例（参照 tests/siliconflow_glm.py 的模式）"""
    return ChatOpenAI(
        base_url=f"{settings.SERVER_BASE_URL}/siliconflow/v1",
        api_key=SecretStr(settings.SILICON_FLOW_API_KEY or "not-needed"),
        model=model or settings.DEFAULT_MODEL,
        streaming=streaming,
    )


# ==================== 非流式对话 ====================

def chat_sync(messages: List[Message], max_rounds: int = 3, model: str | None = None) -> dict:
    """非流式调用 LLM"""
    trimmed = trim_messages(messages, max_rounds)
    llm = _create_llm(model=model, streaming=False)
    response = llm.invoke(trimmed)
    return {
        "role": "assistant",
        "content": response.content,
    }


# ==================== 流式对话（SSE Generator） ====================

def chat_stream(messages: List[Message], max_rounds: int = 3, model: str | None = None) -> Generator[str, None, None]:
    """
    流式调用 LLM，产出 SSE 格式的事件流。
    格式兼容 OpenAI Chat Completion Chunk 规范。
    """
    trimmed = trim_messages(messages, max_rounds)
    llm = _create_llm(model=model, streaming=True)

    model_name = model or settings.DEFAULT_MODEL

    # 先发送 role chunk
    first_chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

    for chunk in llm.stream(trimmed):
        if chunk.content:
            out = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk.content},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    # 结束 chunk
    end_chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
