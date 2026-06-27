import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="AIGC Core Server based on FastAPI",
    )

    # CORS 中间件（本地开发全放行）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.CORS_CREDENTIALS,
        allow_methods=settings.cors_method_list,
        allow_headers=settings.cors_header_list,
    )

    app.include_router(api_router)

    return app


app = create_app()



if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
 