"""
RAG 增强对话请求 Schema
"""
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class RagChatRequest(BaseModel):
    """RAG 增强对话请求（前端"增强模式"专用）

    与 ChatV2Request 区别：
        - 多一个 kb_ids 字段（前端选中的知识库）
    """
    conversation_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="用户当前消息（纯图片输入时可空）")
    images: List[str] = Field(
        default_factory=list,
        description="图片列表（data URL 或 http(s) 公网 URL），用于视觉模型",
    )
    kb_ids: List[str] = Field(
        default_factory=list,
        description="要检索的知识库 ID 列表",
    )
    model: Optional[str] = Field(default=None, description="模型名")
    max_rounds: int = Field(default=3, ge=1, le=20)
    thinking: bool = Field(default=False, description="深度思考开关")

    @model_validator(mode="after")
    def _require_content(self):
        if not self.message.strip() and not self.images:
            raise ValueError("message 与 images 至少需要提供一个")
        return self
