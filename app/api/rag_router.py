"""
RAG 对话路由（统一入口）

挂载路径：/api/v1/rag/chat
根据前端 use_rag + kb_ids 走 LangGraph：
    - 普通模式：START → answer → END
    - 增强模式：START → permission → retrieval → answer → END
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.schemas.rag import RagChatRequest
from app.services.conversation_service import ConversationService, MessageService
from app.services.rag_chat_service import rag_chat_stream
from app.utils.auth_deps import get_current_user


rag_router = APIRouter(prefix="/api/v1/rag", tags=["RAG 对话"])


@rag_router.post("/chat")
def rag_chat(req: RagChatRequest, user_id: str = Depends(get_current_user)):
    """
    RAG 对话（流式 SSE）—— 普通/增强模式统一入口

    请求体：
        conversation_id:  会话 ID
        message:          用户消息
        kb_ids:           要检索的知识库（普通模式可空）
        use_rag:          true=增强模式，false=普通模式

    流程：
        1. 保存用户消息到 DB
        2. 拉历史
        3. 调 rag_chat_stream()（内部走 LangGraph 决定路径）
        4. 流式输出，结束时自动落库 assistant 消息
    """
    # 0. 确保会话存在
    ConversationService.ensure_exists(
        req.conversation_id, user_id,
        title=req.message[:50],
    )

    # 1. 保存用户消息
    MessageService.save(req.conversation_id, role="user", content=req.message)

    # 2. 拉历史
    limit = req.max_rounds * 2
    history_msgs = MessageService.get_by_conversation(req.conversation_id, user_id, limit=limit)

    # 2.1 首条消息 → 更新标题
    if len(history_msgs) == 1:
        title = req.message[:30] + ("..." if len(req.message) > 30 else "")
        ConversationService.update_title(req.conversation_id, user_id, title)

    history_dicts = [{"role": m.role, "content": m.content} for m in history_msgs]

    # 3. 统一入口（LangGraph 内部按 use_rag + kb_ids 决定走哪条路）
    generator = rag_chat_stream(
        user_id=user_id,
        kb_ids=req.kb_ids,
        query=req.message,
        conversation_id=req.conversation_id,
        history=history_dicts,
        model=req.model,
        thinking=req.thinking,
        use_rag=req.use_rag,
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
