"""
模型推理节点（节点 3）

职责：
    answer_node 把"检索后返回的块"拼成 prompt，调 LLM 流式收集响应，
    构造 SSE chunks 列表保存到 state["llm_chunks"]，DB 落库。

注：
    - 不 import chat_service
    - LLM 调用、DB 保存、SSE 构造 全部 inline 到本节点
    - answer_node 是同步节点（return state dict），不直接 yield SSE
    - state["llm_chunks"] 里的 SSE 字符串由 @app/services/rag_chat_service.py
      里的 rag_chat_stream 取出后逐条 yield 给客户端
"""
import json
import logging
import time
import uuid
from typing import Dict, List

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings
from app.services.conversation_service import MessageService
from app.services.rag_graph.state import (
    ENHANCED_SYSTEM_PROMPT,
    MODE_ENHANCED,
    MODE_NORMAL,
    NORMAL_SYSTEM_PROMPT,
    RAGState,
)

logger = logging.getLogger(__name__)

# LLM 实例缓存（避免每次新建连接，httpx 连接池自动管理并发）
_llm_cache: dict = {}


def answer_node(state: RAGState) -> RAGState:
    """
    1. 拼装 prompt（普通/增强共用）
    2. 调 LLM 流式收集响应
    3. 构造 SSE chunks 列表（state["llm_chunks"]）
    4. DB 保存 assistant 消息
    5. return state（含 llm_chunks + llm_response_text）
    """
    if state.get("error"):
        return state

    # ============================================================
    # 1. 拼装 prompt
    # ============================================================
    mode = state.get("mode", MODE_NORMAL)
    context = state.get("context", "")
    query = state["query"]
    history: List[Dict[str, str]] = state.get("history") or []
    conversation_id = state["conversation_id"]
    model = state.get("model")
    thinking = state.get("thinking", False)

    if mode == MODE_ENHANCED and context:
        system_content = ENHANCED_SYSTEM_PROMPT + f"\n\n【参考资料】\n{context}"
    else:
        system_content = NORMAL_SYSTEM_PROMPT

    prompt_messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    prompt_messages.extend(history)
    prompt_messages.append({"role": "user", "content": query})

    # ============================================================
    # 2. LLM 实例获取（inline _get_llm 逻辑）
    # ============================================================
    model_name = model or settings.DEFAULT_MODEL
    key = (model_name, thinking)
    if key not in _llm_cache:
        base_url = settings.SILICON_FLOW_URL.removesuffix("/chat/completions")
        _llm_cache[key] = ChatOpenAI(
            base_url=base_url,
            api_key=SecretStr(settings.SILICON_FLOW_API_KEY or "not-needed"),
            model=model_name,
            streaming=True,
            max_retries=1,
            extra_body={"enable_thinking": thinking},
        )
    llm = _llm_cache[key]

    # ============================================================
    # 3. 流式收集 + 构造 SSE chunks
    # ============================================================
    full_text = ""
    chunks: List[str] = []

    def _mk_chunk(delta: dict, finish_reason=None) -> str:
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

    # role chunk
    chunks.append(_mk_chunk({"role": "assistant"}))

    had_error = False
    error_msg = ""
    try:
        for chunk in llm.stream(prompt_messages):
            if chunk.content and isinstance(chunk.content, str):
                full_text += chunk.content
                chunks.append(_mk_chunk({"content": chunk.content}))
    except Exception as e:  # noqa: BLE001 — 必须兜住任何上游异常
        had_error = True
        error_msg = f"{type(e).__name__}: {e}"
        logger.exception("[rag.answer] LLM 调用失败: %s", error_msg)

    if not full_text and had_error:
        full_text = f"⚠️ 模型调用失败：{error_msg}"

    # ============================================================
    # 4. DB 保存
    # ============================================================
    if full_text:
        try:
            MessageService.save(conversation_id, role="assistant", content=full_text)
        except Exception as e:  # noqa: BLE001
            logger.exception("[rag.answer] 保存 assistant 消息失败: %s", e)

    # ============================================================
    # 5. 结束 chunk + DONE（finish_reason 根据是否异常区分）
    # ============================================================
    chunks.append(_mk_chunk({}, "stop" if not had_error else "error"))
    chunks.append("data: [DONE]\n\n")

    return {**state, "llm_chunks": chunks, "llm_response_text": full_text}
