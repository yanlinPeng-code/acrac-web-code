# RAG 推荐 API 接口流程文档

## 概述

本文档详细描述了智能推荐 API (`/api/v1/recommend`) 的完整处理流程，从控制器接收到请求开始，经过服务层处理、检索服务、LLM 选择，最终返回响应。

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI 应用层                                   │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │  控制器层    │    │   服务层     │    │   检索层     │                 │
│  │ Recommend-  │───▶│   RagService │───▶│ Retrieval-  │                 │
│  │ Controller  │    │             │    │ Service     │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│         │                  │                  │                        │
│         ▼                  ▼                  ▼                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ 响应包装器   │    │  模型服务    │    │ 向量数据库    │                 │
│  │ Response    │    │ ModelService│    │ VectorDB     │                 │
│  │ Factory     │    │             │    │ Service     │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        基础设施层                                        │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │  PostgreSQL │    │    Redis    │    │   AI服务     │                 │
│  │  数据库      │    │   缓存      │    │  (LLM)      │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 详细处理流程

### 1. 控制器层 (Controller)

**文件位置**: <mcfile name="recommend_controller.py" path="d:\code\acro\app\controller\rag_v1\recommend_controller.py"></mcfile>

#### 入口函数: `rag_recommend`

```python
@router.post("/recommend")
async def rag_recommend(
    http_request: Request,
    recommendation_request: IntelligentRecommendationRequest,
    rag_recommendation_service: RagRecommendDep,
):
```

**处理步骤**:
1. **请求接收**: 接收 HTTP 请求和序列化的请求体
2. **上下文提取**: 获取客户端 IP 和请求 ID 用于日志追踪
3. **医学词典加载**: 从应用状态获取预加载的医学术语词典
4. **服务调用**: 将请求委托给 `RagService` 处理
5. **响应包装**: 使用标准响应格式包装服务返回的结果

### 2. 服务层 (RagService)

**文件位置**: <mcfile name="rag_service.py" path="d:\code\acro\app\service\rag_v1\rag_service.py"></mcfile>

#### 核心方法: `generate_intelligent_recommendation`

**四阶段处理流程**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RagService 处理流程                               │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  │  混合检索    │    │  场景排序    │    │ 推荐获取     │    │ 最终选择     │
│  │ Hybrid      │───▶│ Scenario    │───▶│ Recommen-   │───▶│ LLM Ranking │
│  │ Retrieval   │    │ Ranking     │    │ dation      │    │             │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
│         │                  │                  │                  │        │
│         ▼                  ▼                  ▼                  ▼        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  │ Jieba模糊    │    │ 混合评分     │    │ 场景推荐     │    │ LLM推理      │
│  │ 搜索        │    │ 算法        │    │ 查询        │    │ 排序        │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3. 检索服务层 (RetrievalService)

**文件位置**: <mcfile name="retrieval_service.py" path="d:\code\acro\app\service\rag_v1\retrieval_service.py"></mcfile>

#### 关键方法: `retrieve_clinical_scenarios`

**并行检索策略**:

```python
async def retrieve_clinical_scenarios(
    self, query: str, medical_dict: Optional[List[str]] = None
) -> List[ClinicalScenario]:
```

**检索阶段**:
1. **查询标准化**: 使用 LLM 对用户查询进行标准化处理（带缓存）
2. **并行检索**: 使用 `asyncio.gather` 并行执行三种检索方式
   - **Jieba 模糊搜索**: 基于医学词典的术语匹配
   - **语义向量搜索**: 使用 embedding 模型进行语义相似度检索
   - **MMR 搜索**: 最大边际相关性搜索，平衡相关性和多样性
3. **结果合并**: 合并不同检索方法的结果，去除重复项
4. **混合评分**: 计算每个场景的最终综合评分

### 4. 数据库会话管理

**文件位置**: <mcfile name="database.py" path="d:\code\acro\app\config\database.py"></mcfile>

#### 会话管理策略:

- **异步会话管理器**: `PostgreSQLAsyncSessionManager`
- **依赖注入**: 通过 FastAPI 依赖项提供数据库会话
- **并发安全**: 检索服务使用独立会话来避免事务冲突

### 5. 响应处理

