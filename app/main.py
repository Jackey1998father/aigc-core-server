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

    # Celery 健康检查
    @app.get("/api/v1/celery-health")
    def celery_health():
        try:
            from app.celery_app import celery_app
            ping = celery_app.control.ping(timeout=2)
            workers_online = len(ping) > 0
            return {
                "code": 0,
                "message": "success" if workers_online else "no workers",
                "data": {
                    "workers": len(ping),
                    "online": workers_online,
                },
            }
        except Exception as e:
            return {
                "code": 1,
                "message": f"Celery 不可用: {e}",
                "data": None,
            }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )