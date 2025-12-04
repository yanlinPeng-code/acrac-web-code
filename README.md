# 推荐系统评测平台

一个基于FastAPI和React的推荐系统评测平台，支持多个推荐接口的评测和对比分析。

## 功能特性

- ✅ 支持4个推荐接口评测：
  - recommend
  - recommend-simple
  - intelligent-recommendation
  - recommend_item_with_reason

- ✅ 两种评测模式：
  - 单个接口评测
  - 所有接口并发评测

- ✅ 完整的评测数据：
  - 命中率统计
  - 处理时间分析
  - 详细结果展示
  - CSV文件导出

- ✅ 线程池并发模拟真实用户场景
- ✅ 智能文本提取和参数适配
- ✅ 清晰的层次结构和模块化设计

## 技术栈

### 后端
- Python 3.11
- FastAPI
- Uvicorn
- Pandas
- httpx
- uv (包管理)

### 前端
- React 18
- TypeScript
- Ant Design
- Vite
- Tailwind CSS

### 部署
- Docker & Docker Compose
- Nginx

## 快速开始

### 使用Docker部署（推荐）

#### 本地开发环境

**Windows**
```bash
deploy.bat
```

**Linux/Mac**
```bash
chmod +x deploy.sh
./deploy.sh
```

部署成功后访问：
- **前端**: http://localhost:5188
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

#### 云服务器生产环境部署

在Linux云服务器（阿里云、腾讯云、AWS等）上部署，并暴露到公网：

```bash
# 克隆代码到服务器
git clone <your-repo> /opt/acrac-app
cd /opt/acrac-app

# 执行生产环境部署脚本
chmod +x deploy-prod.sh
./deploy-prod.sh
```

部署成功后，通过公网访问：
- **前端应用**: http://你的服务器IP:6188
- **API文档**: http://你的服务器IP:6188/docs
- **ReDoc文档**: http://你的服务器IP:6188/redoc
- **健康检查**: http://你的服务器IP:6188/health

**注意事项**：
- 确保云服务器安全组已开放 **6188** 端口
- 所有服务都通过Nginx统一代理，提供统一访问入口
- 详细部署指南请查看 [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md)

### 本地开发

#### 后端
```bash
cd backend
uv pip install -r pyproject.toml
uvicorn main:app --reload --port 8000
```

#### 前端
```bash
cd frontend/eval-app
npm install
npm run dev
```

## 项目结构

```
acrac-code/
├── backend/                # 后端服务
│   ├── app/
│   │   ├── api/           # API层
│   │   ├── controller/    # 控制器
│   │   ├── service/       # 业务逻辑
│   │   ├── model/         # 数据模型
│   │   ├── schema/        # 数据模式
│   │   └── config/        # 配置
│   ├── logs/              # 日志目录
│   ├── evaluation_results/# 评测结果
│   ├── origin_data/       # 测试数据
│   ├── Dockerfile         # 后端Docker配置
│   └── pyproject.toml     # Python依赖
│
├── frontend/              # 前端应用
│   └── eval-app/
│       ├── src/
│       │   ├── api/       # API请求层
│       │   ├── types/     # 类型定义
│       │   ├── components/# UI组件
│       │   ├── utils/     # 工具函数
│       │   └── App.tsx    # 主应用
│       ├── Dockerfile     # 前端Docker配置
│       └── package.json   # Node依赖
│
├── docker/                # Docker配置
│   └── nginx.conf         # Nginx配置
│
├── docker-compose.yml     # Docker编排
├── deploy.sh / deploy.bat # 部署脚本
├── start.sh / start.bat   # 启动脚本
├── stop.sh / stop.bat     # 停止脚本
└── DEPLOYMENT.md          # 部署文档
```

## 使用说明

### 1. 上传评测数据

上传Excel文件（包含临床场景和标准答案）

### 2. 选择评测模式

- **单个接口评测**: 选择一个具体的接口进行评测
- **所有接口并发评测**: 同时评测所有4个接口并对比

### 3. 配置参数

根据选择的接口配置相应的评测参数

### 4. 开始评测

点击"开始评测"按钮，等待评测完成

### 5. 查看结果

- 查看命中率统计
- 查看详细评测结果
- 下载CSV文件

## 评测数据格式

Excel文件应包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| 题号 | 测试题编号 | 1 |
| 临床场景 | 临床描述 | 45岁女性，慢性反复头痛3年 |
| 首选检查项目（标准化） | 标准答案 | * MR颅脑(平扫) |

## API文档

启动服务后访问 http://localhost:8000/docs 查看完整的API文档

### 主要接口

- `POST /api/v1/evaluate-recommend` - 单个接口评测
- `POST /api/v1/evaluate-recommend/all` - 所有接口并发评测

## 常用命令

### Docker命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 重新构建
docker-compose up -d --build
```

### 查看评测结果

评测结果保存在：
- 内存: 通过API返回
- 文件: `backend/evaluation_results/evaluation_all_*.csv`

## 性能优化

- 使用线程池并发评测，模拟真实用户场景
- 支持4个worker的uvicorn配置
- Nginx代理和缓存优化
- 健康检查和自动重启

## 开发文档

- [前端项目结构](frontend/eval-app/PROJECT_STRUCTURE.md)
- [部署文档](DEPLOYMENT.md)

## 故障排查

### 端口冲突
如果端口5188已被占用，可以修改 `docker-compose.yml` 中的端口映射

### 服务无法启动
查看日志：
```bash
docker-compose logs backend
docker-compose logs frontend
```

### 评测失败
- 检查Excel文件格式
- 确认目标API服务可访问
- 查看后端日志

## 贡献

欢迎提交Issue和Pull Request

## 许可证

MIT License
