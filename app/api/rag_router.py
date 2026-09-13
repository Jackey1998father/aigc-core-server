"""
RAG 对话路由（增强模式专用）

挂载路径：/api/v1/rag/chat
固定链路：START → permission → retrieval → answer → END
普通对话由 /api/v1/chat（chat_v2）承担，不走本接口。
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse

from app.schemas.rag import RagChatRequest
from app.services.conversation_service import ConversationService, MessageService
from app.services.model_service import ModelService
from app.services.rag_chat_service import rag_chat_stream
from app.utils.auth_deps import get_current_user


rag_router = APIRouter(prefix="/api/v1/rag", tags=["RAG 对话"])


@rag_router.post("/chat")
def rag_chat(req: RagChatRequest, user_id: str = Depends(get_current_user)):
    """
    RAG 对话（流式 SSE）—— 增强模式专用入口

    请求体：
        conversation_id:  会话 ID
        message:          用户消息
        kb_ids:           要检索的知识库

    流程：
        1. 保存用户消息到 DB
        2. 拉历史
        3. 调 rag_chat_stream()（LangGraph: permission → retrieval → answer）
        4. 流式输出，结束时自动落库 assistant 消息

    注：普通对话请走 /api/v1/chat（chat_v2）
    """
    # 0. 确保会话存在
    title_source = req.message.strip() or "图片对话"
    try:
        ConversationService.ensure_exists(
            req.conversation_id, user_id,
            title=title_source[:50],
        )
    except PermissionError:
        return JSONResponse(
            content={"code": 1, "message": "会话不存在或无权访问"},
            status_code=404,
        )

    # 1. 保存用户消息
    MessageService.save(req.conversation_id, role="user", content=req.message)

    # 2. 拉历史
    limit = req.max_rounds * 2
    history_msgs = MessageService.get_by_conversation(req.conversation_id, user_id, limit=limit)

    # 2.1 首条消息 → 更新标题
    if len(history_msgs) == 1:
        title = title_source[:30] + ("..." if len(title_source) > 30 else "")
        ConversationService.update_title(req.conversation_id, user_id, title)

    history_dicts = [{"role": m.role, "content": m.content} for m in history_msgs]

    # 2.5 模型解析：未传 → 用 tj_models 里配置的默认 chat 模型；传了 → 校验合法性
    model = req.model or None
    if model:
        if ModelService.get_model(model) is None:
            ModelService.refresh()  # 缓存可能滞后，强制重查一次
            if ModelService.get_model(model) is None:
                return JSONResponse(
                    content={"code": 1, "message": f"模型 {model} 不可用或未配置"},
                    status_code=400,
                )
    else:
        model = ModelService.get_default_model_id("chat")

    # 3. 增强模式入口（LangGraph 固定链路：permission → retrieval → answer）
    generator = rag_chat_stream(
        user_id=user_id,
        kb_ids=req.kb_ids,
        query=req.message,
        conversation_id=req.conversation_id,
        history=history_dicts,
        model=model,
        thinking=req.thinking,
        images=req.images,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
        },
    )
