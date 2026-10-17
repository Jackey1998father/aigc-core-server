"""
模型推理节点（节点 3）

职责：
    answer_node：
        1. 拼装 prompt（检索到 context 用增强分析型 prompt，
           未检索到用普通 prompt 兜底）
        2. 用 OpenAI 原生客户端流式调 LLM（thinking=True 时透传
           reasoning_content，不用 langchain_openai.ChatOpenAI — 后者会
           丢弃 reasoning_content；thinking=False 时强制丢弃思考内容，
           因为部分推理模型无视 enable_thinking 开关）
        3. 边生成边通过 state["on_chunk"] 回调把 SSE chunk 推给外层（真流式）
        4. DB 落库（保存最终回答 + 思考过程）
        5. return state

注：
    - 本节点仅服务 RAG 增强对话（/api/v1/rag/chat），
      普通对话由 /api/v1/chat 直接流式调 LLM，不经过本图
    - 不 import chat_service / rag_chat_service
    - answer_node 是同步节点（return state dict），SSE 推送靠 on_chunk 回调
    - 节点开头检查 error：权限/检索失败的 state 直接透传，由外层兜底输出错误流
"""
import json
import logging
import time
import uuid
from typing import Callable, Dict, List, Optional

from openai import OpenAI

from app.core.config import settings
from app.services.conversation_service import MessageService
from app.services.model_service import ModelService, DEFAULT_MODEL_IDENTITY_RULE
from app.utils.multimodal import build_user_content
from app.services.rag_graph.state import (
    ENHANCED_SYSTEM_PROMPT,
    NORMAL_SYSTEM_PROMPT,
    RAGState,
)

logger = logging.getLogger(__name__)

# OpenAI 客户端缓存（httpx 连接池自动管理并发）
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


def _extract_source_title(text: str) -> str:
    """从 chunk 文本开头提取文件名（格式：「文件名：xxx」）。"""
    if not text:
        return ""
    first_line = text.lstrip().split("\n", 1)[0].strip()
    prefix = "文件名："
    if first_line.startswith(prefix):
        return first_line[len(prefix):].strip()
    return first_line


def answer_node(state: RAGState) -> RAGState:
    """
    1. 拼装 prompt（普通/增强共用）
    2. OpenAI 原生客户端流式调 LLM，reasoning_content + content 都透传
    3. 每个 chunk 实时通过 state["on_chunk"] 回调推送（真流式）
    4. DB 保存 assistant 消息
    5. return state（含 llm_response_text）
    """
    if state.get("error"):
        return state

    # ============================================================
    # 1. 拼装 prompt
    # ============================================================
    context = state.get("context", "")
    query = state["query"]
    history: List[Dict[str, str]] = state.get("history") or []
    conversation_id: Optional[str] = state.get("conversation_id")
    model = state.get("model")
    thinking = state.get("thinking", False)
    images: List[str] = state.get("images") or []
    on_chunk: Optional[Callable[[str], None]] = state.get("on_chunk")

    # 检索到内容 → 增强分析型 prompt；未检索到 → 普通 prompt 兜底
    if context:
        system_content = ENHANCED_SYSTEM_PROMPT + f"\n\n【参考资料】\n{context}"
    else:
        system_content = NORMAL_SYSTEM_PROMPT

    # 默认模型追加身份保密规则，非默认模型允许暴露底层模型名
    if ModelService.is_default_model(model):
        system_content += "\n\n" + DEFAULT_MODEL_IDENTITY_RULE

    prompt_messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    prompt_messages.extend(history)
    # 视觉模型：query 带图片时转成多模态 content
    prompt_messages.append({"role": "user", "content": build_user_content(query, images)})

    model_name = model or settings.DEFAULT_MODEL

    logger.info(
        "[rag.answer] conversation=%s model=%s has_context=%s thinking=%s → 开始流式调用 LLM",
        conversation_id, model_name, bool(context), thinking,
    )

    # ============================================================
    # 2. 流式调用 + 实时推送 SSE chunk
    # ============================================================
    # 从 tj_models 取该模型专属的 api_key（查不到/为空则用全局配置）
    model_cfg = ModelService.get_model(model) if model else None
    model_api_key = (model_cfg or {}).get("api_key") or None
    client = _get_openai_client(model_api_key)

    def _emit(sse: str) -> None:
        if on_chunk is None:
            return
        try:
            on_chunk(sse)
        except Exception:  # noqa: BLE001 — 回调失败不阻断生成
            logger.exception("[rag.answer] on_chunk 回调失败")

    # role chunk
    _emit(_mk_chunk({"role": "assistant"}, model_name))

    # 检索来源（父块优先，与 context 的「参考资料 N」顺序一致）→ 以 SSE chunk 回传前端展示
    parents = state.get("parent_chunks") or []
    source_items = parents if parents else (state.get("reranked_matches") or [])
    sources = []
    for i, item in enumerate(source_items):
        text = item.get("text", "") if isinstance(item, dict) else ""
        sources.append({"index": i + 1, "title": _extract_source_title(text)})
    if sources:
        _emit(_mk_chunk({"sources": sources}, model_name))

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

            # thinking=False 时丢弃思考内容
            # （部分推理模型无视 enable_thinking 开关，仍输出 reasoning_content）
            if not thinking:
                reasoning = ""

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

            _emit(_mk_chunk(delta_dict, model_name))

    except Exception as e:  # noqa: BLE001 — 必须兜住任何上游异常
        had_error = True
        error_msg = f"{type(e).__name__}: {e}"
        logger.exception("[rag.answer] LLM 调用失败: %s", error_msg)

    if not full_text and had_error:
        full_text = f"⚠️ 模型调用失败：{error_msg}"

    # ============================================================
    # 3. DB 保存（保存最终回答 + 思考过程）
    # ============================================================
    if full_text and conversation_id:
        try:
            MessageService.save(conversation_id, role="assistant", content=full_text, reasoning=full_reasoning)
        except Exception as e:  # noqa: BLE001
            logger.exception("[rag.answer] 保存 assistant 消息失败: %s", e)

    # ============================================================
    # 4. 结束 chunk + DONE（finish_reason 根据是否异常区分）
    # ============================================================
    _emit(_mk_chunk({}, model_name, "stop" if not had_error else "error"))
    _emit("data: [DONE]\n\n")

    return {
        **state,
        "llm_response_text": full_text,
        "llm_had_error": had_error,
    }
