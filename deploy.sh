#!/bin/bash

# 评测平台部署脚本
# 端口: 5188

set -e

echo "================================================"
echo "评测平台部署脚本"
echo "================================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装，请先安装Docker${NC}"
    exit 1
fi

# 检查docker-compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: docker-compose未安装，请先安装docker-compose${NC}"
    exit 1
fi

# 停止并移除旧容器
echo -e "${YELLOW}停止旧容器...${NC}"
docker-compose down || true

# 清理旧镜像（可选）
read -p "是否清理旧镜像? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}清理旧镜像...${NC}"
    docker-compose down --rmi all || true
fi

# 构建镜像
echo -e "${YELLOW}构建Docker镜像...${NC}"
docker-compose build --no-cache

# 启动服务
echo -e "${YELLOW}启动服务...${NC}"
docker-compose up -d

# 等待服务启动
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${YELLOW}检查服务状态...${NC}"
docker-compose ps

# 检查后端健康状态
echo -e "${YELLOW}检查后端健康状态...${NC}"
for i in {1..10}; do
    if curl -f http://localhost:8000/health &> /dev/null; then
        echo -e "${GREEN}✓ 后端服务启动成功${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}✗ 后端服务启动失败${NC}"
        docker-compose logs backend
        exit 1
    fi
    echo "等待后端启动... ($i/10)"
    sleep 3
done

# 检查前端健康状态
echo -e "${YELLOW}检查前端健康状态...${NC}"
for i in {1..10}; do
    if curl -f http://localhost:5188 &> /dev/null; then
        echo -e "${GREEN}✓ 前端服务启动成功${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}✗ 前端服务启动失败${NC}"
        docker-compose logs frontend
        exit 1
    fi
    echo "等待前端启动... ($i/10)"
    sleep 3
done

echo ""
echo "================================================"
echo -e "${GREEN}部署完成!${NC}"
echo "================================================"
echo ""
echo "访问地址:"
echo "  前端: http://localhost:5188"
echo "  后端API: http://localhost:8000"
echo "  后端文档: http://localhost:8000/docs"
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose logs -f"
echo "  查看后端日志: docker-compose logs -f backend"
echo "  查看前端日志: docker-compose logs -f frontend"
echo "  停止服务: docker-compose down"
echo "  重启服务: docker-compose restart"
echo ""
