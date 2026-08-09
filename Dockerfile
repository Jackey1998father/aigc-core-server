FROM python:3.12-slim

WORKDIR /app

# 安装 Poetry
RUN pip install --no-cache-dir poetry

# 创建非 root 用户，提高安全性
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 先复制依赖文件（利用 Docker 缓存层）
COPY pyproject.toml poetry.lock ./

# 安装生产依赖（不在容器内创建虚拟环境，直接用系统 Python）
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# 复制应用代码
COPY . .

# 复制入口脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 切换到非 root 用户
RUN chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查（仅 API 服务有效，Worker 需自定义）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# 统一入口，通过 command 区分服务类型
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
