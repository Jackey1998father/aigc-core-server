"""
SiliconFlow GLM-5.1 模型转发路由
支持流式和非流式输出
"""

import json
import time
import uuid
import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.silicon_flow_service import SILICON_FLOW_URL, DEFAULT_MODEL

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
    model = body.get("model", DEFAULT_MODEL)

    # ---------------- 非流式 ----------------
    if not stream:
        resp = requests.post(
            SILICON_FLOW_URL,
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
            SILICON_FLOW_URL,
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
