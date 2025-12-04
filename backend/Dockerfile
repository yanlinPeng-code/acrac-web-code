# 后端Dockerfile - 生产环境部署
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 替换为阿里云镜像源（加速apt-get下载）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（包括 PostgreSQL 客户端工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    ca-certificates \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 使用pip安装uv（更快的包管理器）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv

# 复制依赖文件
COPY backend/requirements.txt ./

# 使用uv安装依赖（使用阿里云镜像加速）
RUN uv pip install --system --no-cache --index-url https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 复制应用代码

COPY backend/ .

# 创建必要的目录并设置权限
RUN mkdir -p logs evaluation_results dict origin_data && \
    chmod -R 755 logs evaluation_results

# 复制并设置 entrypoint 脚本
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 创建非root用户（生产环境最佳实践）
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# 切换到非root用户
USER appuser

# 暴露端口
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# 设置 entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动应用（生产环境推荐配置）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
