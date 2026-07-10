from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse

from app.schemas.demo import DemoResponse, DemoRequest
from app.schemas.chat import ChatV2Request
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationDetailResponse,
    DeleteResponse,
    MessageListResponse,
)
from app.services.demo_service import DemoService
from app.services.chat_service import chat_v2_stream
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService, MessageService
from app.utils.auth_deps import get_current_user

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


# ==================== 登录接口 ====================

@v1_router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """
    用户登录接口。

    验证用户名和密码，成功返回用户信息。
    密码使用 pbkdf2_hmac 哈希存储，不保存明文。
    """
    try:
        user = AuthService.login(req)
        return LoginResponse(code=0, message="登录成功", data=user)
    except ValueError as e:
        return LoginResponse(code=1, message=str(e), data=None)


# ==================== 对话接口（V2 - 基于 DB 会话管理） ====================

SYSTEM_PROMPT = (
    "你是锦点餐饮公司的智能回答助手。"
    "请严格根据用户的最新一条消息回答，不要重复之前已经说过的内容，也不要被历史话题带偏；"
    "如果用户的问题与餐饮无关，先简单回应用户的问题，再自然引导回锦点餐饮相关话题。"
)


@v1_router.post("/chat")
def chat_v2(req: ChatV2Request, user_id: str = Depends(get_current_user)):
    """
    V2 对话接口（流式 SSE），基于 DB 会话管理。

    流程：
    1. 保存用户消息到 DB
    2. 从 DB 读取历史消息（最近 N 轮）
    3. 拼接 system_prompt + history → 流式调用 LLM
    4. 流结束后自动保存 assistant 消息
    """
    model = req.model or None

    # 0. 确保会话存在（首次消息兜底创建）
    ConversationService.ensure_exists(
        req.conversation_id, user_id,
        title=req.message[:50],  # 用首条消息前50字做标题
    )

    # 1. 保存用户消息
    MessageService.save(req.conversation_id, role="user", content=req.message)

    # 2. 从 DB 读取历史消息
    limit = req.max_rounds * 2  # N 轮 = N*2 条
    history = MessageService.get_by_conversation(req.conversation_id, user_id, limit=limit)

    # 2.1 首条消息：用消息内容更新会话标题
    if len(history) == 1:
        title = req.message[:30] + ("..." if len(req.message) > 30 else "")
        ConversationService.update_title(req.conversation_id, user_id, title)

    # 3. 拼接 messages
    prompt_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        prompt_messages.append({"role": m.role, "content": m.content})

    # DEBUG: 打印最终传给模型的 prompt，方便排查上下文问题
    import json as _json
    print(f"[CHAT DEBUG] conversation_id={req.conversation_id}, messages={_json.dumps(prompt_messages, ensure_ascii=False)}")

    # 4. 流式返回（assistant 消息在生成器内部自动落库）
    return StreamingResponse(
        chat_v2_stream(req.conversation_id, prompt_messages, model=model, thinking=req.thinking),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁止 nginx/代理缓冲
            "Transfer-Encoding": "chunked",
        },
    )


# ==================== 会话管理接口 ====================

@v1_router.get("/conversations")
def list_conversations(user_id: str = Depends(get_current_user)):
    """获取当前用户的所有会话列表（按 updated_at 倒序）"""
    items = ConversationService.list_by_user(user_id)
    return ConversationListResponse(data=items).model_dump()


@v1_router.post("/conversations")
def create_conversation(
    req: ConversationCreateRequest,
    user_id: str = Depends(get_current_user),
):
    """创建新会话"""
    item = ConversationService.create(user_id, req.title)
    # 创建完成后查出完整字段（含时间）
    return ConversationDetailResponse(data=item).model_dump()


@v1_router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    user_id: str = Depends(get_current_user),
):
    """删除会话（CASCADE 自动删除关联消息）"""
    ok = ConversationService.delete(conv_id, user_id)
    if not ok:
        return JSONResponse(
            content={"code": 1, "message": "会话不存在或无权操作"},
            status_code=404,
        )
    return DeleteResponse().model_dump()


# ==================== 消息查询接口 ====================

@v1_router.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
):
    """获取指定会话的所有消息（按时间升序）"""
    messages = MessageService.get_by_conversation(conversation_id, user_id, limit=200)
    return MessageListResponse(data=messages).model_dump()