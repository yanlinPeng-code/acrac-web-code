# 前端Dockerfile - 多阶段构建（生产环境）
# 阶段1: 构建
FROM node:20.19-alpine AS builder

WORKDIR /app

# 设置npm镜像（可选，国内服务器加速）
# RUN npm config set registry https://registry.npmmirror.com

# 复制package文件
COPY frontend/eval-app/package*.json ./

# 安装所有依赖（包括开发依赖，构建时需要tailwindcss等）
RUN npm ci

# 复制源代码
COPY frontend/eval-app/ .

# 构建生产版本
RUN npm run build

# 阶段2: 运行 - 使用nginx提供静态文件服务
FROM nginx:alpine

# 安装curl用于健康检查
RUN apk add --no-cache curl

# 复制构建产物到nginx目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制nginx配置
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# 设置正确的权限
RUN chmod -R 755 /usr/share/nginx/html

# 创建nginx用户（如果不存在）
RUN addgroup -g 101 -S nginx || true && \
    adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx || true

# 暴露端口6188
EXPOSE 6188

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:6188/ || exit 1

# 启动nginx
CMD ["nginx", "-g", "daemon off;"]
