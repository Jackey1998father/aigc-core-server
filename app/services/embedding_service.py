"""
Embedding 服务（对接硅基流动 BGE-m3）
"""
import logging
from typing import List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """调用硅基流动 BGE-m3 embedding 接口"""

    @staticmethod
    def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
        """
        批量文本向量化。

        Args:
            texts: 待向量化的文本列表
            model: 模型名，默认 BAAI/bge-m3

        Returns:
            与 texts 等长的向量列表，每个向量是 1024 维
        """
        if not texts:
            return []

        model = model or settings.DEFAULT_EMBEDDING_MODEL
        url = settings.SILICON_FLOW_EMBEDDING_URL
        headers = {
            "Authorization": f"Bearer {settings.SILICON_FLOW_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": texts,
            "encoding_format": "float",
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("[embedding] 调用失败: %s", e)
            raise

        # 兼容两种返回格式
        embeddings = []
        if "data" in data:
            for item in data["data"]:
                embeddings.append(item.get("embedding") or item.get("vector"))
        elif "embeddings" in data:
            embeddings = data["embeddings"]
        else:
            raise ValueError(f"unexpected embedding response: {list(data.keys())}")

        logger.info(
            "[embedding] batch=%d model=%s dim=%d",
            len(texts), model, len(embeddings[0]) if embeddings else 0,
        )
        return embeddings