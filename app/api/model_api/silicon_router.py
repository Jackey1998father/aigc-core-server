"""
SiliconFlow GLM-5.1 模型转发路由
支持流式和非流式输出
"""

import json
import time
import uuid
import requests
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import settings

silicon_router = APIRouter(prefix="/siliconflow")


def build_chunk(model, content="", role=None, finish_reason=None):
    """构建 OpenAI 格式的 chunk"""
    delta = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }
        ]
    }


@silicon_router.post("/v1/chat/completions")
async def siliconflow_proxy(request: Request):
    """SiliconFlow GLM-5.1 代理接口"""

    body = await request.json()

    # 构建请求头
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }

    stream = body.get("stream", False)
    model = body.get("model", settings.DEFAULT_MODEL)

    # ---------------- 非流式 ----------------
    if not stream:
        resp = requests.post(
            settings.SILICON_FLOW_URL,
            headers=headers,
            json=body,
            timeout=120
        )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return JSONResponse(
            status_code=resp.status_code,
            content=resp.json()
        )

    # ---------------- 流式 ----------------
    def event_stream():
        # 先发送 assistant role chunk
        first_chunk = build_chunk(model=model, role="assistant")
        yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

        resp = requests.post(
            settings.SILICON_FLOW_URL,
            headers=headers,
            json=body,
            stream=True
        )

        if resp.status_code != 200:
            error_chunk = {
                "error": {
                    "message": resp.text,
                    "type": "upstream_error"
                }
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        for line in resp.iter_lines():
            if not line:
                continue

            line = line.decode("utf-8")

            if line.startswith("data:"):
                payload = line[5:].strip()
            else:
                payload = line.strip()

            if payload == "[DONE]":
                break

            try:
                obj = json.loads(payload)
            except:
                continue

            # 提取 content
            content = ""
            try:
                content = obj["choices"][0].get("delta", {}).get("content", "") or ""
            except:
                pass

            # 兜底其他格式
            if not content:
                try:
                    content = obj["choices"][0]["message"].get("content", "")
                except:
                    pass

            if not content:
                continue

            out_chunk = build_chunk(model=model, content=content)
            yield f"data: {json.dumps(out_chunk, ensure_ascii=False)}\n\n"

        # 发送结束 chunk
        end_chunk = build_chunk(model=model, finish_reason="stop")
        yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@silicon_router.post("/v1/embeddings")
async def create_embedding(request: Request):
    """
    创建文本嵌入向量
    
    调用 SiliconFlow 的嵌入模型服务，格式兼容 OpenAI Embeddings API
    
    请求体格式：
    {
        "input": "Hello, world!",
        "model": "BAAI/bge-m3"
    }
    
    返回格式：
    {
        "object": "list",
        "model": "BAAI/bge-m3",
        "data": [
            {
                "object": "embedding",
                "embedding": [...],
                "index": 0
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "total_tokens": 5
        }
    }
    """
    body = await request.json()
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    
    model = body.get("model", settings.DEFAULT_EMBEDDING_MODEL)
    
    payload = {
        "input": body.get("input", ""),
        "model": model
    }
    
    resp = requests.post(
        settings.SILICON_FLOW_EMBEDDING_URL,
        headers=headers,
        json=payload,
        timeout=60
    )
    
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    return resp.json()


@silicon_router.post("/v1/rerank")
async def rerank(request: Request):
    """
    Rerank 重排序接口
    
    调用 SiliconFlow 的 Rerank 模型服务，对召回的文档进行重排序
    
    请求体格式：
    {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "Apple",
        "documents": ["apple", "banana", "fruit", "vegetable"],
        "return_documents": true,
        "top_n": 4
    }
    
    返回格式：
    {
        "results": [
            {
                "index": 0,
                "document": "apple",
                "score": 0.99
            }
        ]
    }
    """
    body = await request.json()
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    
    model = body.get("model", settings.DEFAULT_RERANK_MODEL)
    
    payload = {
        "model": model,
        "query": body.get("query", ""),
        "return_documents": body.get("return_documents", True),
        "top_n": body.get("top_n", 4)
    }
    
    documents = body.get("documents", [])
    if documents and isinstance(documents[0], dict):
        payload["documents"] = [doc.get("text", "") for doc in documents]
    else:
        payload["documents"] = documents
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            settings.SILICON_FLOW_RERANK_URL,
            headers=headers,
            json=payload,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    return resp.json()
