FROM python:3.12-slim

WORKDIR /app

# 创建非 root 用户，提高安全性
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 先复制依赖文件（利用 Docker 缓存层）
COPY requirements.txt .

RUN pip install \
    -i https://mirrors.aliyun.com/pypi/simple \
    --trusted-host mirrors.aliyun.com \
    --no-cache-dir \
    -r requirements.txt

# 复制应用代码
COPY . .

# 切换到非 root 用户
RUN chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# 生产环境启动（关闭 reload）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
