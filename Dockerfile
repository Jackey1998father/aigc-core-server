FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 requests（模型转发需要）
RUN pip install --no-cache-dir requests

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令（生产环境关闭 reload）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
