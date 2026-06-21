from fastapi import APIRouter
from app.schemas.demo import DemoResponse, DemoRequest
from app.services.demo_service import DemoService

v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/health")
def health_check():
    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": "ok"
        }
    }

@v1_router.post("/demo", response_model=DemoResponse)
def echo(req: DemoRequest):
    result = DemoService.echo(req.text)
    return DemoResponse(code=0, message="success", data=result)