from typing import Optional, Dict, Any
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text, TIMESTAMP, JSON as SQLALCHEMY_JSON
from sqlalchemy.sql import func

class User(SQLModel, table=True):
    """用户表"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    username: str = Field(max_length=100, unique=True, index=True)
    email: str = Field(max_length=255, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: str = Field(default="viewer", max_length=50, description="用户角色: viewer, editor, reviewer, admin")
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"

class InferenceLog(SQLModel, table=True):
    """推理日志表"""
    __tablename__ = "inference_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    project_id: Optional[str] = Field(default=None, max_length=50, description="项目ID，用于关联Excel评测任务")
    query_text: str = Field(sa_column=Column(Text), description="查询文本")
    query_language: str = Field(default="zh", max_length=10, description="查询语言")
    inference_method: Optional[str] = Field(default=None, max_length=50, description="推理方法: rag, rule_based, case_voting")
    result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="推理结果")
    confidence_score: Optional[float] = Field(default=None, description="置信度分数")
    success: bool = Field(description="是否成功")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="错误信息")
    execution_time: Optional[float] = Field(default=None, description="执行时间(秒)")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    
    # Relationships
    user: Optional["User"] = Relationship()
    
    def __repr__(self):
        return f"<InferenceLog(id={self.id}, method='{self.inference_method}', success={self.success})>"

class Rule(SQLModel, table=True):
    """规则表"""
    __tablename__ = "rules"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    rule_name: str = Field(max_length=255, description="规则名称")
    rule_content: Dict[str, Any] = Field(sa_column=Column(SQLALCHEMY_JSON), description="规则内容")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="规则描述")
    status: str = Field(default="draft", max_length=50, description="状态: draft, review, approved, published, deprecated")
    priority: int = Field(default=100, description="优先级，数字越小优先级越高")
    created_by: int = Field(foreign_key="users.id")
    approved_by: Optional[int] = Field(default=None, foreign_key="users.id")
    version: int = Field(default=1, description="版本号")
    is_active: bool = Field(default=True, description="是否激活")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    )
    
    # Relationships
    creator: Optional["User"] = Relationship(sa_relationship_kwargs={"foreign_keys": "[Rule.created_by]"})
    approver: Optional["User"] = Relationship(sa_relationship_kwargs={"foreign_keys": "[Rule.approved_by]"})
    
    def __repr__(self):
        return f"<Rule(id={self.id}, name='{self.rule_name}', status='{self.status}')>"

class DataImportTask(SQLModel, table=True):
    """数据导入任务表"""
    __tablename__ = "data_import_tasks"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    user_id: int = Field(foreign_key="users.id")
    filename: str = Field(max_length=255, description="文件名")
    file_size: Optional[int] = Field(default=None, description="文件大小(字节)")
    file_type: Optional[str] = Field(default=None, max_length=50, description="文件类型")
    status: str = Field(default="pending", max_length=50, description="状态: pending, processing, completed, failed")
    total_records: Optional[int] = Field(default=None, description="总记录数")
    processed_records: int = Field(default=0, description="已处理记录数")
    success_records: int = Field(default=0, description="成功记录数")
    error_records: int = Field(default=0, description="错误记录数")
    error_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="错误详情")
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP), description="完成时间")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    
    # Relationships
    user: Optional["User"] = Relationship()
    
    def __repr__(self):
        return f"<DataImportTask(id={self.id}, filename='{self.filename}', status='{self.status}')>"

class EvaluationProject(SQLModel, table=True):
    """评测项目表"""
    __tablename__ = "evaluation_projects"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    project_id: str = Field(max_length=50, unique=True, description="项目唯一标识符")
    project_name: str = Field(max_length=255, description="项目名称")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="项目描述")
    excel_filename: str = Field(max_length=255, description="Excel文件名")
    total_questions: int = Field(default=0, description="总问题数")
    processed_questions: int = Field(default=0, description="已处理问题数")
    status: str = Field(default="created", max_length=50, description="状态: created, processing, completed, failed")
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    )
    
    # Relationships
    creator: Optional["User"] = Relationship()
    
    def __repr__(self):
        return f"<EvaluationProject(id={self.id}, project_id='{self.project_id}', status='{self.status}')>"

class ExcelEvaluationData(SQLModel, table=True):
    """Excel评测数据表"""
    __tablename__ = "excel_evaluation_data"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    project_id: str = Field(foreign_key="evaluation_projects.project_id", description="关联的评测项目ID")
    task_id: str = Field(max_length=50, description="评测任务ID")
    filename: str = Field(max_length=255, description="Excel文件名")
    question: str = Field(sa_column=Column(Text), description="问题")
    ground_truth: str = Field(sa_column=Column(Text), description="标准答案")
    contexts: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="上下文信息")
    answer: Optional[str] = Field(default=None, sa_column=Column(Text), description="模型回答")
    
    # RAGAS评分字段
    faithfulness: Optional[float] = Field(default=None, description="忠实度评分")
    answer_relevancy: Optional[float] = Field(default=None, description="答案相关性评分")
    context_precision: Optional[float] = Field(default=None, description="上下文精确度评分")
    context_recall: Optional[float] = Field(default=None, description="上下文召回率评分")
    
    # 评测状态
    status: str = Field(default="pending", max_length=50, description="状态: pending, completed, failed")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="错误信息")
    
    # 时间戳
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    )
    
    # Relationships
    project: Optional["EvaluationProject"] = Relationship()
    
    def __repr__(self):
        return f"<ExcelEvaluationData(id={self.id}, project_id='{self.project_id}', task_id='{self.task_id}', status='{self.status}')>"
