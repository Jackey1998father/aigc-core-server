"""
知识库 Schema
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., description="知识库名称", max_length=100)
    description: str = Field(default="", description="描述", max_length=500)


class KnowledgeBaseUpdateRequest(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(default=None, description="知识库名称", max_length=100)
    description: Optional[str] = Field(default=None, description="描述", max_length=500)


class KnowledgeBaseItem(BaseModel):
    """知识库列表项"""
    id: str
    name: str
    description: str
    doc_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""
    code: int = 0
    message: str = "success"
    data: List[KnowledgeBaseItem] = []


class KnowledgeBaseDetailResponse(BaseModel):
    """单个知识库响应"""
    code: int = 0
    message: str = "success"
    data: Optional[KnowledgeBaseItem] = None
