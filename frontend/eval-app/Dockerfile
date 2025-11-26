# 前端Dockerfile - 多阶段构建
# 阶段1: 构建
FROM node:18-alpine AS builder

WORKDIR /app

# 复制package文件
COPY frontend/eval-app/package*.json ./

# 安装依赖
RUN npm ci

# 复制源代码
COPY frontend/eval-app/ .

# 构建生产版本
RUN npm run build

# 阶段2: 运行 - 使用nginx提供静态文件服务
FROM nginx:alpine

# 复制构建产物到nginx目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制nginx配置
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 启动nginx
CMD ["nginx", "-g", "daemon off;"]
