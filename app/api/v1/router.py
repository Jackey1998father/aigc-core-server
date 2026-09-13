from fastapi import APIRouter, Depends, UploadFile, File, Form
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
from app.schemas.kb import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseDetailResponse,
)
from app.schemas.document import DocumentListResponse, DocumentDetailResponse
from app.schemas.model import ModelItem, ModelListResponse
from app.services.demo_service import DemoService
from app.services.chat_service import chat_v2_stream
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService, MessageService
from app.services.kb_service import KnowledgeBaseService
from app.services.document_service import DocumentService
from app.services.model_service import ModelService, DEFAULT_MODEL_IDENTITY_RULE
from app.utils.auth_deps import get_current_user
from app.utils.multimodal import build_user_content

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
    "你是锦点 AI 大模型，是锦点餐饮管理有限公司旗下的智能助手。"
    "你擅长团餐运营、中央厨房管理、菜品管理、餐饮供应链、食品安全、采购配送、客户服务、企业制度等餐饮领域相关问题。"
    "当用户咨询这些业务问题时，请优先依据公司提供的知识库、业务资料和制度文件进行准确、专业的回答；"
    "涉及具体业务细节时，以知识库资料为准，不要凭空编造。"
    "\n\n"
    "除了餐饮业务，你也能友好、认真地回答日常生活中的各类问题，帮助用户解决工作、学习、生活等方面的疑问。"
    "回答日常问题时保持专业、清晰、易懂，像一名博学又亲切的助手。"
    "\n\n"
    "你需要结合当前对话上下文理解用户意图，始终以用户最新一条消息为核心，不要机械重复之前已经回答过的内容。"
    "如果用户的问题存在指代不清、信息不足的情况，可以结合历史上下文合理推断；仍无法确定时，主动向用户询问必要信息。"
    "\n\n"
    "安全边界（必须遵守）："
    "如果用户请求涉及游戏、赌博、色情、暴力、违法或其他不当内容，请明确拒绝回答，"
    "并引导用户回到合法、健康、与餐饮业务或日常生活相关的主题。"
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
    # 模型解析：未传 → 用 tj_models 里配置的默认 chat 模型；传了 → 校验合法性
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

    # 0. 确保会话存在（首次消息兜底创建，会话 ID 不存在时用该 ID 直接创建）
    #    纯图片输入（message 为空）时，标题回退为"图片对话"
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

    # 2. 从 DB 读取历史消息
    limit = req.max_rounds * 2  # N 轮 = N*2 条
    history = MessageService.get_by_conversation(req.conversation_id, user_id, limit=limit)

    # 2.1 首条消息：用消息内容更新会话标题
    if len(history) == 1:
        title = title_source[:30] + ("..." if len(title_source) > 30 else "")
        ConversationService.update_title(req.conversation_id, user_id, title)

    # 3. 拼接 messages（默认模型追加身份保密规则，非默认模型允许暴露底层模型名）
    system_content = SYSTEM_PROMPT
    if ModelService.is_default_model(model):
        system_content += "\n\n" + DEFAULT_MODEL_IDENTITY_RULE
    prompt_messages = [{"role": "system", "content": system_content}]
    for m in history:
        prompt_messages.append({"role": m.role, "content": m.content})

    # 3.1 视觉模型：把图片挂到当前这条 user 消息上（history 最后一条即刚保存的当前消息）
    if req.images and prompt_messages and prompt_messages[-1]["role"] == "user":
        prompt_messages[-1]["content"] = build_user_content(
            prompt_messages[-1]["content"], req.images
        )

    # DEBUG: 打印最终传给模型的 prompt，方便排查上下文问题
    #        （图片 data URL 很长，只打印角色/文本 + 图片数量，避免刷屏）
    import json as _json
    _debug_msgs = []
    for _m in prompt_messages:
        _c = _m.get("content")
        if isinstance(_c, list):
            _texts = [p.get("text", "") for p in _c if p.get("type") == "text"]
            _n_img = sum(1 for p in _c if p.get("type") == "image_url")
            _debug_msgs.append({"role": _m["role"], "content": " ".join(_texts), "images": _n_img})
        else:
            _debug_msgs.append({"role": _m["role"], "content": _c})
    print(f"[CHAT DEBUG] conversation_id={req.conversation_id}, messages={_json.dumps(_debug_msgs, ensure_ascii=False)}")

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


# ==================== 模型配置接口 ====================

