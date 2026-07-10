"""
会话 & 消息 Schema
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """创建会话请求"""
    title: str = Field(default="新对话", description="会话标题")


class ConversationItem(BaseModel):
    """会话列表项"""
    id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    code: int = 0
    message: str = "success"
    data: List[ConversationItem] = []


class ConversationDetailResponse(BaseModel):
    """单个会话响应"""
    code: int = 0
    message: str = "success"
    data: Optional[ConversationItem] = None


class DeleteResponse(BaseModel):
    """删除响应"""
    code: int = 0
    message: str = "已删除"


class MessageItem(BaseModel):
    """消息项"""
    id: str
    role: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    """消息列表响应"""
    code: int = 0
    message: str = "success"
    data: List[MessageItem] = []
