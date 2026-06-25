"""
召回接口路由
提供基于 Milvus 的文档召回能力
"""

from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, Query

from app.services.retriever_service import RetrieverService, SearchResult

retriever_router = APIRouter(prefix="/retrieve", tags=["召回服务"])


@retriever_router.post("/query", response_model=List[SearchResult])
async def retrieve_documents(
    request: Request,
    query: str,
    top_k: Optional[int] = Query(5, ge=1, le=50, description="返回结果数量")
):
    """
    召回相关文档
    
    根据用户查询，从 Milvus 向量数据库中召回相似文档
    
    Args:
        query: 用户查询文本
        top_k: 返回的结果数量，默认为 5
    
    Returns:
        召回的文档列表，按相似度排序
    """
    # 获取认证头
    auth_header = request.headers.get("Authorization")
    
    try:
        results = RetrieverService.retrieve(
            query=query,
            top_k=top_k,
            auth_header=auth_header
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@retriever_router.post("/embedding")
async def get_embedding(request: Request, text: str, model: Optional[str] = None):
    """
    获取文本嵌入向量
    
    调用 SiliconFlow 的嵌入模型服务
    
    Args:
        text: 输入文本
        model: 嵌入模型名称，默认使用配置中的模型
    
    Returns:
        嵌入向量
    """
    auth_header = request.headers.get("Authorization")
    
    try:
        embedding = RetrieverService.get_embedding(
            text=text,
            model=model,
            auth_header=auth_header
        )
        return {"embedding": embedding}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))