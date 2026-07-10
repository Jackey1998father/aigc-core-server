"""
使用 LangChain 调用本地 Embedding 接口测试

前提：确保 aigc-core-server 已启动
默认地址：http://localhost:8000/v1/embeddings
"""

import os
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

# SiliconFlow API Key
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-lbaejguljpqjckzkqtaybqnjxzzjizfqyijkxfwatbxrglnv")

# 本地代理地址（根据环境选择）
BASE_URL = "http://localhost:8000/siliconflow/v1"  # 本地测试
# BASE_URL = "http://106.14.181.222:8000/siliconflow/v1"  # 阿里云服务器

# 嵌入模型
EMBEDDING_MODEL = "BAAI/bge-m3"


def create_embeddings() -> OpenAIEmbeddings:
    """创建 Embeddings 实例"""
    return OpenAIEmbeddings(
        base_url=BASE_URL,
        api_key=SecretStr(API_KEY),
        model=EMBEDDING_MODEL,
    )


if __name__ == "__main__":
    embeddings = create_embeddings()

    # 测试单条文本嵌入
    text = "Hello, world!"
    print(f"输入文本: {text}")
    print("正在获取嵌入向量...")

    vector = embeddings.embed_query(text)
    print(f"向量维度: {len(vector)}")
    print(f"前5个值: {vector[:5]}")

    # 测试多条文本嵌入
    texts = [
        "这是第一段文本",
        "这是第二段文本",
        "这是第三段文本"
    ]
    print(f"\n批量处理 {len(texts)} 条文本...")

    vectors = embeddings.embed_documents(texts)
    print(f"返回向量数量: {len(vectors)}")
    for i, v in enumerate(vectors):
        print(f"第{i+1}条向量维度: {len(v)}")
