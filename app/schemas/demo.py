from pydantic import BaseModel


class DemoRequest(BaseModel):
    text: str


class DemoData(BaseModel):
    original_text: str
    echoed_text: str


class DemoResponse(BaseModel):
    code: int
    message: str
    data: DemoData