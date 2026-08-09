"""
RAG 增强对话：LangGraph 统一编排

包结构（按职责分层）：
    state.py                图状态管理（RAGState、常量、提示词、图构建、单例）
    permission_service.py   权限节点（仅增强模式）
    retrieval_service.py    检索节点（仅增强模式）
    model_service.py        模型推理节点（已废弃 — LLM 流式调用已移到 rag_chat_service.py）

外部调用入口（在 app/services/ 下，不在本包内）：
    app/services/rag_chat_service.py   rag_chat_stream 流式入口（含 LLM 实时流式）

图结构（仅负责 permission + retrieval，LLM 调用在图外）：

                       [START]
                          ↓
                (conditional: _route_by_mode)
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
   mode == "normal"                  mode == "enhanced"
        ↓                                   ↓
      [END]                          permission_node
      (图外直接                          ↓
       stream LLM)                (error → END, 否则 → retrieval)
                                          ↓
                                    retrieval_node
                                          ↓
                                       [END]
                                    (图外 stream LLM
                                     带 context)
"""
# 顶层导出
from app.services.rag_graph.state import (  # noqa: F401
    MODE_NORMAL,
    MODE_ENHANCED,
    NORMAL_SYSTEM_PROMPT,
    ENHANCED_SYSTEM_PROMPT,
    RAGState,
    build_rag_graph,
    get_graph,
)

__all__ = [
    "MODE_NORMAL",
    "MODE_ENHANCED",
    "NORMAL_SYSTEM_PROMPT",
    "ENHANCED_SYSTEM_PROMPT",
    "RAGState",
    "build_rag_graph",
    "get_graph",
]
