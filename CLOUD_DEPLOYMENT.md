# Linux云服务器部署指南

本指南将帮助你在Linux云服务器（如阿里云、腾讯云、AWS等）上部署前后端应用，并将两者都暴露到公网。

## 架构说明

```
互联网
    ↓
云服务器公网IP:6188
    ↓
┌─────────────────────────────────────────────┐
│   Nginx (Port 6188) - 前端 + 反向代理         │
│   ┌──────────────────────────────────────┐  │
│   │  前端静态文件 (/)                      │  │
│   │  API代理 (/api/*)    → Backend:8000  │  │
│   │  文档代理 (/docs)    → Backend:8000  │  │
│   │  文档代理 (/redoc)   → Backend:8000  │  │
│   │  OpenAPI (/openapi.json)→Backend:8000│  │
│   │  健康检查 (/health)   → Backend:8000  │  │
│   └──────────────────────────────────────┘  │
│                    ↓                         │
│   ┌──────────────────────────────────────┐  │
│   │  FastAPI Backend (Port 8000)         │  │
│   │  - uvicorn + 4 workers               │  │
│   └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## 访问地址（部署后）

- **前端界面**: `http://你的服务器IP:6188`
- **API文档**: `http://你的服务器IP:6188/docs`
- **ReDoc文档**: `http://你的服务器IP:6188/redoc`
- **OpenAPI规范**: `http://你的服务器IP:6188/openapi.json`
- **健康检查**: `http://你的服务器IP:6188/health`
- **API接口**: `http://你的服务器IP:6188/api/...`

注意：所有访问都通过6188端口，Nginx会自动将请求路由到相应的服务。

## 前置要求

### 1. 云服务器配置建议

- **操作系统**: Ubuntu 20.04/22.04 或 CentOS 7/8
- **CPU**: 2核以上
- **内存**: 4GB以上
- **磁盘**: 20GB以上
- **网络**: 公网IP，带宽至少1Mbps

### 2. 防火墙/安全组配置

在云服务器控制台配置安全组，开放以下端口：

| 端口 | 协议 | 说明 | 源地址 |
|------|------|------|--------|
| 22 | TCP | SSH登录 | 你的IP（建议限制） |
| 6188 | TCP | 前端访问（包含所有API和文档） | 0.0.0.0/0（公网访问） |

**重要**: 不需要开放8000端口，因为后端通过Nginx代理访问，不直接暴露到公网。

### 3. 软件依赖

- Docker >= 20.10
- Docker Compose >= 2.0
- Git

## 部署步骤

### 步骤1: 连接到云服务器

```bash
ssh root@你的服务器IP
# 或者使用你的用户名
ssh 用户名@你的服务器IP
```

### 步骤2: 安装Docker和Docker Compose

#### Ubuntu系统

```bash
# 更新包索引
sudo apt-get update

# 安装必要的依赖
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 添加Docker官方GPG密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 设置Docker仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
sudo docker --version
sudo docker compose version
```

#### CentOS系统

```bash
# 安装必要的依赖
sudo yum install -y yum-utils

# 添加Docker仓库
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 安装Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
sudo docker --version
sudo docker compose version
```

### 步骤3: 克隆项目代码

```bash
# 进入工作目录
cd /opt

# 克隆项目（替换为你的仓库地址）
sudo git clone https://github.com/你的用户名/你的项目.git acrac-app

# 或者从本地上传代码
# 方法1: 使用scp从本地上传
# 在本地电脑执行：
# scp -r D:\acrac-code root@服务器IP:/opt/acrac-app

# 方法2: 使用rsync
# rsync -avz -e ssh D:\acrac-code/ root@服务器IP:/opt/acrac-app/

# 进入项目目录
cd /opt/acrac-app
```

### 步骤4: 配置环境文件（可选）

如果你的应用需要环境变量配置，创建 `.env` 文件：

```bash
# 创建后端环境配置文件
sudo nano backend/.env
```

示例 `.env` 内容：

```env
# 应用配置
APP_NAME=ACRO
APP_VERSION=1.0.0
DEBUG=false

# 数据库配置（如果需要）
# DATABASE_URL=postgresql://user:password@host:5432/dbname

# Redis配置（如果需要）
# REDIS_URL=redis://localhost:6379

# API密钥等敏感信息
# API_KEY=your_secret_key
```

### 步骤5: 创建必要的目录

