FROM python:3.12-slim

WORKDIR /app

# pip 清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Poetry
RUN pip install --no-cache-dir poetry

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 先复制依赖文件（利用 Docker 缓存层）
COPY pyproject.toml poetry.lock ./

# Poetry 也走清华源，不创建虚拟环境
RUN poetry config virtualenvs.create false && \
    poetry source add --priority=primary tsinghua https://pypi.tuna.tsinghua.edu.cn/simple && \
    poetry source remove default || true && \
    poetry install --only main --no-interaction --no-ansi --no-root

# 复制应用代码
COPY . .

# 复制入口脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 切换到非 root 用户
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
