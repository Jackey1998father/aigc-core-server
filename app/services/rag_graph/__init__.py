"""
RAG 增强对话：LangGraph 统一编排

包结构（按职责分层）：
    state.py                图状态管理（RAGState、提示词、图构建、单例）
    permission_service.py   权限节点
    retrieval_service.py    检索节点
    model_service.py        模型推理节点（图内流式调 LLM）

外部调用入口（在 app/services/ 下，不在本包内）：
    app/services/rag_chat_service.py   rag_chat_stream 流式入口
                                       （队列 + 后台线程桥接，真流式）

图结构（固定链路：permission + retrieval + answer 全部在图内）：

                       [START]
                          ↓
                                  permission_node
                                    (无权限 → END)
                                          ↓
                                    retrieval_node
                                          ↓
                                    answer_node
                                  (带 context 回答，
                                   context 为空时用普通 prompt 兜底)
                                          ↓
                                       [END]

注：本图仅服务 RAG 增强对话接口（/api/v1/rag/chat），
    普通对话由 /api/v1/chat（chat_v2）直接走 LLM，不进图
"""
# 顶层导出
from app.services.rag_graph.state import (  # noqa: F401
    NORMAL_SYSTEM_PROMPT,
    ENHANCED_SYSTEM_PROMPT,
    RAGState,
    build_rag_graph,
    get_graph,
)

__all__ = [
    "NORMAL_SYSTEM_PROMPT",
    "ENHANCED_SYSTEM_PROMPT",
    "RAGState",
    "build_rag_graph",
    "get_graph",
]
