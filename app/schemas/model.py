"""
模型配置 Schema
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ModelItem(BaseModel):
    """模型配置项"""
    model_id: str = Field(..., description="调上游 API 用的模型标识")
    name: str = Field(..., description="前端显示名称")
    model_type: str = Field(..., description="类型：chat / embedding / rerank")
    provider: str = Field(..., description="服务商")
    max_tokens: int = Field(..., description="最大输出 token")
    is_default: bool = Field(..., description="是否该类型默认模型")
    description: Optional[str] = Field(default=None, description="模型描述")


class ModelListResponse(BaseModel):
    """模型列表响应"""
    code: int = 0
    message: str = "success"
    data: List[ModelItem] = []
