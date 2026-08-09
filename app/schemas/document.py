"""
文档 Schema
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class DocumentItem(BaseModel):
    """文档列表项"""
    id: str
    kb_id: str
    title: str
    file_name: str
    file_type: str
    file_size: int
    parse_status: int = 0
    content_text: Optional[str] = None
    created_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    code: int = 0
    message: str = "success"
    data: List[DocumentItem] = []


class DocumentDetailResponse(BaseModel):
    """单个文档响应"""
    code: int = 0
    message: str = "success"
    data: Optional[DocumentItem] = None
