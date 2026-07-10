"""
对话服务：管理 LLM 实例 + 对话上下文窗口

核心设计：
1. V1: 前端传入完整 messages，后端自动裁剪到最近 N 轮
2. V2: 前端只传 conversation_id + 当前消息，后端从 DB 拉历史
3. system 消息始终保留
4. 支持流式/非流式输出
"""

import json
import time
import uuid
from typing import List, Generator

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings
from app.schemas.chat import Message
from app.services.conversation_service import MessageService


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

# 全局缓存：复用 ChatOpenAI 客户端，避免每次请求都新建连接和 SSL 握手
_llm_cache: dict = {}


def _get_llm(model: str | None = None, streaming: bool = False, max_retries: int = 1, thinking: bool = False) -> ChatOpenAI:
    """获取缓存的 ChatOpenAI 实例（线程安全复用，httpx 连接池自动管理并发）"""
    key = (model or settings.DEFAULT_MODEL, streaming, thinking)
    if key not in _llm_cache:
        base_url = settings.SILICON_FLOW_URL.removesuffix("/chat/completions")
        _llm_cache[key] = ChatOpenAI(
            base_url=base_url,
            api_key=SecretStr(settings.SILICON_FLOW_API_KEY or "not-needed"),
            model=key[0],
            streaming=streaming,
            max_retries=max_retries,
            extra_body={"enable_thinking": thinking},
        )
    return _llm_cache[key]


# ==================== 非流式对话 ====================

def chat_sync(messages: List[Message], max_rounds: int = 3, model: str | None = None) -> dict:
    """非流式调用 LLM"""
    trimmed = trim_messages(messages, max_rounds)
    llm = _get_llm(model=model, streaming=False)
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
    llm = _get_llm(model=model, streaming=True)

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


# ==================== V2 流式对话（基于 DB 会话管理） ====================

def chat_v2_stream(
    conversation_id: str,
    prompt_messages: List[dict],
    model: str | None = None,
    thinking: bool = False,
) -> Generator[str, None, None]:
    """
    V2 流式对话：输出 SSE 并在流结束后自动保存 assistant 消息到 DB。

    Args:
        conversation_id: 会话 ID
        prompt_messages: 构造好的完整 messages（system + history + 新消息）
        model: 模型名称
        thinking: 是否开启深度思考模式
    """
    full_text = ""
    model_name = model or settings.DEFAULT_MODEL
    llm = _get_llm(model=model, streaming=True, thinking=thinking)

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

    # 关键：必须保证 [DONE] 一定会发出，否则前端 reader.read() 会永久阻塞。
    # 任何异常/中断分支都要走 finally 里的结束逻辑。
    had_error = False
    error_msg = ""
    try:
        for chunk in llm.stream(prompt_messages):
            if chunk.content and isinstance(chunk.content, str):
                full_text += chunk.content
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
    except Exception as e:  # noqa: BLE001 — 必须兜住任何上游异常
        had_error = True
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[CHAT V2 ERROR] conversation_id={conversation_id}, {error_msg}")

    # 流结束（正常或异常）后保存 assistant 消息到 DB
    # 即便内容为空也写一条占位，避免下次提问历史里"丢消息"
    if not full_text and had_error:
        full_text = f"⚠️ 模型调用失败：{error_msg}"
    if full_text:
        try:
            MessageService.save(conversation_id, role="assistant", content=full_text)
        except Exception as e:  # noqa: BLE001
            print(f"[CHAT V2 SAVE ERROR] conversation_id={conversation_id}, {e!r}")

    # 结束 chunk（finish_reason 根据是否异常区分）
    end_chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop" if not had_error else "error",
            }
        ],
    }
    yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
