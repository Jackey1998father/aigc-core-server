"""直接调用后端 chat 接口，观察 SSE 流是否能正常结束"""
import json
import time
import urllib.request

url = "http://106.14.181.222:8000/api/v1/chat"
body = json.dumps({
    "conversation_id": "b9baf35d5a79431188eff7990cc15269",
    "message": "你会制定流程嘛",
    "max_rounds": 3,
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer test",
    },
    method="POST",
)

start = time.time()
print(f"[{time.time()-start:.2f}s] request start...")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        print(f"[{time.time()-start:.2f}s] status={resp.status}, headers={dict(resp.headers)}")
        count = 0
        for line in resp:
            count += 1
            line = line.decode("utf-8", errors="replace").rstrip()
            print(f"[{time.time()-start:.2f}s] line#{count}: {line[:200]}")
            if line == "data: [DONE]":
                print(f"[{time.time()-start:.2f}s] GOT [DONE]!")
                break
        print(f"[{time.time()-start:.2f}s] total lines={count}")
except Exception as e:
    print(f"[{time.time()-start:.2f}s] ERROR: {e!r}")