**文件位置**: <mcfile name="response_factory.py" path="d:\code\acro\app\response\response_factory.py"></mcfile>

#### 统一响应格式:

```python
{
    "success": true,
    "code": 200,
    "message": "推荐成功",
    "data": {
        "query": "患者主诉",
        "best_recommendations": [...],
        "processing_time_ms": 1500,
        "model_used": "siliconflow/embedding-model"
    },
    "request_id": "uuid",
    "host_id": "client_ip"
}
```

## 请求响应示例

### 请求示例

```json
{
    "patient_info": {
        "age": 45,
        "gender": "male",
        "allergies": ["青霉素"],
        "comorbidities": ["高血压", "糖尿病"]
    },
    "clinical_context": {
        "department": "心血管内科",
        "chief_complaint": "胸痛伴呼吸困难",
        "medical_history": "高血压病史10年",
        "present_illness": "突发胸痛2小时",
        "diagnosis": "急性冠脉综合征"
    },
    "search_strategy": {
        "vector_weight": 0.6,
        "keyword_weight": 0.3,
        "diversity_weight": 0.1
    },
    "top_scenarios": 5,
    "top_recommendations_per_scenario": 3,
    "similarity_threshold": 0.7,
    "min_appropriateness_rating": 4
}
```

### 响应示例

```json
{
    "success": true,
    "code": 200,
    "message": "推荐成功",
    "data": {
        "query": "胸痛伴呼吸困难",
        "best_recommendations": [
            {
                "scenario_id": "scenario_001",
                "scenario_title": "急性心肌梗死急诊处理",
                "recommendations": [
                    {
                        "recommendation_id": "rec_001",
                        "content": "立即进行心电图检查",
                        "appropriateness_rating": 5,
                        "confidence_score": 0.92
                    },
                    {
                        "recommendation_id": "rec_002", 
                        "content": "给予阿司匹林300mg嚼服",
                        "appropriateness_rating": 4,
                        "confidence_score": 0.88
                    }
                ]
            }
        ],
        "processing_time_ms": 1250,
        "model_used": "siliconflow/embedding-model",
        "reranker_model_used": "llama-3-70b",
        "similarity_threshold": 0.7
    },
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "host_id": "192.168.1.100"
}
```

## 错误处理机制

### 异常处理层级

1. **控制器层异常**: 捕获服务层异常并转换为标准错误响应
2. **服务层异常**: 处理业务逻辑错误和超时
3. **检索层异常**: 处理数据库查询失败和网络超时
4. **基础设施异常**: 处理数据库连接、Redis 连接等问题

### 重试策略

- **数据库查询**: 自动重试 3 次
- **LLM 调用**: 指数退避重试
- **向量搜索**: 连接失败时自动切换到备用节点

## 性能优化措施

### 缓存策略

1. **查询标准化缓存**: 缓存 LLM 标准化结果
2. **向量嵌入缓存**: 缓存文本嵌入结果
3. **医学词典缓存**: 应用启动时预加载医学术语

### 并发优化

1. **并行检索**: 使用 `asyncio.gather` 并行执行多种检索方法
2. **连接池**: 数据库连接池和 Redis 连接池
3. **会话管理**: 为并发检索创建独立数据库会话

## 监控和日志

### 关键监控指标

- **处理时间**: 每个阶段的处理时间监控
- **缓存命中率**: 查询缓存和嵌入缓存命中率
- **错误率**: 各层级的错误发生率
- **并发数**: 同时处理的请求数量

### 日志追踪

- **请求ID**: 每个请求的唯一标识符
- **客户端IP**: 请求来源IP地址
- **处理阶段**: 记录每个关键阶段的开始和结束

## 部署和扩展

### 水平扩展策略

1. **无状态服务**: 服务层无状态，可以水平扩展
2. **数据库分片**: 按科室或疾病类型进行数据分片
3. **缓存集群**: Redis 集群提供分布式缓存

### 容灾方案

1. **多区域部署**: 跨区域部署服务实例
2. **数据库备份**: 定期数据库备份和快照
3. **降级策略**: 在 LLM 服务不可用时降级到规则引擎

---

*文档最后更新: 2024年*  
*维护团队: 智能推荐组*