"""
召回服务模块
基于 Milvus 向量数据库实现文档召回
"""

import json
import requests
from typing import List, Dict, Optional, Any
from pydantic import BaseModel

from app.core.config import settings


class EmbeddingResponse(BaseModel):
    """嵌入模型响应结构"""
    object: str
    model: str
    data: List[Dict[str, Any]]
    usage: Dict[str, int]


class SearchResult(BaseModel):
    """召回结果结构"""
    id: str
    content: str
    score: float
    metadata: Optional[Dict[str, Any]] = None


class RetrieverService:
    """召回服务"""

    @staticmethod
    def get_embedding(text: str, model: Optional[str] = None, auth_header: Optional[str] = None) -> List[float]:
        """
        获取文本的嵌入向量
        
        通过调用本服务的 embedding 接口获取嵌入向量
        
        Args:
            text: 输入文本
            model: 嵌入模型名称，默认使用配置中的 DEFAULT_EMBEDDING_MODEL
            auth_header: 认证头
        
        Returns:
            嵌入向量列表
        """
        model = model or settings.DEFAULT_EMBEDDING_MODEL
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if auth_header:
            headers["Authorization"] = auth_header

        payload = {
            "input": text,
            "model": model
        }

        # 调用本服务的 embedding 接口
        resp = requests.post(
            f"{settings.SERVER_BASE_URL}/siliconflow/v1/embeddings",
            headers=headers,
            json=payload,
            timeout=60
        )

        if resp.status_code != 200:
            raise Exception(f"Embedding API error: {resp.text}")

        result = resp.json()
        return result["data"][0]["embedding"]

    @staticmethod
    def search_similar(query_embedding: List[float], top_k: int = 5) -> List[SearchResult]:
        """
        在 Milvus 中搜索相似文档
        
        Args:
            query_embedding: 查询向量
            top_k: 返回的结果数量
        
        Returns:
            搜索结果列表
        """
        try:
            from pymilvus import connections, Collection, utility
            
            # 建立连接
            conn_params = {
                "host": settings.MILVUS_HOST,
                "port": settings.MILVUS_PORT
            }
            
            if settings.MILVUS_USER and settings.MILVUS_PASSWORD:
                conn_params["user"] = settings.MILVUS_USER
                conn_params["password"] = settings.MILVUS_PASSWORD
            
            connections.connect("default", **conn_params)
            
            # 检查集合是否存在
            if not utility.has_collection(settings.MILVUS_COLLECTION_NAME):
                return []
            
            # 加载集合
            collection = Collection(settings.MILVUS_COLLECTION_NAME)
            collection.load()
            
            # 执行搜索
            search_params = {
                "metric_type": "IP",  # Inner Product
                "params": {"nprobe": 10}
            }
            
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "metadata"]
            )
            
            # 解析结果
            search_results = []
            for hit in results[0]:
                metadata = hit.entity.get("metadata")
                if metadata and isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = None
                
                search_results.append(SearchResult(
                    id=hit.id,
                    content=hit.entity.get("content", ""),
                    score=hit.score,
                    metadata=metadata
                ))
            
            # 释放集合
            collection.release()
            
            return search_results
            
        except ImportError:
            raise Exception("Milvus SDK not installed. Please install pymilvus.")
        except Exception as e:
            raise Exception(f"Milvus search error: {str(e)}")

    @staticmethod
    def retrieve(query: str, top_k: int = 5, auth_header: Optional[str] = None) -> List[SearchResult]:
        """
        完整的召回流程：获取嵌入向量 -> 搜索相似文档
        
        Args:
            query: 用户查询文本
            top_k: 返回结果数量
            auth_header: 认证头
        
        Returns:
            召回结果列表
        """
        # 获取查询向量
        query_embedding = RetrieverService.get_embedding(query, auth_header=auth_header)
        
        # 搜索相似文档
        results = RetrieverService.search_similar(query_embedding, top_k)
        
        return results