"""
OpenAIReRank - 自定义重排序类（基于 RESTfulRerankModelHandle）

使用方式：
    from tests.OpenAIReRank import OpenAIReRank
    
    reranker = OpenAIReRank(
        base_url="http://localhost:8000/siliconflow",
        api_key="your-api-key",
        model="BAAI/bge-reranker-v2-m3",
        top_n=4
    )
    
    # 使用 compress_documents 方法重排序文档
    results = reranker.compress_documents(documents, query)
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Union
from pydantic import BaseModel, SecretStr

from langchain_core.documents import Document
from xinference_client.client.restful.restful_client import RESTfulRerankModelHandle


class OpenAIReRank(BaseModel):
    """基于 RESTfulRerankModelHandle 的重排序器（兼容 XinferenceRerank 风格）"""

    base_url: str = "http://localhost:8000/siliconflow"
    api_key: SecretStr = SecretStr("")
    model: str = "BAAI/bge-reranker-v2-m3"
    top_n: int = 4
    threshold: float = 0.0

    @property
    def _model_handle(self) -> RESTfulRerankModelHandle:
        auth_headers = {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json"
        }
        return RESTfulRerankModelHandle(
            model_uid=self.model,
            base_url=self.base_url,
            auth_headers=auth_headers
        )

    def rerank(
        self,
        documents: Sequence[Union[str, Document, dict]],
        query: str,
        *,
        model: Optional[str] = None,
        top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        if len(documents) == 0:
            return {}

        docs = [
            doc.page_content if isinstance(doc, Document) else doc
            for doc in documents
        ]
        model = model or self.model
        top_n = top_n if top_n is not None else self.top_n

        model_handle = self._model_handle
        model_handle._model_uid = model

        return model_handle.rerank(
            documents=docs,
            query=query,
            top_n=top_n,
            return_documents=True
        )

    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        threshold: Optional[float] = None,
    ) -> List[Document]:
        if not documents:
            return []

        rerank_res = self.rerank(documents, query)
        res_list = rerank_res.get("results", [])
        if not res_list:
            return []

        used_threshold = threshold if threshold is not None else self.threshold

        if used_threshold == 0.0:
            res_list = res_list[:self.top_n]

        compressed = []
        for res in res_list:
            score = res.get("relevance_score", 0)
            if used_threshold != 0.0 and score < used_threshold:
                break
            index = res.get("index", 0)
            if index < len(documents):
                doc = documents[index]
                compressed.append(Document(
                    page_content=doc.page_content,
                    metadata={
                        **doc.metadata,
                        "relevance_score": score
                    }
                ))

        return compressed