```bash
# 创建数据目录
sudo mkdir -p backend/logs
sudo mkdir -p backend/evaluation_results
sudo mkdir -p backend/dict
sudo mkdir -p backend/origin_data

# 设置权限
sudo chmod -R 755 backend/logs
sudo chmod -R 755 backend/evaluation_results
```

### 步骤6: 部署应用

```bash
# 构建并启动服务
sudo docker compose -f docker-compose.prod.yml up -d --build

# 查看服务状态
sudo docker compose -f docker-compose.prod.yml ps

# 查看日志
sudo docker compose -f docker-compose.prod.yml logs -f
```

### 步骤7: 验证部署

等待1-2分钟让服务完全启动，然后验证：

```bash
# 检查后端健康状态
curl http://localhost:8000/health

# 检查前端和Nginx
curl http://localhost:6188

# 检查API文档是否可访问
curl http://localhost:6188/docs
```

如果返回正常，说明部署成功！

### 步骤8: 从外部访问

在你的浏览器中访问：

- 前端应用: `http://你的服务器公网IP:6188`
- API文档: `http://你的服务器公网IP:6188/docs`
- ReDoc文档: `http://你的服务器公网IP:6188/redoc`

## 常用管理命令

### 查看服务状态

```bash
cd /opt/acrac-app
sudo docker compose -f docker-compose.prod.yml ps
```

### 查看日志

```bash
# 查看所有日志
sudo docker compose -f docker-compose.prod.yml logs -f

# 只查看后端日志
sudo docker compose -f docker-compose.prod.yml logs -f backend

# 只查看前端日志
sudo docker compose -f docker-compose.prod.yml logs -f frontend

# 查看最近100行日志
sudo docker compose -f docker-compose.prod.yml logs --tail=100
```

### 重启服务

```bash
# 重启所有服务
sudo docker compose -f docker-compose.prod.yml restart

# 只重启后端
sudo docker compose -f docker-compose.prod.yml restart backend

# 只重启前端
sudo docker compose -f docker-compose.prod.yml restart frontend
```

### 停止服务

```bash
sudo docker compose -f docker-compose.prod.yml down
```

### 更新应用

```bash
# 1. 停止服务
sudo docker compose -f docker-compose.prod.yml down

# 2. 拉取最新代码
sudo git pull

# 3. 重新构建并启动
sudo docker compose -f docker-compose.prod.yml up -d --build
```

### 清理未使用的Docker资源

```bash
# 清理未使用的容器、网络、镜像
sudo docker system prune -a

# 查看磁盘使用情况
sudo docker system df
```

## 性能优化建议

### 1. 启用HTTPS（推荐）

使用Let's Encrypt免费SSL证书：

```bash
# 安装Certbot
sudo apt-get install -y certbot

# 获取证书（需要域名）
sudo certbot certonly --standalone -d 你的域名.com

# 修改Nginx配置以使用HTTPS
# 编辑 docker/nginx.conf，添加SSL配置
```

### 2. 配置Nginx日志轮转

```bash
# 创建日志轮转配置
sudo nano /etc/logrotate.d/nginx-docker

# 内容：
/opt/acrac-app/logs/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        docker exec acrac-frontend nginx -s reload
    endscript
}
```

### 3. 监控服务

安装监控工具：

```bash
# 安装htop查看系统资源
sudo apt-get install -y htop

# 使用ctop查看容器资源使用
sudo wget https://github.com/bcicen/ctop/releases/download/v0.7.7/ctop-0.7.7-linux-amd64 -O /usr/local/bin/ctop
sudo chmod +x /usr/local/bin/ctop

# 查看容器资源使用情况
sudo ctop
```

### 4. 设置自动重启

服务已配置为 `restart: always`，Docker会在系统重启后自动启动容器。

验证自动重启：

```bash
# 重启服务器
sudo reboot

# 重新连接后检查服务
sudo docker compose -f docker-compose.prod.yml ps
```

## 故障排查

### 问题1: 无法访问6188端口

**检查清单**:

1. 确认安全组已开放6188端口
   ```bash
   # 检查防火墙状态（Ubuntu）
   sudo ufw status
   sudo ufw allow 6188/tcp

   # 检查防火墙状态（CentOS）
   sudo firewall-cmd --list-all
   sudo firewall-cmd --add-port=6188/tcp --permanent
   sudo firewall-cmd --reload
   ```

2. 确认服务正在运行
   ```bash
   sudo docker compose -f docker-compose.prod.yml ps
   sudo netstat -tulpn | grep 6188
   ```

