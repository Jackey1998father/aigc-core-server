"""
使用 LangChain 调用本地 SiliconFlow GLM-5.1 模型接口

前提：确保 aigc-core-server 已启动
默认地址：http://localhost:8000/siliconflow/v1/chat/completions
"""

import os
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# SiliconFlow API Key
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-lbaejguljpqjckzkqtaybqnjxzzjizfqyijkxfwatbxrglnv")

# 本地代理地址
BASE_URL = "http://106.14.181.222:8000/siliconflow/v1"

MODEL = "zai-org/GLM-5.2"


def create_llm(streaming: bool = False) -> ChatOpenAI:
    """创建 LLM 实例"""
    return ChatOpenAI(
        base_url=BASE_URL,
        api_key=SecretStr(API_KEY),
        model=MODEL,
        streaming=streaming,
    )


if __name__ == "__main__":
    llm = create_llm(streaming=True)

    messages = [
        {"role": "system", "content": "你是锦点餐饮公司的RAG的回答助手"},
        {"role": "user", "content": "请详细介绍一下你自己"}
    ]

    print("回复: ", end="", flush=True)
    for chunk in llm.stream(messages):
        if chunk.content:
            print(chunk.content, end="", flush=True)
    print()
