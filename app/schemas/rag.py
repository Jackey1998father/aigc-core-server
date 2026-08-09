"""
RAG 增强对话请求 Schema
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class RagChatRequest(BaseModel):
    """RAG 增强对话请求（前端"增强模式"专用）

    与 ChatV2Request 区别：
        - 多一个 kb_ids 字段（前端选中的知识库）
        - 多一个 use_rag 开关（前端可临时切到普通模式）
    """
    conversation_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户当前消息", min_length=1)
    kb_ids: List[str] = Field(
        default_factory=list,
        description="增强模式要检索的知识库 ID 列表（空数组=不检索）",
    )
    use_rag: bool = Field(
        default=True,
        description="是否启用 RAG 增强（false 时退化到普通 chat）",
    )
    model: Optional[str] = Field(default=None, description="模型名")
    max_rounds: int = Field(default=3, ge=1, le=20)
    thinking: bool = Field(default=False, description="深度思考开关")
