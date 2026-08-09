"""
检索节点（节点 2，仅增强模式）

职责：把 kb_ids + query 转成最终发给 LLM 的 context 文本
    1. kb_ids → doc_ids（MySQL）
    2. query 向量化
    3. Milvus 混合召回（BGE 稠密 0.6 + BM25 稀疏 0.4）
    4. Rerank 取 top 5
    5. 通过 child.index_id 反推 parent.index_id
    6. 查父块原文
    7. 拼 context 字符串
"""
import json
import logging
from typing import List, Dict, Any

import httpx
from pymilvus import AnnSearchRequest, WeightedRanker

from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.rag_graph.state import RAGState
from app.store.milvus_client import milvus_client
from app.utils.db import get_cursor

logger = logging.getLogger(__name__)


# ============================================================
# 1. Rerank 工具
# ============================================================
def _rerank(query: str, documents: List[str], top_n: int = 5) -> List[Dict[str, Any]]:
    """
    调用硅基流动 bge-reranker-v2-m3 对召回结果重排。

    Returns:
        [{index, relevance_score}, ...]，按 score 倒序
        失败时按原顺序兜底（score 递减 0.01）
    """
    if not documents:
        return []

    payload = {
        "model": settings.DEFAULT_RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
    }
    headers = {
        "Authorization": f"Bearer {settings.SILICON_FLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(settings.SILICON_FLOW_RERANK_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("[rag.rerank] 调用失败: %s", e)
        # 失败时按原顺序兜底
        return [{"index": i, "relevance_score": 1.0 - i * 0.01} for i in range(len(documents))]

    results = data.get("results") or []
    logger.info("[rag.rerank] query=%s docs=%d → top %d", query[:30], len(documents), len(results))
    return results


# ============================================================
# 2. 检索节点
# ============================================================
def retrieval_node(state: RAGState) -> RAGState:
    """
    1. kb_ids → doc_ids
    2. query 向量化
    3. 混合召回（稠密 0.6 + BM25 0.4，按 doc_id 权限过滤）
    4. Rerank 取 top 5
    5. 通过 child.index_id 反推 parent.index_id
    6. 查父块原文
    7. 拼 context
    """
    if state.get("error"):
        return state

    kb_ids: List[str] = state["authorized_kb_ids"]
    query: str = state["query"]

    # 1. kb_ids → doc_ids（biz_id 字段就是 doc_id）
    with get_cursor() as cursor:
        placeholders = ",".join(["%s"] * len(kb_ids))
        cursor.execute(
            f"SELECT id FROM tj_documents "
            f"WHERE kb_id IN ({placeholders}) AND status = 1",
            tuple(kb_ids),
        )
        doc_ids = [row["id"] for row in cursor.fetchall()]

    if not doc_ids:
        return {**state, "parent_chunks": [], "context": "（所选知识库下暂无文档）"}

    # 2. query 向量化
    try:
        query_vec = EmbeddingService.embed_texts([query])[0]
    except Exception as e:
        logger.error("[rag.retrieval] embedding 失败: %s", e)
        return {**state, "error": f"向量化失败: {e}"}

    # 3. 混合召回（稠密 0.6 + BM25 0.4，按 doc_id 权限过滤）
    try:
        milvus_filter = f'biz_id in {json.dumps(doc_ids)}'
        dense_req = AnnSearchRequest(
            data=[query_vec],
            anns_field="vector",
            param={"metric_type": "COSINE"},
            limit=20,
        )
        # BM25 Function 产出的字段名是 text_sparse
        sparse_req = AnnSearchRequest(
            data=[query],
            anns_field="text_sparse",
            param={"metric_type": "BM25"},
            limit=20,
        )
        search_res = milvus_client.hybrid_search(
            collection_name=settings.MILVUS_BGE_COLLECTION,
            reqs=[dense_req, sparse_req],
            ranker=WeightedRanker(0.6, 0.4),
            limit=20,
            filter=milvus_filter,
            output_fields=["chunk_id", "text", "biz_id", "index_id"],
        )
    except Exception as e:
        logger.error("[rag.retrieval] milvus 混合召回失败: %s", e)
        return {**state, "error": f"向量召回失败: {e}"}

    # 4. 解析结果
    child_matches: List[Dict[str, Any]] = []
    for hit in (search_res[0] if search_res else []):
        entity = hit.get("entity") if isinstance(hit, dict) else getattr(hit, "entity", {})
        if not entity:
            entity = hit if isinstance(hit, dict) else {}

        if hasattr(entity, "get"):
            text = entity.get("text", "")
            chunk_id = entity.get("chunk_id", "")
            biz_id = entity.get("biz_id", "")
            index_id = entity.get("index_id", 0.0)
        else:
            text = getattr(entity, "text", "")
            chunk_id = getattr(entity, "chunk_id", "")
            biz_id = getattr(entity, "biz_id", "")
            index_id = getattr(entity, "index_id", 0.0)

        score = hit.get("distance") if isinstance(hit, dict) else getattr(hit, "distance", 0.0)

        child_matches.append({
            "chunk_id": chunk_id,
            "text": text,
            "biz_id": biz_id,
            "index_id": float(index_id) if index_id else 0.0,
            "score": score,
        })

    if not child_matches:
        return {**state, "parent_chunks": [], "context": "（未召回到相关文档）"}

    # 5. Rerank 取 top 5
    reranked = _rerank(query, [m["text"] for m in child_matches], top_n=5)
    top_children: List[Dict[str, Any]] = []
    for r in reranked:
        idx = r.get("index", -1)
        if 0 <= idx < len(child_matches):
            top_children.append({**child_matches[idx], "rerank_score": r.get("relevance_score", 0.0)})
    if not top_children:
        top_children = child_matches[:5]

    # 6. 反推父块 index_id（splitter: parent.index_id = 1000 * (idx+1)）
    parent_index_ids = {int(c["index_id"] // 1000) * 1000 for c in top_children}

    # 7. 查父块原文
    try:
        parent_res = milvus_client.query(
            collection_name=settings.MILVUS_PARENT_COLLECTION,
            filter=f"index_id in {json.dumps(list(parent_index_ids))}",
            output_fields=["chunk_id", "text", "biz_id", "index_id"],
        )
    except Exception as e:
        logger.error("[rag.retrieval] 父块查询失败: %s", e)
        parent_res = []

    parent_map: Dict[tuple, Dict[str, Any]] = {
        (p.get("biz_id"), int(p.get("index_id", 0))): p for p in parent_res
    }
    parents: List[Dict[str, Any]] = []
    seen: set = set()
    for child in top_children:
        key = (child["biz_id"], int(child["index_id"] // 1000) * 1000)
        parent = parent_map.get(key)
        if parent and parent.get("chunk_id") not in seen:
            parents.append(parent)
            seen.add(parent.get("chunk_id"))

    # 8. 拼 context
    if parents:
        context = "\n\n---\n\n".join(
            f"【参考资料 {i+1}】\n{p.get('text', '')}" for i, p in enumerate(parents)
        )
    else:
        context = "\n\n---\n\n".join(
            f"【片段 {i+1}】\n{c['text']}" for i, c in enumerate(top_children)
        )

    logger.info(
        "[rag.retrieval] query=%s docs=%d children=%d reranked=%d parents=%d",
        query[:30], len(doc_ids), len(child_matches), len(top_children), len(parents),
    )
    return {
        **state,
        "authorized_doc_ids": doc_ids,
        "query_embedding": query_vec,
        "child_matches": child_matches,
        "reranked_matches": top_children,
        "parent_chunks": parents,
        "context": context,
    }
