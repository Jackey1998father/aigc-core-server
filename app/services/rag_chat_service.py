"""
RAG 流式对话入口服务

职责：
    - _resolve_mode：根据 use_rag + kb_ids 决定 mode
    - rag_chat_stream：
        1. 跑 LangGraph（permission + retrieval，快速返回 context）
        2. 拼装 prompt，直接流式调 LLM（OpenAI 原生客户端，非 langchain）
        3. 边生成边 yield SSE chunk（真流式），结束后 DB 落库
        4. 支持 DeepSeek reasoning_content（思考过程）透传

与旧版的关键区别：
    LLM 流式调用已从 answer_node 移到这里，并用 OpenAI 原生客户端替代
    langchain_openai.ChatOpenAI（后者会丢弃 reasoning_content）。
"""
import json
import logging
import time
import uuid
from typing import Generator, Dict, List, Optional

from openai import OpenAI

from app.core.config import settings
from app.services.conversation_service import MessageService
from app.services.rag_graph.state import (
    ENHANCED_SYSTEM_PROMPT,
    MODE_ENHANCED,
    MODE_NORMAL,
    NORMAL_SYSTEM_PROMPT,
    RAGState,
    get_graph,
)

logger = logging.getLogger(__name__)

# OpenAI 客户端缓存（httpx 连接池自动管理并发）
_client_cache: dict = {}


def _get_openai_client() -> OpenAI:
    """获取缓存的 OpenAI 客户端（按 base_url + api_key 缓存）"""
    key = (settings.SILICON_FLOW_URL, settings.SILICON_FLOW_API_KEY)
    if key not in _client_cache:
        base_url = settings.SILICON_FLOW_URL.removesuffix("/chat/completions")
        _client_cache[key] = OpenAI(
            base_url=base_url,
            api_key=settings.SILICON_FLOW_API_KEY or "not-needed",
        )
    return _client_cache[key]


def _mk_chunk(delta: dict, model_name: str, finish_reason=None) -> str:
    """构造一个 SSE data chunk"""
    return f"data: {json.dumps({
        'id': f'chatcmpl-{uuid.uuid4().hex}',
        'object': 'chat.completion.chunk',
        'created': int(time.time()),
        'model': model_name,
        'choices': [{
            'index': 0,
            'delta': delta,
            'finish_reason': finish_reason,
        }],
    }, ensure_ascii=False)}\n\n"


# ============================================================
# 1. 模式判定
# ============================================================
def _resolve_mode(use_rag: bool, kb_ids: List[str]) -> str:
    """根据前端 use_rag + kb_ids 决定实际 mode"""
    if use_rag and kb_ids:
        return MODE_ENHANCED
    return "normal"


# ============================================================
# 2. 错误兜底事件流
# ============================================================
def _error_stream(error_msg: str) -> Generator[str, None, None]:
    """生成一个错误 SSE 事件流（finish_reason=error）"""
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "error",
        "choices": [{
            "index": 0,
            "delta": {"content": f"⚠️ 系统提示：{error_msg}。请稍后重试。"},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    end = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "error",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
    }
    yield f"data: {json.dumps(end, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ============================================================
# 3. 流式入口（真流式 + reasoning_content 透传）
# ============================================================
def rag_chat_stream(
    user_id: str,
    kb_ids: List[str],
    query: str,
    conversation_id: str,
    history: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    thinking: bool = False,
    use_rag: bool = True,
) -> Generator[str, None, None]:
    """
    统一 RAG 流式对话入口（普通/增强模式都走这里）

    流程：
        1. 确定 mode
        2. 跑 LangGraph（增强模式：permission → retrieval，普通模式：直接结束）
        3. 拼装 prompt
        4. 用 OpenAI 原生客户端流式调 LLM，边生成边 yield
           → reasoning_content（思考过程）+ content（回答）都透传
        5. 流结束后 DB 落库
    """
    mode = _resolve_mode(use_rag, kb_ids or [])

    state_in: RAGState = {
        "user_id": user_id,
        "mode": mode,
        "kb_ids": kb_ids or [],
        "query": query,
        "conversation_id": conversation_id,
        "history": history or [],
        "model": model,
        "thinking": thinking,
    }

    # ---- 第 1 步：跑图 ----
    try:
        final = get_graph().invoke(state_in)
    except Exception as e:
        logger.exception("[rag_chat_stream] 图执行失败")
        yield from _error_stream(f"图执行失败: {e}")
        return

    if final.get("error"):
        yield from _error_stream(final["error"])
        return

    # ---- 第 2 步：拼装 prompt ----
    context = final.get("context", "")
    model_name = model or settings.DEFAULT_MODEL

    if mode == MODE_ENHANCED and context:
        system_content = ENHANCED_SYSTEM_PROMPT + f"\n\n【参考资料】\n{context}"
    else:
        system_content = NORMAL_SYSTEM_PROMPT

    prompt_messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    prompt_messages.extend(history or [])
    prompt_messages.append({"role": "user", "content": query})

    logger.info(
        "[rag_chat_stream] conversation=%s model=%s mode=%s thinking=%s kb_ids=%s → 开始流式调用 LLM",
        conversation_id, model_name, mode, thinking, kb_ids or [],
    )

    # ---- 第 3 步：OpenAI 原生客户端流式调用 ----
    client = _get_openai_client()

    # role chunk
    yield _mk_chunk({"role": "assistant"}, model_name)

    full_text = ""
    full_reasoning = ""
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

            if not reasoning and not content:
                continue

            # 组装 delta dict，思考内容 + 回答内容一起发
            delta_dict: Dict[str, str] = {}
            if reasoning:
                full_reasoning += reasoning
                delta_dict["reasoning_content"] = reasoning
            if content:
                full_text += content
                delta_dict["content"] = content

            yield _mk_chunk(delta_dict, model_name)

    except Exception as e:  # noqa: BLE001
        had_error = True
        error_msg = f"{type(e).__name__}: {e}"
        logger.exception("[rag_chat_stream] LLM 调用失败: %s", error_msg)

    if not full_text and had_error:
        full_text = f"⚠️ 模型调用失败：{error_msg}"

    # ---- 第 4 步：DB 落库（只保存最终回答，思考过程不持久化）----
    if full_text:
        try:
            MessageService.save(conversation_id, role="assistant", content=full_text)
        except Exception as e:  # noqa: BLE001
            logger.exception("[rag_chat_stream] 保存 assistant 消息失败: %s", e)

    # ---- 第 5 步：结束 chunk + DONE ----
    yield _mk_chunk({}, model_name, "stop" if not had_error else "error")
    yield "data: [DONE]\n\n"
