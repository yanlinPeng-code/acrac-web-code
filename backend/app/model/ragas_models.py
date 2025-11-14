"""RAGAS评测数据模型 - 使用 SQLModel 实现"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text, TIMESTAMP, JSON as SQLALCHEMY_JSON
from sqlalchemy.sql import func

class TaskStatus(str, Enum):
    """评测任务状态枚举"""
    PENDING = "pending"          # 待处理
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消

class EvaluationTask(SQLModel, table=True):
    """RAGAS评测任务表"""
    __tablename__ = "evaluation_tasks"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    task_id: str = Field(max_length=50, unique=True, index=True, description="任务唯一标识")
    task_name: str = Field(max_length=255, description="任务名称")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="任务描述")
    status: str = Field(default=TaskStatus.PENDING, max_length=20, description="任务状态")
    
    # 文件信息
    file_path: Optional[str] = Field(default=None, max_length=500, description="上传文件路径")
    file_name: Optional[str] = Field(default=None, max_length=255, description="原始文件名")
    file_size: Optional[int] = Field(default=None, description="文件大小（字节）")
    
    # 进度信息
    total_scenarios: int = Field(default=0, description="总场景数")
    completed_scenarios: int = Field(default=0, description="已完成场景数")
    failed_scenarios: int = Field(default=0, description="失败场景数")
    progress_percentage: float = Field(default=0.0, description="完成百分比")
    
    # 评测配置
    evaluation_config: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="评测配置参数")
    
    # 结果统计
    avg_faithfulness: Optional[float] = Field(default=None, description="平均忠实度得分")
    avg_answer_relevancy: Optional[float] = Field(default=None, description="平均答案相关性得分")
    avg_context_precision: Optional[float] = Field(default=None, description="平均上下文精确度得分")
    avg_context_recall: Optional[float] = Field(default=None, description="平均上下文召回率得分")
    avg_overall_score: Optional[float] = Field(default=None, description="平均总体得分")
    
    # 时间信息
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="完成时间")
    estimated_completion: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="预计完成时间")
    
    # 错误信息
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="错误信息")
    error_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="详细错误信息")
    
    # 系统信息
    created_by: Optional[str] = Field(default=None, max_length=100, description="创建者")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="创建时间"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now()),
        description="更新时间"
    )
    
    # Celery任务信息
    celery_task_id: Optional[str] = Field(default=None, max_length=255, description="Celery任务ID")
    
    # Relationships
    scenario_results: List["ScenarioResult"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    
    def __repr__(self):
        return f"<EvaluationTask(task_id='{self.task_id}', status='{self.status}', progress={self.progress_percentage}%)>"
    
    def update_progress(self):
        """更新进度百分比"""
        if self.total_scenarios > 0:
            self.progress_percentage = (self.completed_scenarios / self.total_scenarios) * 100
        else:
            self.progress_percentage = 0.0
    
    def calculate_average_scores(self):
        """计算平均得分"""
        if not self.scenario_results:
            return
        
        completed_results = [r for r in self.scenario_results if r.status == 'completed']
        if not completed_results:
            return
        
        count = len(completed_results)
        self.avg_faithfulness = sum(r.faithfulness_score or 0 for r in completed_results) / count
        self.avg_answer_relevancy = sum(r.answer_relevancy_score or 0 for r in completed_results) / count
        self.avg_context_precision = sum(r.context_precision_score or 0 for r in completed_results) / count
        self.avg_context_recall = sum(r.context_recall_score or 0 for r in completed_results) / count
        self.avg_overall_score = sum(r.overall_score or 0 for r in completed_results) / count

class ScenarioResult(SQLModel, table=True):
    """场景评测结果表"""
    __tablename__ = "scenario_results"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    scenario_id: str = Field(max_length=50, index=True, description="场景唯一标识")
    task_id: str = Field(foreign_key="evaluation_tasks.task_id", ondelete="CASCADE", index=True)
    
    # 关联临床场景数据
    clinical_scenario_id: Optional[int] = Field(
        default=None,
        foreign_key="clinical_scenario_data.id",
        ondelete="SET NULL",
        index=True,
        description="关联的临床场景数据ID"
    )
    
    # 原始数据（仏clinical_scenarios表获取，这里保留副本用于历史记录）
    question_number: Optional[str] = Field(default=None, max_length=20, description="题号")
    clinical_scenario: Optional[str] = Field(default=None, sa_column=Column(Text), description="临床场景描述")
    standard_answer: Optional[str] = Field(default=None, max_length=500, description="标准答案（首选检查项目）")
    
    # RAG-LLM推理结果
    rag_question: Optional[str] = Field(default=None, sa_column=Column(Text), description="RAG系统处理的问题")
    rag_answer: Optional[str] = Field(default=None, sa_column=Column(Text), description="RAG-LLM生成的答案")
    rag_contexts: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="RAG检索的上下文列表")
    rag_trace_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="RAG推理过程追踪数据")
    
    # 数据适配器处理结果
    adapted_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="适配器转换后的标准格式数据")
    
    # RAGAS评分结果
    faithfulness_score: Optional[float] = Field(default=None, description="忠实度得分 (0-1)")
    answer_relevancy_score: Optional[float] = Field(default=None, description="答案相关性得分 (0-1)")
    context_precision_score: Optional[float] = Field(default=None, description="上下文精确度得分 (0-1)")
    context_recall_score: Optional[float] = Field(default=None, description="上下文召回率得分 (0-1)")
    overall_score: Optional[float] = Field(default=None, description="总体得分 (0-1)")
    
    # 详细评估信息
    ragas_evaluation_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="RAGAS详细评估结果")
    evaluation_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="评估元数据")
    
    # 状态信息
    status: str = Field(default="pending", max_length=20, description="处理状态: pending, processing, completed, failed")
    processing_stage: Optional[str] = Field(default=None, max_length=50, description="当前处理阶段: inference, parsing, evaluation")
    
    # 时间信息
    inference_started_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="推理开始时间")
    inference_completed_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="推理完成时间")
    evaluation_started_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="评估开始时间")
    evaluation_completed_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="评估完成时间")
    
    # 性能指标
    inference_duration_ms: Optional[int] = Field(default=None, description="推理耗时（毫秒）")
    evaluation_duration_ms: Optional[int] = Field(default=None, description="评估耗时（毫秒）")
    total_duration_ms: Optional[int] = Field(default=None, description="总耗时（毫秒）")
    
    # 错误信息
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="错误信息")
    error_stage: Optional[str] = Field(default=None, max_length=50, description="出错阶段")
    error_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="详细错误信息")
    
    # 系统信息
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="创建时间"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now()),
        description="更新时间"
    )
    
    # Celery子任务信息
    inference_task_id: Optional[str] = Field(default=None, max_length=255, description="推理任务ID")
    parsing_task_id: Optional[str] = Field(default=None, max_length=255, description="解析任务ID")
    evaluation_task_id: Optional[str] = Field(default=None, max_length=255, description="评估任务ID")
    
    # Relationships
    task: Optional["EvaluationTask"] = Relationship(back_populates="scenario_results")
    clinical_scenario: Optional["ClinicalScenarioData"] = Relationship(back_populates="evaluation_results")
    
    def __repr__(self):
        return f"<ScenarioResult(scenario_id='{self.scenario_id}', status='{self.status}', overall_score={self.overall_score})>"
    
    def update_duration(self):
        """更新总耗时"""
        if self.inference_started_at and self.evaluation_completed_at:
            delta = self.evaluation_completed_at - self.inference_started_at
            self.total_duration_ms = int(delta.total_seconds() * 1000)
    
    def is_completed(self) -> bool:
        """检查是否已完成"""
        return self.status == 'completed' and all([
            self.faithfulness_score is not None,
            self.answer_relevancy_score is not None,
            self.context_precision_score is not None,
            self.context_recall_score is not None,
            self.overall_score is not None
        ])

class EvaluationMetrics(SQLModel, table=True):
    """评测指标历史记录表"""
    __tablename__ = "evaluation_metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    task_id: str = Field(foreign_key="evaluation_tasks.task_id", ondelete="CASCADE")
    metric_name: str = Field(max_length=100, description="指标名称")
    metric_value: float = Field(description="指标值")
    metric_category: Optional[str] = Field(default=None, max_length=50, description="指标类别: ragas, performance, custom")
    
    # 计算信息
    calculation_method: Optional[str] = Field(default=None, max_length=100, description="计算方法")
    sample_size: Optional[int] = Field(default=None, description="样本数量")
    confidence_interval: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="置信区间")
    
    # 时间信息
    measured_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="测量时间"
    )
    
    def __repr__(self):
        return f"<EvaluationMetrics(task_id='{self.task_id}', metric='{self.metric_name}', value={self.metric_value})>"

class DataAdapterLog(SQLModel, table=True):
    """数据适配器日志表"""
    __tablename__ = "data_adapter_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    scenario_id: str = Field(max_length=50, index=True)
    task_id: str = Field(foreign_key="evaluation_tasks.task_id", ondelete="CASCADE")
    
    # 适配信息
    input_format: Optional[str] = Field(default=None, max_length=100, description="输入数据格式")
    output_format: Optional[str] = Field(default=None, max_length=100, description="输出数据格式")
    adapter_version: Optional[str] = Field(default=None, max_length=20, description="适配器版本")
    
    # 数据内容
    raw_input_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="原始输入数据")
    transformed_output_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="转换后输出数据")
    
    # 转换统计
    transformation_rules_applied: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="应用的转换规则")
    data_quality_score: Optional[float] = Field(default=None, description="数据质量评分")
    
    # 性能信息
    processing_time_ms: Optional[int] = Field(default=None, description="处理耗时（毫秒）")
    
    # 状态信息
    status: str = Field(default="success", max_length=20, description="适配状态: success, warning, error")
    warnings: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="警告信息")
    errors: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="错误信息")
    
    # 时间信息
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="创建时间"
    )
    
    def __repr__(self):
        return f"<DataAdapterLog(scenario_id='{self.scenario_id}', status='{self.status}', quality_score={self.data_quality_score})>"