3. 检查Nginx日志
   ```bash
   sudo docker compose -f docker-compose.prod.yml logs frontend
   ```

### 问题2: 后端服务启动失败

```bash
# 查看后端详细日志
sudo docker compose -f docker-compose.prod.yml logs backend

# 进入容器调试
sudo docker exec -it acrac-backend bash
```

常见原因：
- 依赖安装失败：检查 `requirements.txt`
- 环境变量缺失：检查 `.env` 文件
- 端口冲突：确认8000端口未被占用

### 问题3: API文档无法访问

```bash
# 测试后端直接访问
curl http://localhost:8000/docs

# 测试Nginx代理
curl http://localhost:6188/docs

# 检查Nginx配置
sudo docker exec acrac-frontend cat /etc/nginx/conf.d/default.conf
```

### 问题4: 磁盘空间不足

```bash
# 查看磁盘使用情况
df -h

# 清理Docker资源
sudo docker system prune -a

# 清理日志文件
sudo find /opt/acrac-app/backend/logs -name "*.log" -mtime +7 -delete
```

### 问题5: 容器频繁重启

```bash
# 查看容器状态
sudo docker compose -f docker-compose.prod.yml ps

# 查看健康检查日志
sudo docker inspect acrac-backend | grep -A 20 Health

# 检查系统资源
free -h
htop
```

## 安全加固建议

### 1. 修改SSH端口

```bash
sudo nano /etc/ssh/sshd_config
# 修改 Port 22 为其他端口，如 Port 2222
sudo systemctl restart sshd
```

### 2. 配置防火墙

```bash
# Ubuntu - 使用ufw
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 2222/tcp  # SSH端口
sudo ufw allow 6188/tcp  # 应用端口

# CentOS - 使用firewalld
sudo systemctl start firewalld
sudo systemctl enable firewalld
sudo firewall-cmd --set-default-zone=public
sudo firewall-cmd --add-port=2222/tcp --permanent
sudo firewall-cmd --add-port=6188/tcp --permanent
sudo firewall-cmd --reload
```

### 3. 设置自动更新

```bash
# Ubuntu
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. 配置限流（防止DDoS）

编辑 `docker/nginx.conf`，添加限流配置：

```nginx
# 在http块中添加
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

# 在location块中应用
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    # ... 其他配置
}
```

### 5. 备份数据

创建自动备份脚本：

```bash
sudo nano /opt/backup.sh

# 内容：
#!/bin/bash
BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份评测结果
tar -czf $BACKUP_DIR/evaluation_$DATE.tar.gz /opt/acrac-app/backend/evaluation_results/

# 备份日志
tar -czf $BACKUP_DIR/logs_$DATE.tar.gz /opt/acrac-app/backend/logs/

# 删除7天前的备份
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

# 设置权限
sudo chmod +x /opt/backup.sh

# 设置定时任务
sudo crontab -e
# 添加：每天凌晨2点执行备份
0 2 * * * /opt/backup.sh
```

## 域名配置（可选）

如果你有域名，可以配置域名访问：

### 1. 添加DNS解析

在域名服务商的控制台添加A记录：

```
类型: A
主机记录: @（或www）
记录值: 你的服务器公网IP
TTL: 600
```

### 2. 修改Nginx配置

编辑 `docker/nginx.conf`：

```nginx
server {
    listen 80;
    server_name 你的域名.com www.你的域名.com;

    # 其他配置保持不变
    ...
}
```

### 3. 重启前端服务

```bash
sudo docker compose -f docker-compose.prod.yml restart frontend
```

### 4. 配置HTTPS（推荐）

使用Certbot获取免费SSL证书：

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 获取证书并自动配置Nginx
sudo certbot --nginx -d 你的域名.com -d www.你的域名.com

# 测试自动续期
sudo certbot renew --dry-run
```

## 监控和告警

### 使用Prometheus + Grafana（进阶）

```bash
# 创建docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  grafana-data:
```

## 总结

通过以上步骤，你已经成功在Linux云服务器上部署了前后端应用，并将以下接口暴露到公网：

- 前端应用 (端口6188)
- FastAPI文档 (通过Nginx代理)
- 所有API接口 (通过Nginx代理)

所有服务都通过单一端口(6188)访问，提高了安全性和管理便利性。

如有问题，请查看日志文件或参考故障排查章节。
