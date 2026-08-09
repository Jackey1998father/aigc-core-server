"""
权限节点（节点 1，仅增强模式）

职责：校验用户对所选知识库是否真有权限。
      无权限时在 state["error"] 标错，路由到 END（不进入 retrieval）。
"""
import logging
from typing import List

from langgraph.graph import END

from app.services.kb_service import KnowledgeBaseService
from app.services.rag_graph.state import RAGState

logger = logging.getLogger(__name__)


def permission_node(state: RAGState) -> RAGState:
    """校验用户对所选知识库是否真有权限（无权限的直接 END）"""
    user_id = state["user_id"]
    requested_kbs: List[str] = state.get("kb_ids") or []

    if not requested_kbs:
        return {**state, "error": "未选择任何知识库", "authorized_kb_ids": []}

    owned_ids = {kb.id for kb in KnowledgeBaseService.list_by_user(user_id)}
    authorized = [kb_id for kb_id in requested_kbs if kb_id in owned_ids]

    if not authorized:
        return {**state, "error": "所选知识库均无访问权限", "authorized_kb_ids": []}

    logger.info(
        "[rag.permission] user=%s requested=%d authorized=%d",
        user_id, len(requested_kbs), len(authorized),
    )
    return {**state, "authorized_kb_ids": authorized}


def _route_after_permission(state: RAGState) -> str:
    """permission 节点之后：无权限（error）→ END，否则 → retrieval"""
    return END if state.get("error") else "retrieval"
