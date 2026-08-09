#!/bin/bash
# Docker 容器统一入口
# 用法: docker run ... aigc-core-server [api|parse-worker|embed-worker]
set -e

SERVICE="${1:-api}"

case "$SERVICE" in
  api)
    echo "[entrypoint] 启动 FastAPI 服务"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  parse-worker)
    echo "[entrypoint] 启动 Celery parse worker"
    exec celery -A app.celery_app worker -l info -Q parse -c 2 -n "parser@%h"
    ;;
  embed-worker)
    echo "[entrypoint] 启动 Celery embed worker"
    exec celery -A app.celery_app worker -l info -Q embed -c 4 -n "embedder@%h"
    ;;
  *)
    echo "[entrypoint] 未知服务类型: $SERVICE (支持: api | parse-worker | embed-worker)"
    exit 1
    ;;
esac
