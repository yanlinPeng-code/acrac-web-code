#!/usr/bin/env python3
"""
临床场景数据模型
用于存储上传的Excel文件中的临床场景数据
使用 SQLModel 实现
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text, JSON as SQLALCHEMY_JSON

class ClinicalScenarioData(SQLModel, table=True):
    """临床场景数据表
    
    存储从Excel文件解析的临床场景数据，包括：
    - 题号
    - 临床场景描述
    - 首选检查项目（标准答案）
    - 其他相关信息
    """
    __tablename__ = "clinical_scenario_data"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True, description="主键ID")
    
    # 基本信息
    question_id: str = Field(max_length=50, index=True, description="题号")
    clinical_query: str = Field(sa_column=Column(Text), description="临床场景描述")
    ground_truth: str = Field(sa_column=Column(Text), description="首选检查项目（标准答案）")
    
    # 扩展信息
    category: Optional[str] = Field(default=None, max_length=100, description="分类")
    difficulty: Optional[str] = Field(default=None, max_length=20, description="难度等级")
    keywords: Optional[str] = Field(default=None, sa_column=Column(Text), description="关键词")
    
    # 元数据
    source_file: Optional[str] = Field(default=None, max_length=255, description="来源文件名")
    file_row_number: Optional[int] = Field(default=None, description="文件中的行号")
    upload_batch_id: str = Field(max_length=10, index=True, description="上传批次ID")
    
    # 状态信息
    is_active: bool = Field(default=True, description="是否激活")
    is_validated: bool = Field(default=False, description="是否已验证")
    validation_notes: Optional[str] = Field(default=None, sa_column=Column(Text), description="验证备注")
    
    # 时间戳
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="更新时间")
    
    # 关联关系
    evaluation_results: List["ScenarioResult"] = Relationship(back_populates="clinical_scenario")
    
    def __repr__(self):
        return f"<ClinicalScenario(id={self.id}, question_id='{self.question_id}', query='{self.clinical_query[:50]}...')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "question_id": self.question_id,
            "clinical_query": self.clinical_query,
            "ground_truth": self.ground_truth,
            "category": self.category,
            "difficulty": self.difficulty,
            "keywords": self.keywords,
            "source_file": self.source_file,
            "file_row_number": self.file_row_number,
            "upload_batch_id": self.upload_batch_id,
            "is_active": self.is_active,
            "is_validated": self.is_validated,
            "validation_notes": self.validation_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def to_test_case(self) -> Dict[str, Any]:
        """转换为评测用例格式"""
        return {
            "question_id": self.question_id,
            "clinical_query": self.clinical_query,
            "ground_truth": self.ground_truth,
            "metadata": {
                "id": self.id,
                "category": self.category,
                "difficulty": self.difficulty,
                "keywords": self.keywords,
                "source_file": self.source_file
            }
        }

class DataUploadBatch(SQLModel, table=True):
    """数据上传批次表
    
    记录每次数据上传的批次信息
    """
    __tablename__ = "data_upload_batches"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True, description="主键ID")
    
    # 批次信息
    batch_id: str = Field(max_length=10, unique=True, index=True, description="批次ID")
    batch_name: str = Field(max_length=255, description="批次名称")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="批次描述")
    
    # 文件信息
    original_filename: str = Field(max_length=255, description="原始文件名")
    file_path: Optional[str] = Field(default=None, max_length=500, description="文件存储路径")
    file_size: Optional[int] = Field(default=None, description="文件大小（字节）")
    file_hash: Optional[str] = Field(default=None, max_length=64, description="文件MD5哈希")
    
    # 处理统计
    total_rows: int = Field(default=0, description="总行数")
    valid_rows: int = Field(default=0, description="有效行数")
    invalid_rows: int = Field(default=0, description="无效行数")
    
    # 处理状态
    status: str = Field(default="pending", max_length=20, description="处理状态：pending/processing/completed/failed")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="错误信息")
    processing_log: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(SQLALCHEMY_JSON), description="处理日志")
    
    # 时间戳
    uploaded_at: Optional[datetime] = Field(default_factory=datetime.now, description="上传时间")
    processed_at: Optional[datetime] = Field(default=None, description="处理完成时间")
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="更新时间")
    
    def __repr__(self):
        return f"<DataUploadBatch(id={self.id}, batch_id='{self.batch_id}', filename='{self.original_filename}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "batch_name": self.batch_name,
            "description": self.description,
            "original_filename": self.original_filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "status": self.status,
            "error_message": self.error_message,
            "processing_log": self.processing_log,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }