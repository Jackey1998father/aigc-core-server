"""
Celery 应用实例

启动方式（需要开两个终端）:

  终端 1 — parse 队列（CPU 密集，prefork 2 进程）:
    python app/celery_app.py parse

  终端 2 — embed 队列（IO 密集，prefork 4 进程，可调大）:
    python app/celery_app.py embed

或直接 CLI:
    celery -A app.celery_app worker -l info -P prefork -c 2 -Q parse -n parser@%h
    celery -A app.celery_app worker -l info -P prefork -c 4 -Q embed -n embedder@%h

并发模型说明:
  - prefork: 多进程，真正并行。适合 CPU 密集任务（parse）和 IO 密集任务（embed）
  - solo:   单进程串行，仅用于调试
  - gevent: 协程模型，适合高并发 IO（embed 可开 50-200 并发），需要安装 gevent

worker_prefetch_multiplier=1 保证"哪个资源空了就去 Redis 取"，不会出现
某个 Worker 手里堆一堆任务、另一个闲着的状况。
"""
import sys
from celery import Celery

from app.core.config import settings

# 构造 Redis 连接串
if settings.REDIS_PASSWORD:
    redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
else:
    redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

celery_app = Celery(
    "aigc_core",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks"],
)

# 队列路由：按 task 名分配到不同队列
celery_app.conf.update(
    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 可靠性
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # 重试
    task_default_retry_delay=60,
    task_max_retries=3,

    # 结果过期
    result_expires=86400,

    # ===== Broker 连接稳定性（远程 Redis 场景）=====
    broker_connection_retry_on_startup=True,
    broker_heartbeat=0,                     # 禁用应用层心跳，用 TCP keepalive
    broker_connection_timeout=30,           # Redis 连接超时（秒）
    broker_transport_options={
        "visibility_timeout": 3600,         # 任务被 worker 取走后，多久没 ack 就重新分发（长任务保底）
        "socket_keepalive": True,           # TCP keepalive 防止远程 Redis 断开
        "socket_timeout": 30,               # Redis socket 读写超时
        "socket_connect_timeout": 10,       # Redis socket 连接超时
    },

    # ===== 队列路由 =====
    # parse:  CPU 密集 → Worker 数 ≤ CPU 核数，用 prefork
    # embed:  IO 密集  → 调用 API，Worker 数可以开大
    task_routes={
        "app.tasks.parse_document":       {"queue": "parse"},
        "app.tasks.chunk_and_vectorize":  {"queue": "embed"},
    },

    # 各队列默认只取本队列的任务
    task_default_queue="parse",
)

if __name__ == "__main__":

    args = sys.argv[1:] if len(sys.argv) > 1 else []
    queue = args[0] if args else "parse"

    # Windows 不支持 prefork（无 fork()），用 threads 替代
    # Linux/Mac 继续用 prefork 保证 CPU 密集型任务的真正并行
    if sys.platform == "win32":
        pool = "threads"
        print("[WARNING] Windows 检测到，使用 --pool=threads 替代 prefork")
    else:
        pool = "prefork"

    if queue == "parse":
        celery_app.start(argv=["worker", "-l", "info", "-P", pool, "-c", "2", "-Q", "parse", "-n", "parser@%h"])
    elif queue == "embed":
        celery_app.start(argv=["worker", "-l", "info", "-P", pool, "-c", "4", "-Q", "embed", "-n", "embedder@%h"])
    else:
        print("用法: python app/celery_app.py [parse|embed]")
        sys.exit(1)
