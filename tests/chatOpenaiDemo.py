import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("Missing OPENAI_API_KEY env variable")

llm = ChatOpenAI(
    base_url="http://localhost:8000/models/v1",
    api_key=SecretStr(api_key),
    model="qwen-plus",
)

for chunk in llm.stream("请告诉我你对无锡的了解"):
    if chunk.content:
        print(chunk.content, end="", flush=True)
