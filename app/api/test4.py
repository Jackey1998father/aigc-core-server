from fastapi import APIRouter


test4_router = APIRouter(prefix="/api")


@test4_router.get("/test4")
def test4():
    return {
        "code": 0,
        "message": "success",
        "data": {
            "msg": "test4 ok"
        }
    }
