# 评测平台部署文档

## 部署架构

```
┌─────────────────────────────────────────┐
│         Nginx (Port 5188)               │
│  ┌──────────────────────────────────┐   │
│  │  Frontend (React/Vite)           │   │
│  │  Static Files                    │   │
│  └──────────────────────────────────┘   │
│               │                          │
│               │ /api/* → proxy           │
│               ▼                          │
│  ┌──────────────────────────────────┐   │
│  │  Backend (FastAPI)               │   │
│  │  Port 8000                       │   │
│  │  uvicorn + 4 workers             │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## 端口说明

- **5188**: 前端访问端口（对外）
- **8000**: 后端API端口（内部）

## 前置要求

- Docker >= 20.10
- Docker Compose >= 2.0
- curl (用于健康检查)

## 快速部署

### Windows系统

双击运行 `deploy.bat` 或在命令行执行：

```bash
deploy.bat
```

### Linux/Mac系统

```bash
chmod +x deploy.sh
./deploy.sh
```

## 手动部署步骤

### 1. 构建镜像

```bash
docker-compose build
```

### 2. 启动服务

```bash
docker-compose up -d
```

### 3. 查看状态

```bash
docker-compose ps
```

### 4. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看后端日志
docker-compose logs -f backend

# 查看前端日志
docker-compose logs -f frontend
```

## 服务访问

部署成功后，可以通过以下地址访问：

- **前端界面**: http://localhost:5188
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 常用命令

### 启动服务

```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

### 停止服务

```bash
# Windows
stop.bat

# Linux/Mac
./stop.sh
```

### 重启服务

```bash
docker-compose restart
```

### 查看日志

```bash
docker-compose logs -f
```

### 进入容器

```bash
# 进入后端容器
docker exec -it acrac-backend bash

# 进入前端容器
docker exec -it acrac-frontend sh
```

### 清理服务

```bash
# 停止并删除容器
docker-compose down

# 停止、删除容器并删除镜像
docker-compose down --rmi all

# 停止、删除容器、镜像和卷
docker-compose down --rmi all -v
```

## 目录挂载

以下目录会从宿主机挂载到容器：

- `./backend/logs` → `/app/logs` (日志)
- `./backend/evaluation_results` → `/app/evaluation_results` (评测结果)
- `./backend/dict` → `/app/dict` (字典数据)
- `./backend/origin_data` → `/app/origin_data` (原始数据)

## 环境变量

可以在 `docker-compose.yml` 中修改环境变量：

```yaml
environment:
  - PYTHONUNBUFFERED=1
  - TZ=Asia/Shanghai
```

## 健康检查

服务包含自动健康检查：

- **后端**: 每30秒检查一次 `/health` 端点
- **前端**: 每30秒检查一次首页访问

如果健康检查失败3次，容器会自动重启。

## 性能配置

### 后端配置

在 `backend/Dockerfile` 中修改worker数量：

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Nginx配置

在 `docker/nginx.conf` 中可以调整：

- 代理超时时间
- Gzip压缩
- 缓存策略

## 故障排查

### 1. 服务无法启动

```bash
# 查看详细日志
docker-compose logs

# 检查端口占用
netstat -ano | findstr :5188
netstat -ano | findstr :8000
```

### 2. 后端健康检查失败

```bash
# 查看后端日志
docker-compose logs backend

# 手动测试健康检查
curl http://localhost:8000/health
```

### 3. 前端无法访问后端

- 检查nginx配置中的代理设置
- 确认backend服务已启动
- 查看frontend日志

### 4. 权限问题

```bash
# Linux/Mac 赋予脚本执行权限
chmod +x deploy.sh start.sh stop.sh
```

## 更新部署

```bash
# 1. 停止服务
docker-compose down

# 2. 更新代码
git pull

# 3. 重新构建并启动
docker-compose up -d --build
```

## 生产环境建议

1. **使用HTTPS**: 配置SSL证书
2. **限流保护**: 配置Nginx限流
3. **日志轮转**: 配置日志轮转策略
4. **监控告警**: 集成Prometheus/Grafana
5. **备份策略**: 定期备份数据和配置
6. **安全加固**:
   - 修改默认端口
   - 配置防火墙
   - 使用非root用户运行

## 支持

如有问题，请查看：
- 日志文件: `./backend/logs/`
- 评测结果: `./backend/evaluation_results/`
