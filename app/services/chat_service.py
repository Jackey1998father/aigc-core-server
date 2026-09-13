"""
对话服务：管理 LLM 调用 + 对话上下文窗口

核心设计：
1. V1: 前端传入完整 messages，后端自动裁剪到最近 N 轮
2. V2: 前端只传 conversation_id + 当前消息，后端从 DB 拉历史
3. system 消息始终保留
4. 支持流式/非流式输出
5. 用 OpenAI 原生客户端（非 langchain），支持 DeepSeek reasoning_content 透传
   （仅 thinking=True 时透传；部分推理模型无视 enable_thinking 开关，
    thinking=False 时后端强制丢弃思考内容）
"""

import json
import logging
import time
import uuid
from typing import List, Generator

from openai import OpenAI

from app.core.config import settings
from app.schemas.chat import Message
from app.services.conversation_service import MessageService
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)


# ==================== OpenAI 客户端 ====================

_client_cache: dict = {}


def _get_openai_client(api_key: str | None = None) -> OpenAI:
    """获取缓存的 OpenAI 客户端（按 base_url + api_key 缓存）

    api_key 来自 tj_models 表该模型自己的配置；
    为空则回退后端全局的 SILICON_FLOW_API_KEY。
    """
    effective_key = api_key or settings.SILICON_FLOW_API_KEY
    key = (settings.SILICON_FLOW_URL, effective_key)
    if key not in _client_cache:
        base_url = settings.SILICON_FLOW_URL.removesuffix("/chat/completions")
        _client_cache[key] = OpenAI(
            base_url=base_url,
            api_key=effective_key or "not-needed",
        )
    return _client_cache[key]


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
    system_prompt = system_msgs[-1] if system_msgs else None

    non_system = [m for m in messages if m.role != "system"]

    window_size = max_rounds * 2
    recent = non_system[-window_size:] if len(non_system) > window_size else non_system

    result = []
    if system_prompt:
        result.append(system_prompt.model_dump())

    for m in recent:
        result.append(m.model_dump())

    return result


# ==================== 非流式对话 ====================

def chat_sync(messages: List[Message], max_rounds: int = 3, model: str | None = None) -> dict:
    """非流式调用 LLM"""
    trimmed = trim_messages(messages, max_rounds)
    client = _get_openai_client()
    model_name = model or settings.DEFAULT_MODEL
    response = client.chat.completions.create(
        model=model_name,
        messages=trimmed,  # type: ignore[arg-type]
        stream=False,
        max_tokens=settings.DEFAULT_MAX_TOKENS,
    )
    return {
        "role": "assistant",
        "content": response.choices[0].message.content or "",
    }


# ==================== V1 流式对话（messages 入参） ====================

def _mk_sse_chunk(delta: dict, model_name: str, finish_reason=None) -> str:
    """构造一个 SSE data chunk"""
    return f"data: {json.dumps({
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }, ensure_ascii=False)}\n\n"


def chat_stream(messages: List[Message], max_rounds: int = 3, model: str | None = None) -> Generator[str, None, None]:
    """
    V1 流式调用 LLM，产出 SSE 格式的事件流。
    """
    trimmed = trim_messages(messages, max_rounds)
    client = _get_openai_client()
    model_name = model or settings.DEFAULT_MODEL

    yield _mk_sse_chunk({"role": "assistant"}, model_name)

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=trimmed,  # type: ignore[arg-type]
            stream=True,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue

            reasoning = getattr(delta, "reasoning_content", None) or ""
            content = delta.content or ""

            delta_dict: dict = {}
            if reasoning:
                delta_dict["reasoning_content"] = reasoning
            if content:
                delta_dict["content"] = content
            if delta_dict:
                yield _mk_sse_chunk(delta_dict, model_name)

    except Exception as e:  # noqa: BLE001
        yield _mk_sse_chunk(
            {"content": f"⚠️ 模型调用失败：{type(e).__name__}: {e}"},
            model_name, "error",
        )

    yield _mk_sse_chunk({}, model_name, "stop")
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
    full_reasoning = ""
    model_name = model or settings.DEFAULT_MODEL

    # 从 tj_models 取该模型专属的 api_key（查不到/为空则用全局配置）
    model_cfg = ModelService.get_model(model) if model else None
    model_api_key = (model_cfg or {}).get("api_key") or None
    client = _get_openai_client(model_api_key)

    logger.info(
        "[chat_v2_stream] conversation=%s model=%s thinking=%s → 开始流式调用 LLM",
        conversation_id, model_name, thinking,
    )

    # role chunk
    yield _mk_sse_chunk({"role": "assistant"}, model_name)

    had_error = False
    error_msg = ""

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=prompt_messages,  # type: ignore[arg-type]
            stream=True,
            max_tokens=settings.DEFAULT_MAX_TOKENS,
            extra_body={"enable_thinking": thinking},
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue

            reasoning = getattr(delta, "reasoning_content", None) or ""
            content = delta.content or ""

            # thinking=False 时丢弃思考内容
            # （部分推理模型无视 enable_thinking 开关，仍输出 reasoning_content）
            if not thinking:
                reasoning = ""

            if not reasoning and not content:
                continue

            delta_dict: dict = {}
            if reasoning:
                delta_dict["reasoning_content"] = reasoning
                full_reasoning += reasoning
            if content:
                full_text += content
                delta_dict["content"] = content

            yield _mk_sse_chunk(delta_dict, model_name)

    except Exception as e:  # noqa: BLE001
        had_error = True
        error_msg = f"{type(e).__name__}: {e}"
        logger.exception("[chat_v2_stream] LLM 调用失败: %s", error_msg)

    if not full_text and had_error:
        full_text = f"⚠️ 模型调用失败：{error_msg}"

    # DB 落库
    if full_text:
        try:
            MessageService.save(conversation_id, role="assistant", content=full_text, reasoning=full_reasoning)
        except Exception as e:  # noqa: BLE001
            logger.exception("[chat_v2_stream] 保存 assistant 消息失败: %s", e)

    # 结束 chunk + DONE
    yield _mk_sse_chunk({}, model_name, "stop" if not had_error else "error")
    yield "data: [DONE]\n\n"
