#!/bin/bash

echo "=========================================="
echo "ACRAC 网络诊断工具"
echo "=========================================="
echo ""

# 检查端口监听状态
echo "步骤 1: 检查端口监听状态..."
echo "----------------------------------------"
if command -v netstat &> /dev/null; then
    netstat -tlnp | grep -E ':(6188|8002)'
elif command -v ss &> /dev/null; then
    ss -tlnp | grep -E ':(6188|8002)'
else
    echo "警告: 未找到 netstat 或 ss 命令"
fi
echo ""

# 检查服务是否可以本地访问
echo "步骤 2: 检查服务本地访问..."
echo "----------------------------------------"
echo "测试 localhost:6188 ..."
curl -s -o /dev/null -w "HTTP状态码: %{http_code}\n" http://localhost:6188/ || echo "无法访问 localhost:6188"
echo ""

echo "测试 127.0.0.1:6188 ..."
curl -s -o /dev/null -w "HTTP状态码: %{http_code}\n" http://127.0.0.1:6188/ || echo "无法访问 127.0.0.1:6188"
echo ""

# 获取本机IP
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "本机内网IP: $LOCAL_IP"
echo "测试 $LOCAL_IP:6188 ..."
curl -s -o /dev/null -w "HTTP状态码: %{http_code}\n" http://$LOCAL_IP:6188/ || echo "无法访问 $LOCAL_IP:6188"
echo ""

# 检查防火墙状态
echo "步骤 3: 检查防火墙状态..."
echo "----------------------------------------"

# 检查 ufw
if command -v ufw &> /dev/null; then
    echo "UFW 状态:"
    sudo ufw status | grep -E '(Status|6188|8002)' || echo "UFW 未启用或未配置"
    echo ""
fi

# 检查 firewalld
if command -v firewall-cmd &> /dev/null; then
    echo "Firewalld 状态:"
    sudo firewall-cmd --state 2>/dev/null || echo "Firewalld 未运行"
    echo "已开放的端口:"
    sudo firewall-cmd --list-ports 2>/dev/null || echo "无法获取端口列表"
    echo ""
fi

# 检查 iptables
if command -v iptables &> /dev/null; then
    echo "iptables 规则（与6188相关）:"
    sudo iptables -L -n | grep -E '(6188|Chain)' || echo "未找到与6188相关的规则"
    echo ""
fi

# 检查 Docker 容器状态
echo "步骤 4: 检查 Docker 容器状态..."
echo "----------------------------------------"
docker ps --filter "name=acrac" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 检查容器日志（最后20行）
echo "步骤 5: 检查前端容器日志..."
echo "----------------------------------------"
docker logs --tail 20 acrac-frontend-peng
echo ""

echo "步骤 6: 检查后端容器日志..."
echo "----------------------------------------"
docker logs --tail 20 acrac-backend-peng
echo ""

echo "=========================================="
echo "诊断建议"
echo "=========================================="
echo ""
echo "如果服务本地可以访问但公网无法访问，请检查："
echo ""
echo "1. 【最重要】云服务器安全组规则："
echo "   - 登录云服务商控制台（阿里云/腾讯云/AWS等）"
echo "   - 找到 ECS 实例的安全组配置"
echo "   - 添加入方向规则："
echo "     * 端口: 6188"
echo "     * 协议: TCP"
echo "     * 授权对象: 0.0.0.0/0 (所有IP)"
echo ""
echo "2. 服务器本地防火墙："
echo "   使用以下命令开放端口："
echo ""
echo "   # Ubuntu/Debian (UFW):"
echo "   sudo ufw allow 6188/tcp"
echo "   sudo ufw reload"
echo ""
echo "   # CentOS/RHEL (firewalld):"
echo "   sudo firewall-cmd --permanent --add-port=6188/tcp"
echo "   sudo firewall-cmd --reload"
echo ""
echo "   # iptables:"
echo "   sudo iptables -I INPUT -p tcp --dport 6188 -j ACCEPT"
echo "   sudo iptables-save | sudo tee /etc/iptables/rules.v4"
echo ""
echo "3. 验证配置："
echo "   从外部机器测试: curl -v http://203.83.233.236:6188"
echo ""
