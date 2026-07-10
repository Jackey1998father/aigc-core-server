"""
测试 Rerank 接口（使用自定义 OpenAIReRank 类）

前提：确保 aigc-core-server 已启动
默认地址：http://localhost:8000/siliconflow/v1/rerank
"""

import os
from pydantic import SecretStr
from langchain_core.documents import Document
from OpenAIReRank import OpenAIReRank

# API Key
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-lbaejguljpqjckzkqtaybqnjxzzjizfqyijkxfwatbxrglnv")

# 测试地址（根据环境选择）
BASE_URL = "http://localhost:8000/siliconflow"
# BASE_URL = "http://106.14.181.222:8000/siliconflow"


def create_reranker() -> OpenAIReRank:
    """创建 Reranker 实例"""
    return OpenAIReRank(
        base_url=BASE_URL,
        api_key=SecretStr(API_KEY),
        model="BAAI/bge-reranker-v2-m3",
        top_n=4
    )


def val_rerank_basic():
    """测试基础文档重排序"""
    reranker = create_reranker()
    
    query = "Apple"
    documents = [
        Document(page_content="apple", metadata={"source": "fruit.txt"}),
        Document(page_content="banana", metadata={"source": "fruit.txt"}),
        Document(page_content="fruit", metadata={"source": "general.txt"}),
        Document(page_content="vegetable", metadata={"source": "general.txt"}),
    ]
    
    print("测试 OpenAIReRank 类...")
    print(f"查询: {query}")
    print(f"文档数量: {len(documents)}")
    
    results = reranker.compress_documents(documents, query)
    
    print("\n重排序结果:")
    for i, doc in enumerate(results):
        score = doc.metadata.get("relevance_score", 0)
        source = doc.metadata.get("source", "")
        print(f"  {i+1}. '{doc.page_content}' - 相关性: {score:.4f} (来源: {source})")


def val_rerank_top_n():
    """测试 top_n 参数"""
    reranker = OpenAIReRank(
        base_url=BASE_URL,
        api_key=SecretStr(API_KEY),
        model="BAAI/bge-reranker-v2-m3",
        top_n=2  # 只返回前 2 个
    )
    
    query = "What is apple?"
    documents = [
        Document(page_content="apple is a fruit"),
        Document(page_content="banana is yellow"),
        Document(page_content="fruit contains vitamins"),
        Document(page_content="vegetable is healthy"),
        Document(page_content="car is a vehicle"),
    ]
    
    print("\n测试 top_n=2...")
    print(f"查询: {query}")
    
    results = reranker.compress_documents(documents, query)
    
    print(f"返回文档数量: {len(results)}")
    for i, doc in enumerate(results):
        score = doc.metadata.get("relevance_score", 0)
        print(f"  {i+1}. '{doc.page_content}' - 相关性: {score:.4f}")


def val_rerank_threshold():
    """测试 threshold 参数过滤功能"""
    reranker = OpenAIReRank(
        base_url=BASE_URL,
        api_key=SecretStr(API_KEY),
        model="BAAI/bge-reranker-v2-m3",
        top_n=4,
        threshold=0.5  # 类级阈值
    )
    
    query = "Apple"
    documents = [
        Document(page_content="apple", metadata={"source": "fruit.txt"}),
        Document(page_content="banana", metadata={"source": "fruit.txt"}),
        Document(page_content="fruit", metadata={"source": "general.txt"}),
        Document(page_content="vegetable", metadata={"source": "general.txt"}),
    ]
    
    print("\n测试 threshold=0.5（类级）...")
    results = reranker.compress_documents(documents, query)
    print(f"过滤后文档数量: {len(results)}")
    for i, doc in enumerate(results):
        score = doc.metadata.get("relevance_score", 0)
        print(f"  {i+1}. '{doc.page_content}' - 相关性: {score:.4f}")

    # 方法级阈值覆盖
    print("\n测试 threshold=0.9（方法级覆盖）...")
    results = reranker.compress_documents(documents, query, threshold=0.9)
    print(f"过滤后文档数量: {len(results)}")
    for i, doc in enumerate(results):
        score = doc.metadata.get("relevance_score", 0)
        print(f"  {i+1}. '{doc.page_content}' - 相关性: {score:.4f}")

    # threshold=0.0 时只取 top_n，不过滤
    print("\n测试 threshold=0.0（只取 top_n）...")
    results = reranker.compress_documents(documents, query, threshold=0.0)
    print(f"返回文档数量: {len(results)}")
    for i, doc in enumerate(results):
        score = doc.metadata.get("relevance_score", 0)
        print(f"  {i+1}. '{doc.page_content}' - 相关性: {score:.4f}")


def val_rerank_method():
    """测试 rerank 方法返回原始结果"""
    reranker = create_reranker()
    
    query = "Apple"
    documents = [
        Document(page_content="apple", metadata={"source": "fruit.txt"}),
        Document(page_content="banana", metadata={"source": "fruit.txt"}),
    ]
    
    print("\n测试 rerank 方法...")
    result = reranker.rerank(documents, query)
    print(f"返回结果键: {list(result.keys())}")
    if "results" in result:
        for i, res in enumerate(result["results"]):
            print(f"  {i+1}. index={res['index']}, score={res['relevance_score']:.4f}")


if __name__ == "__main__":
    val_rerank_basic()
    val_rerank_top_n()
    val_rerank_threshold()
    val_rerank_method()