@v1_router.get("/models", response_model=ModelListResponse)
def list_models(
    model_type: str = "chat",
    user_id: str = Depends(get_current_user),
):
    """
    获取可用模型列表（默认返回 chat 类型）。

    数据来自 tj_models 表（enabled=1），带 60s 进程内缓存，
    高并发下不会打爆 DB。model_type 可选 chat / embedding / rerank。
    """
    rows = ModelService.list_models(model_type)
    items = [
        # ⚠️ 显式字段构造：rows 里含 api_key（后端内部用），绝不能带进响应
        ModelItem(
            model_id=r["model_id"],
            name=r["name"],
            model_type=r["model_type"],
            provider=r["provider"],
            max_tokens=r["max_tokens"],
            is_default=bool(r["is_default"]),
            description=r.get("description") or None,
        )
        for r in rows
    ]
    return ModelListResponse(data=items)


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


# ==================== 知识库管理接口 ====================

@v1_router.post("/knowledge-bases")
def create_kb(
    req: KnowledgeBaseCreateRequest,
    user_id: str = Depends(get_current_user),
):
    """创建知识库"""
    item = KnowledgeBaseService.create(user_id, req.name, req.description)
    return KnowledgeBaseDetailResponse(data=item).model_dump()


@v1_router.get("/knowledge-bases")
def list_kb(user_id: str = Depends(get_current_user)):
    """获取当前用户的所有知识库列表"""
    items = KnowledgeBaseService.list_by_user(user_id)
    return KnowledgeBaseListResponse(data=items).model_dump()


@v1_router.get("/knowledge-bases/{kb_id}")
def get_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user),
):
    """获取单个知识库详情"""
    item = KnowledgeBaseService.get_by_id(kb_id, user_id)
    if not item:
        return JSONResponse(
            content={"code": 1, "message": "知识库不存在或无权访问"},
            status_code=404,
        )
    return KnowledgeBaseDetailResponse(data=item).model_dump()


@v1_router.put("/knowledge-bases/{kb_id}")
def update_kb(
    kb_id: str,
    req: KnowledgeBaseUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """更新知识库名称/描述"""
    ok = KnowledgeBaseService.update(kb_id, user_id, req.name, req.description)
    if not ok:
        return JSONResponse(
            content={"code": 1, "message": "知识库不存在或无权操作"},
            status_code=404,
        )
    # 返回更新后的数据
    item = KnowledgeBaseService.get_by_id(kb_id, user_id)
    return KnowledgeBaseDetailResponse(data=item).model_dump()


@v1_router.delete("/knowledge-bases/{kb_id}")
def delete_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user),
):
    """删除知识库（软删除，同时软删除其下所有文档）"""
    ok = KnowledgeBaseService.delete(kb_id, user_id)
    if not ok:
        return JSONResponse(
            content={"code": 1, "message": "知识库不存在或无权操作"},
            status_code=404,
        )
    return DeleteResponse().model_dump()


# ==================== 文档管理接口 ====================

@v1_router.post("/knowledge-bases/{kb_id}/documents")
def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    上传文档到指定知识库。

    支持格式：pdf, txt, ppt, pptx, doc, docx, csv, xlsx
    文件先存储到 RustFS，再写入 DB，parse_status=0 等待后续 MinerU 解析。
    """
    try:
        item = DocumentService.upload(kb_id, user_id, file)
        return DocumentDetailResponse(data=item).model_dump()
    except ValueError as e:
        return JSONResponse(
            content={"code": 1, "message": str(e)},
            status_code=400,
        )
    except RuntimeError as e:
        return JSONResponse(
            content={"code": 1, "message": str(e)},
            status_code=500,
        )
    except Exception as e:
        logger.exception("[upload_document] 未知错误 kb_id=%s file=%s", kb_id, file.filename)
        return JSONResponse(
            content={"code": 1, "message": f"上传失败：{e}"},
            status_code=500,
        )


@v1_router.get("/knowledge-bases/{kb_id}/documents")
def list_documents(
    kb_id: str,
    user_id: str = Depends(get_current_user),
):
    """获取知识库下的文档列表"""
    items = DocumentService.list_by_kb(kb_id, user_id)
    return DocumentListResponse(data=items).model_dump()


@v1_router.get("/documents/{doc_id}")
def get_document(
    doc_id: str,
    user_id: str = Depends(get_current_user),
):
    """获取单个文档详情（含 content_text）"""
    item = DocumentService.get_by_id(doc_id, user_id)
    if not item:
        return JSONResponse(
            content={"code": 1, "message": "文档不存在或无权访问"},
            status_code=404,
        )
    return DocumentDetailResponse(data=item).model_dump()


@v1_router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    user_id: str = Depends(get_current_user),
):
    """删除文档（软删除 + 从 RustFS 删除文件）"""
    ok = DocumentService.delete(doc_id, user_id)
    if not ok:
        return JSONResponse(
            content={"code": 1, "message": "文档不存在或无权操作"},
            status_code=404,
        )
    return DeleteResponse().model_dump()