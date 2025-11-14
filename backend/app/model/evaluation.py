from typing import Optional, Dict, Any
from datetime import datetime
from sqlmodel import Field, SQLModel, Column
from sqlalchemy import Text, TIMESTAMP, JSON as SQLALCHEMY_JSON
from sqlalchemy.sql import func


class EvaluationResult(SQLModel, table=True):
    """评估结果模型"""
    __tablename__ = "evaluation_results"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    task_id: int = Field(description="关联的任务ID")
    result_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="结果数据")
    status: str = Field(default="pending", max_length=50, description="结果状态")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )


class TestData(SQLModel, table=True):
    """测试数据模型"""
    __tablename__ = "test_data"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    question_id: str = Field(max_length=255, index=True, description="问题ID")
    clinical_query: str = Field(sa_column=Column(Text), description="临床查询")
    ground_truth: str = Field(sa_column=Column(Text), description="标准答案")
    source_file: Optional[str] = Field(default=None, max_length=255, description="来源文件")
    upload_batch: Optional[str] = Field(default=None, max_length=255, description="上传批次")
    is_active: bool = Field(default=True, description="是否激活")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    )