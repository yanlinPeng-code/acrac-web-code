"""RAGAS评测相关的数据模式"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

# ==================== 枚举类型 ====================

class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class EvaluationMetricType(str, Enum):
    """评测指标类型"""
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"

# ==================== 基础数据模型 ====================

class TestCaseBase(BaseModel):
    """测试用例基础模型"""
    question_id: Optional[str] = Field(None, description="问题ID")
    clinical_query: str = Field(..., description="临床查询")
    ground_truth: str = Field(..., description="标准答案")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class TestCaseCreate(TestCaseBase):
    """创建测试用例"""
    pass

class TestCaseResponse(TestCaseBase):
    """测试用例响应"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== 文件上传相关 ====================

class FileUploadRequest(BaseModel):
    """文件上传请求"""
    file_name: str = Field(..., description="文件名")
    file_type: str = Field(..., description="文件类型")
    description: Optional[str] = Field(None, description="文件描述")

class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str = Field(..., description="文件ID")
    file_name: str = Field(..., description="文件名")
    file_path: str = Field(..., description="文件路径")
    file_size: int = Field(..., description="文件大小")
    upload_time: datetime = Field(..., description="上传时间")
    status: str = Field(..., description="处理状态")
    batch_id: Optional[str] = Field(None, description="数据批次ID")
    total_records: Optional[int] = Field(None, description="总记录数")
    valid_records: Optional[int] = Field(None, description="有效记录数")
    preview_data: Optional[List[TestCaseBase]] = Field(None, description="数据预览")

class DataPreprocessRequest(BaseModel):
    """数据预处理请求"""
    file_id: str = Field(..., description="文件ID")
    preprocessing_options: Optional[Dict[str, Any]] = Field(None, description="预处理选项")

class DataPreprocessResponse(BaseModel):
    """数据预处理响应"""
    file_id: str = Field(..., description="文件ID")
    processed_data: List[TestCaseBase] = Field(..., description="处理后的测试用例")
    total_cases: int = Field(..., description="总用例数")
    valid_cases: int = Field(..., description="有效用例数")
    invalid_cases: int = Field(..., description="无效用例数")
    processing_time: float = Field(..., description="处理时间")

# ==================== 评测相关 ====================

class RAGASEvaluationRequest(BaseModel):
    """RAGAS评测请求"""
    file_id: Optional[str] = Field(None, description="文件ID（兼容旧版本）")
    test_cases: Optional[List[TestCaseBase]] = Field(None, description="测试用例列表")
    scenario_ids: Optional[List[int]] = Field(None, description="临床场景ID列表")
    batch_id: Optional[str] = Field(None, description="数据批次ID")
    model_name: str = Field("gpt-3.5-turbo", description="模型名称")
    base_url: Optional[str] = Field("https://api.siliconflow.cn/v1", description="模型API基础URL")
    evaluation_config: Optional[Dict[str, Any]] = Field(None, description="评测配置")
    task_name: Optional[str] = Field(None, description="任务名称")
    async_mode: bool = Field(True, description="是否异步执行")
    
    def validate_input(self):
        """验证输入参数"""
        provided_params = sum([
            bool(self.test_cases),
            bool(self.file_id),
            bool(self.scenario_ids),
            bool(self.batch_id)
        ])
        
        if provided_params == 0:
            raise ValueError("必须提供test_cases、file_id、scenario_ids或batch_id中的一个")
        if provided_params > 1:
            raise ValueError("只能提供test_cases、file_id、scenario_ids或batch_id中的一个")

class RAGASScores(BaseModel):
    """RAGAS评分"""
    faithfulness: float = Field(..., ge=0.0, le=1.0, description="忠实度")
    answer_relevancy: float = Field(..., ge=0.0, le=1.0, description="答案相关性")
    context_precision: float = Field(..., ge=0.0, le=1.0, description="上下文精确度")
    context_recall: float = Field(..., ge=0.0, le=1.0, description="上下文召回率")

