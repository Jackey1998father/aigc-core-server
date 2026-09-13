"""
RAG 流式对话入口服务

职责：
    - rag_chat_stream：
        1. 后台线程跑 LangGraph 固定链路
           START → permission → retrieval → answer → END
        2. 图内 answer_node 拼装 prompt、流式调 LLM、DB 落库，
           通过 state["on_chunk"] 回调把 SSE chunk 实时推进队列
        3. 本 generator 从队列边读边 yield（真流式，保持低首字延迟），
           reasoning_content（思考过程）+ content 都透传

注：
    - 本入口仅服务 RAG 增强对话接口（/api/v1/rag/chat），
      普通对话由 /api/v1/chat（chat_v2_stream）直接走 LLM，不进图
    - prompt 拼装 / LLM 调用 / DB 落库均在图内 answer_node
      （app/services/rag_graph/model_service.py）完成，本文件只负责
      队列桥接和图级错误兜底
"""
import json
import logging
import queue
import threading
import time
import uuid
from typing import Dict, Generator, List, Optional

from app.services.rag_graph.state import RAGState, get_graph

logger = logging.getLogger(__name__)


# ============================================================
# 1. 错误兜底事件流
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
# 2. 流式入口（队列桥接，真流式）
# ============================================================
def rag_chat_stream(
    user_id: str,
    kb_ids: List[str],
    query: str,
    conversation_id: str,
    history: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    thinking: bool = False,
    images: Optional[List[str]] = None,
) -> Generator[str, None, None]:
    """
    RAG 增强流式对话入口

    流程：
        1. 后台线程跑 LangGraph 固定链路（permission → retrieval → answer）
        2. answer_node 边生成边通过 on_chunk 回调把 SSE chunk 推进队列
        3. 本 generator 从队列边读边 yield，图级错误兜底输出错误流
    """
    # SSE chunk 队列：answer_node（生产者，图内后台线程）→ 本 generator（消费者）
    chunk_q: "queue.Queue[Optional[str]]" = queue.Queue()

    def on_chunk(sse: str) -> None:
        chunk_q.put(sse)

    state_in: RAGState = {
        "user_id": user_id,
        "kb_ids": kb_ids or [],
        "query": query,
        "conversation_id": conversation_id,
        "history": history or [],
        "model": model,
        "thinking": thinking,
        "images": images or [],
        "on_chunk": on_chunk,
    }

    # 图执行结果容器（后台线程写，主线程在队列排空后读）
    holder: Dict[str, object] = {}

    def _run_graph() -> None:
        try:
            holder["final"] = get_graph().invoke(state_in)
        except Exception as e:  # noqa: BLE001
            logger.exception("[rag_chat_stream] 图执行失败")
            holder["graph_error"] = f"图执行失败: {e}"
        finally:
            chunk_q.put(None)  # 结束信号

    worker = threading.Thread(target=_run_graph, daemon=True)
    worker.start()

    # ---- 边收边发（真流式）----
    while True:
        item = chunk_q.get()
        if item is None:
            break
        yield item

    # ---- 图级错误兜底 ----
    if "graph_error" in holder:
        yield from _error_stream(str(holder["graph_error"]))
        return

    final = holder.get("final") or {}
    if final.get("error"):
        yield from _error_stream(final["error"])
        return
