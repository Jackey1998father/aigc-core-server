from fastapi import APIRouter

from app.api.model_api.router import self_model_router
from app.api.model_api.silicon_router import silicon_router
from app.api.retriever_router import retriever_router
from app.api.v1.router import  v1_router


api_router = APIRouter()
# 模型相关部署
api_router.include_router(self_model_router)
api_router.include_router(silicon_router)


# rag 相关接口开发
# api_router.include_router() #整个回答链路
api_router.include_router(retriever_router)


# 常规后端开发
api_router.include_router(v1_router)