class EvaluationResult(BaseModel):
    """单个评测结果"""
    question_id: Optional[str] = Field(None, description="问题ID")
    clinical_query: str = Field(..., description="临床查询")
    ground_truth: str = Field(..., description="标准答案")
    ragas_scores: RAGASScores = Field(..., description="RAGAS评分")
    # 可选扩展字段（用于‘中间/最终结果’展示）
    rag_answer: Optional[str] = Field(None, description="RAG-LLM生成的答案文本")
    contexts: Optional[List[str]] = Field(None, description="用于评测的上下文片段")
    model: Optional[str] = Field(None, description="推理/评测使用的LLM模型名")
    inference_ms: Optional[int] = Field(None, description="推理耗时（毫秒）")
    evaluation_ms: Optional[int] = Field(None, description="评测耗时（毫秒）")
    trace: Optional[Dict[str, Any]] = Field(None, description="推理trace（裁剪版）")
    timestamp: float = Field(..., description="时间戳")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class RAGASEvaluationResponse(BaseModel):
    """RAGAS评测响应"""
    status: str = Field(..., description="评测状态")
    task_id: Optional[str] = Field(None, description="任务ID（异步模式）")
    results: Optional[List[EvaluationResult]] = Field(None, description="评测结果")
    summary: Optional[RAGASScores] = Field(None, description="综合评分")
    processing_time: Optional[float] = Field(None, description="处理时间")
    error: Optional[str] = Field(None, description="错误信息")

# ==================== 任务管理相关 ====================

class EvaluationTaskBase(BaseModel):
    """评测任务基础模型"""
    task_name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    model_name: str = Field(..., description="使用的模型")
    total_cases: int = Field(..., description="总测试用例数")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")

class EvaluationTaskCreate(EvaluationTaskBase):
    """创建评测任务"""
    test_cases: List[TestCaseBase] = Field(..., description="测试用例")
    evaluation_config: Optional[Dict[str, Any]] = Field(None, description="评测配置")

class EvaluationTaskUpdate(BaseModel):
    """更新评测任务"""
    task_name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    status: Optional[TaskStatus] = Field(None, description="任务状态")
    progress: Optional[float] = Field(None, ge=0.0, le=100.0, description="进度百分比")
    error_message: Optional[str] = Field(None, description="错误信息")

class EvaluationTaskResponse(EvaluationTaskBase):
    """评测任务响应"""
    id: int
    task_id: str
    progress: float = Field(0.0, description="进度百分比")
    completed_cases: int = Field(0, description="已完成用例数")
    failed_cases: int = Field(0, description="失败用例数")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    processing_time: Optional[float] = Field(None, description="处理时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== 历史记录相关 ====================

class EvaluationHistoryQuery(BaseModel):
    """评测历史查询"""
    task_name: Optional[str] = Field(None, description="任务名称")
    status: Optional[TaskStatus] = Field(None, description="任务状态")
    model_name: Optional[str] = Field(None, description="模型名称")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页大小")

class EvaluationHistoryResponse(BaseModel):
    """评测历史响应"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")
    items: List[EvaluationTaskResponse] = Field(..., description="任务列表")

class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    task: EvaluationTaskResponse = Field(..., description="任务信息")
    results: List[EvaluationResult] = Field(..., description="评测结果")
    summary: Optional[RAGASScores] = Field(None, description="综合评分")
    metrics_distribution: Optional[Dict[str, Any]] = Field(None, description="指标分布")

# ==================== 统计分析相关 ====================

class EvaluationStats(BaseModel):
    """评测统计"""
    total_tasks: int = Field(..., description="总任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    failed_tasks: int = Field(..., description="失败任务数")
    total_test_cases: int = Field(..., description="总测试用例数")
    average_scores: Optional[RAGASScores] = Field(None, description="平均评分")
    model_performance: Optional[Dict[str, RAGASScores]] = Field(None, description="模型性能")

class MetricsAnalysis(BaseModel):
    """指标分析"""
    metric_name: str = Field(..., description="指标名称")
    mean_score: float = Field(..., description="平均分")
    median_score: float = Field(..., description="中位数")
    std_deviation: float = Field(..., description="标准差")
    min_score: float = Field(..., description="最低分")
    max_score: float = Field(..., description="最高分")
    score_distribution: Dict[str, int] = Field(..., description="分数分布")

# ==================== 错误处理相关 ====================

class ErrorResponse(BaseModel):
    """错误响应"""
    error_code: str = Field(..., description="错误代码")
    error_message: str = Field(..., description="错误信息")
    error_details: Optional[Dict[str, Any]] = Field(None, description="错误详情")
    timestamp: datetime = Field(..., description="时间戳")

class ValidationError(BaseModel):
    """验证错误"""
    field: str = Field(..., description="字段名")
    message: str = Field(..., description="错误信息")
    value: Optional[Any] = Field(None, description="错误值")

# ==================== 健康检查相关 ====================

class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    dependencies_installed: bool = Field(..., description="依赖是否安装")
    api_key_configured: bool = Field(..., description="API密钥是否配置")
    database_connected: bool = Field(..., description="数据库是否连接")
    redis_connected: bool = Field(..., description="Redis是否连接")
    timestamp: float = Field(..., description="检查时间戳")
    version: Optional[str] = Field(None, description="服务版本")
    uptime: Optional[float] = Field(None, description="运行时间")