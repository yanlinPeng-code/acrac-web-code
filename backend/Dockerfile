# 后端Dockerfile - 使用uv部署FastAPI应用
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# 安装系统依赖和uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# 将uv添加到PATH
ENV PATH="/root/.cargo/bin:$PATH"

# 复制依赖文件
COPY backend/pyproject.toml ./

# 使用uv安装依赖
RUN uv pip install -r pyproject.toml

# 复制应用代码
COPY backend/ .

# 创建必要的目录
RUN mkdir -p logs evaluation_results dict origin_data

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
