#!/bin/bash

# 生产环境部署脚本
# 用于在Linux云服务器上快速部署应用

set -e  # 遇到错误立即退出

echo "=========================================="
echo "开始部署ACRAC评测平台 - 生产环境"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}提示: 建议使用root用户或sudo运行此脚本${NC}"
    echo "如果遇到权限问题，请使用: sudo $0"
    echo ""
fi

# 1. 检查Docker是否安装
echo "步骤 1/7: 检查Docker环境..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    echo "请先安装Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker compose version &> /dev/null && ! docker-compose --version &> /dev/null; then
    echo -e "${RED}错误: Docker Compose未安装${NC}"
    echo "请先安装Docker Compose"
    exit 1
fi

echo -e "${GREEN}✓ Docker环境检查通过${NC}"
docker --version
docker compose version 2>/dev/null || docker-compose --version
echo ""

# 2. 检查端口占用
echo "步骤 2/7: 检查端口占用..."
if netstat -tuln | grep -q ":6188 "; then
    echo -e "${YELLOW}警告: 端口6188已被占用${NC}"
    echo "请先停止占用该端口的服务，或修改docker-compose.prod.yml中的端口配置"
    read -p "是否继续？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo -e "${GREEN}✓ 端口检查完成${NC}"
echo ""

# 3. 创建必要的目录
echo "步骤 3/7: 创建必要的目录..."
mkdir -p backend/logs
mkdir -p backend/evaluation_results
mkdir -p backend/dict
mkdir -p backend/origin_data
chmod -R 755 backend/logs
chmod -R 755 backend/evaluation_results
echo -e "${GREEN}✓ 目录创建完成${NC}"
echo ""

# 4. 检查环境配置文件
echo "步骤 4/7: 检查环境配置..."
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}警告: 未找到backend/.env文件${NC}"
    echo "如果需要环境变量配置，请创建该文件"
else
    echo -e "${GREEN}✓ 找到环境配置文件${NC}"
fi
echo ""

# 5. 停止旧服务（如果存在）
echo "步骤 5/7: 停止旧服务..."
if docker compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    echo "发现正在运行的服务，正在停止..."
    docker compose -f docker-compose.prod.yml down
    echo -e "${GREEN}✓ 旧服务已停止${NC}"
else
    echo "没有运行中的服务"
fi
echo ""

# 6. 构建并启动服务
echo "步骤 6/7: 构建并启动服务..."
echo "这可能需要几分钟时间，请耐心等待..."
echo ""

docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo -e "${GREEN}✓ 服务启动完成${NC}"
echo ""

# 7. 等待服务启动并检查健康状态
echo "步骤 7/7: 等待服务启动并检查健康状态..."
echo "等待后端服务启动（最多等待60秒）..."

COUNTER=0
MAX_TRIES=30

while [ $COUNTER -lt $MAX_TRIES ]; do
    if curl -f http://localhost:8000/health &> /dev/null; then
        echo -e "${GREEN}✓ 后端服务已就绪${NC}"
        break
    fi
    echo -n "."
    sleep 2
    COUNTER=$((COUNTER + 1))
done

echo ""

if [ $COUNTER -eq $MAX_TRIES ]; then
    echo -e "${YELLOW}警告: 后端服务启动超时，请检查日志${NC}"
    echo "运行以下命令查看日志："
    echo "  docker compose -f docker-compose.prod.yml logs backend"
else
    echo "等待前端服务启动..."
    sleep 5

    if curl -f http://localhost:6188/ &> /dev/null; then
        echo -e "${GREEN}✓ 前端服务已就绪${NC}"
    else
        echo -e "${YELLOW}警告: 前端服务可能未完全启动${NC}"
    fi
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""

# 显示服务状态
echo "服务状态："
docker compose -f docker-compose.prod.yml ps
echo ""

# 显示访问地址
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "访问地址："
echo "  前端应用:    http://localhost:6188"
echo "  API文档:     http://localhost:6188/docs"
echo "  ReDoc文档:   http://localhost:6188/redoc"
echo "  健康检查:    http://localhost:6188/health"
echo ""

if [ -n "$SERVER_IP" ]; then
    echo "公网访问地址（如果有公网IP）："
    echo "  前端应用:    http://${SERVER_IP}:6188"
    echo "  API文档:     http://${SERVER_IP}:6188/docs"
    echo "  ReDoc文档:   http://${SERVER_IP}:6188/redoc"
    echo ""
fi

echo "常用命令："
echo "  查看日志:    docker compose -f docker-compose.prod.yml logs -f"
echo "  停止服务:    docker compose -f docker-compose.prod.yml down"
echo "  重启服务:    docker compose -f docker-compose.prod.yml restart"
echo "  查看状态:    docker compose -f docker-compose.prod.yml ps"
echo ""

echo -e "${YELLOW}提示：${NC}"
echo "1. 确保云服务器安全组已开放6188端口"
echo "2. 建议配置防火墙和SSL证书以提高安全性"
echo "3. 查看详细部署文档: CLOUD_DEPLOYMENT.md"
echo ""
echo "=========================================="
