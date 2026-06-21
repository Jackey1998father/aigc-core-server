import uvicorn
from fastapi import FastAPI
from app.api.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="AIGC Core Server based on FastAPI",
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
 