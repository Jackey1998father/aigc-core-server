from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from app.schemas.demo import DemoResponse, DemoRequest
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.demo_service import DemoService
from app.services.chat_service import chat_sync, chat_stream

v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/health")
def health_check():
    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": "ok"
        }
    }


@v1_router.post("/demo", response_model=DemoResponse)
def echo(req: DemoRequest):
    result = DemoService.echo(req.text)
    return DemoResponse(code=0, message="success", data=result)


# ==================== 对话接口 ====================

@v1_router.post("/chat")
async def chat(req: ChatRequest):
    """
    统一对话接口（兼容流式/非流式）。

    核心设计：
    - 前端传入完整 messages 历史
    - 后端自动保留最近 N 轮（默认 3 轮）+ system prompt
    - 流式输出时返回 SSE 格式
    """
    model = req.model or None  # None 时使用默认模型

    if req.stream:
        return StreamingResponse(
            chat_stream(req.messages, max_rounds=req.max_rounds, model=model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    result = chat_sync(req.messages, max_rounds=req.max_rounds, model=model)
    return JSONResponse(
        content=ChatResponse(code=0, message="success", data=result).model_dump()
    )