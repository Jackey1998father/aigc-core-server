from fastapi import APIRouter

from app.api.rag_router import rag_router
from app.api.v1.router import  v1_router


api_router = APIRouter()

# rag 相关接口
api_router.include_router(rag_router)

# 常规后端开发
api_router.include_router(v1_router)