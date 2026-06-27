from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Message(BaseModel):
    """单条消息"""
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """对话请求

    前端每次发请求时，将完整的会话历史放入 messages 中。
    后端会自动裁剪，只保留：
    - system 消息（始终保留）
    - 最近 N 轮 user/assistant 对话（默认 3 轮）
    """
    messages: List[Message] = Field(
        ...,
        description="完整会话历史，按时间顺序排列",
        min_length=1,
    )
    stream: bool = Field(
        default=True,
        description="是否流式输出",
    )
    max_rounds: int = Field(
        default=3,
        ge=1,
        le=20,
        description="保留最近 N 轮对话上下文（1轮 = 1问1答）",
    )
    model: Optional[str] = Field(
        default=None,
        description="模型名称，不传则使用默认模型",
    )


class ChatResponse(BaseModel):
    """非流式对话响应"""
    code: int = 0
    message: str = "success"
    data: Optional[dict] = None
