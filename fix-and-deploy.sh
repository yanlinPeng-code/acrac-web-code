#!/usr/bin/env bash

# 修复并部署脚本
echo "正在修复文件格式并部署..."
echo ""

# 修复deploy-prod.sh的换行符问题
if [ -f "deploy-prod.sh" ]; then
    echo "修复 deploy-prod.sh 文件格式..."
    sed -i 's/\r$//' deploy-prod.sh 2>/dev/null || true
    chmod +x deploy-prod.sh
    echo "✓ 文件格式已修复"
else
    echo "未找到 deploy-prod.sh，创建新文件..."
    cat > deploy-prod.sh << 'DEPLOY_SCRIPT'
#!/usr/bin/env bash

# 生产环境部署脚本
set -e

echo "=========================================="
echo "开始部署ACRAC评测平台 - 生产环境"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}提示: 建议使用root用户或sudo运行此脚本${NC}"
fi

echo "步骤 1/7: 检查Docker环境..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    exit 1
fi

if ! docker compose version &> /dev/null && ! docker-compose --version &> /dev/null; then
    echo -e "${RED}错误: Docker Compose未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker环境检查通过${NC}"
docker --version
docker compose version 2>/dev/null || docker-compose --version
echo ""

echo "步骤 2/7: 检查端口占用..."
if netstat -tuln 2>/dev/null | grep -q ":6188 " || ss -tuln 2>/dev/null | grep -q ":6188 "; then
    echo -e "${YELLOW}警告: 端口6188已被占用${NC}"
fi
echo -e "${GREEN}✓ 端口检查完成${NC}"
echo ""

echo "步骤 3/7: 创建必要的目录..."
mkdir -p backend/logs
mkdir -p backend/evaluation_results
mkdir -p backend/dict
mkdir -p backend/origin_data
chmod -R 755 backend/logs
chmod -R 755 backend/evaluation_results
echo -e "${GREEN}✓ 目录创建完成${NC}"
echo ""

echo "步骤 4/7: 检查环境配置..."
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}警告: 未找到backend/.env文件${NC}"
else
    echo -e "${GREEN}✓ 找到环境配置文件${NC}"
fi
echo ""

echo "步骤 5/7: 停止旧服务..."
docker compose -f docker-compose.prod.yml down 2>/dev/null || true
echo -e "${GREEN}✓ 旧服务已停止${NC}"
echo ""

echo "步骤 6/7: 构建并启动服务..."
echo "这可能需要几分钟时间，请耐心等待..."
echo ""

docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo -e "${GREEN}✓ 服务启动完成${NC}"
echo ""

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

echo "服务状态："
docker compose -f docker-compose.prod.yml ps
echo ""

SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
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
    echo ""
fi

echo "常用命令："
echo "  查看日志:    docker compose -f docker-compose.prod.yml logs -f"
echo "  停止服务:    docker compose -f docker-compose.prod.yml down"
echo "  重启服务:    docker compose -f docker-compose.prod.yml restart"
echo ""
DEPLOY_SCRIPT

    chmod +x deploy-prod.sh
    echo "✓ 已创建 deploy-prod.sh"
fi

echo ""
echo "开始执行部署..."
echo ""

# 执行部署
./deploy-prod.sh
