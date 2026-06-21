import json
import time
import uuid
import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

self_model_router = APIRouter(prefix="/models")

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def build_chunk(model, content="", role=None, finish_reason=None):
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


@self_model_router.post("/v1/chat/completions")
async def openai_proxy(request: Request):

    body = await request.json()

    headers = {
        "Authorization": request.headers.get("Authorization"),
        "Content-Type": "application/json"
    }

    stream = body.get("stream", False)
    model = body.get("model", "qwen-plus")

    # ---------------- 非流式 ----------------
    if not stream:

        resp = requests.post(
            DASHSCOPE_URL,
            headers=headers,
            json=body,
            timeout=120
        )

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
            DASHSCOPE_URL,
            headers=headers,
            json=body,
            stream=True
        )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        for line in resp.iter_lines():

            if not line:
                continue

            line = line.decode("utf-8")

            # 打印调试
            print("RAW:", line)

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

            content = ""

            # OpenAI格式
            try:
                content = obj["choices"][0].get("delta", {}).get("content", "") or ""
            except:
                pass

            # DashScope格式
            if not content:
                try:
                    content = obj["choices"][0]["message"].get("content", "")
                except:
                    pass

            if not content:
                continue

            out_chunk = build_chunk(model=model, content=content)

            yield f"data: {json.dumps(out_chunk, ensure_ascii=False)}\n\n"

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