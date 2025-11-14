"""
ACRAC数据模型 - 优化后的五表分离架构
使用 SQLModel 实现
"""
from typing import Optional, List
from datetime import datetime, date
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text, TIMESTAMP
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

class Panel(SQLModel, table=True):
    """Panel表 - 科室/专科"""
    __tablename__ = "panels"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    semantic_id: str = Field(max_length=20, unique=True, index=True, description="语义化ID: P0001, P0002...")
    name_en: str = Field(max_length=255, description="英文名称")
    name_zh: str = Field(max_length=255, description="中文名称")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="描述")
    is_active: bool = Field(default=True, description="是否激活")
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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1024)), description="向量嵌入")
    
    # Relationships
    topics: List["Topic"] = Relationship(back_populates="panel", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    scenarios: List["ClinicalScenario"] = Relationship(back_populates="panel", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    def __repr__(self):
        return f"<Panel(semantic_id='{self.semantic_id}', name_zh='{self.name_zh}')>"

class Topic(SQLModel, table=True):
    """Topic表 - 临床主题"""
    __tablename__ = "topics"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    semantic_id: str = Field(max_length=20, unique=True, index=True, description="语义化ID: T0001, T0002...")
    panel_id: int = Field(foreign_key="panels.id", ondelete="CASCADE", description="关联的Panel ID")
    name_en: str = Field(max_length=500, description="英文名称")
    name_zh: str = Field(max_length=500, description="中文名称")
    description: Optional[str] = Field(default=None, sa_column=Column(Text), description="描述")
    is_active: bool = Field(default=True, description="是否激活")
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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1024)), description="层次化向量嵌入")
    
    # Relationships
    panel: Optional["Panel"] = Relationship(back_populates="topics")
    scenarios: List["ClinicalScenario"] = Relationship(back_populates="topic", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    def __repr__(self):
        return f"<Topic(semantic_id='{self.semantic_id}', name_zh='{self.name_zh}')>"

class ClinicalScenario(SQLModel, table=True):
    """ClinicalScenario表 - 临床场景"""
    __tablename__ = "clinical_scenarios"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    semantic_id: str = Field(max_length=20, unique=True, index=True, description="语义化ID: S0001, S0002...")
    panel_id: int = Field(foreign_key="panels.id", ondelete="CASCADE", description="关联的Panel ID")
    topic_id: int = Field(foreign_key="topics.id", ondelete="CASCADE", description="关联的Topic ID")
    description_en: str = Field(sa_column=Column(Text), description="英文描述")
    description_zh: str = Field(sa_column=Column(Text), description="中文描述")
    clinical_context: Optional[str] = Field(default=None, sa_column=Column(Text), description="临床上下文")
    patient_population: Optional[str] = Field(default=None, max_length=100, description="患者人群：孕妇、儿童、老年等")
    risk_level: Optional[str] = Field(default=None, max_length=50, description="风险等级：高风险、中风险、低风险")
    age_group: Optional[str] = Field(default=None, max_length=50, description="年龄组：40岁以上、25岁以下等")
    gender: Optional[str] = Field(default=None, max_length=20, description="性别：女性、男性、不限")
    pregnancy_status: Optional[str] = Field(default=None, max_length=50, description="妊娠状态：妊娠期、哺乳期、非妊娠期")
    urgency_level: Optional[str] = Field(default=None, max_length=50, description="紧急程度：急诊、择期")
    symptom_category: Optional[str] = Field(default=None, max_length=100, description="症状分类：疼痛、肿块、出血等")
    is_active: bool = Field(default=True, description="是否激活")
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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(2560)), description="层次化向量嵌入")
    
    # Relationships
    panel: Optional["Panel"] = Relationship(back_populates="scenarios")
    topic: Optional["Topic"] = Relationship(back_populates="scenarios")
    recommendations: List["ClinicalRecommendation"] = Relationship(back_populates="scenario", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    def __repr__(self):
        return f"<ClinicalScenario(semantic_id='{self.semantic_id}', patient_population='{self.patient_population}')>"

class ProcedureDictionary(SQLModel, table=True):
    """ProcedureDictionary表 - 检查项目字典"""
    __tablename__ = "procedure_dictionary"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    semantic_id: str = Field(max_length=20, unique=True, index=True, description="语义化ID: PR0001, PR0002...")
    name_en: str = Field(max_length=500, description="英文名称")
    name_zh: str = Field(max_length=500, description="中文名称")
    modality: Optional[str] = Field(default=None, max_length=50, description="检查方式：CT, MRI, US, XR等")
    body_part: Optional[str] = Field(default=None, max_length=100, description="检查部位：头部、胸部、腹部等")
    contrast_used: bool = Field(default=False, description="是否使用对比剂")
    radiation_level: Optional[str] = Field(default=None, max_length=50, description="辐射等级：无、低、中、高")
    exam_duration: Optional[int] = Field(default=None, description="检查时长（分钟）")
    preparation_required: bool = Field(default=False, description="是否需要准备")
    standard_code: Optional[str] = Field(default=None, max_length=50, description="标准编码（医保编码等）")
    icd10_code: Optional[str] = Field(default=None, max_length=20, description="ICD10编码")
    cpt_code: Optional[str] = Field(default=None, max_length=20, description="CPT编码")
    description_en: Optional[str] = Field(default=None, sa_column=Column(Text), description="英文描述")
    description_zh: Optional[str] = Field(default=None, sa_column=Column(Text), description="中文描述")
    is_active: bool = Field(default=True, description="是否激活")
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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1024)), description="独立向量嵌入")
    
    # Relationships
    recommendations: List["ClinicalRecommendation"] = Relationship(back_populates="procedure", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    
    def __repr__(self):
        return f"<ProcedureDictionary(semantic_id='{self.semantic_id}', name_zh='{self.name_zh}', modality='{self.modality}')>"

class ClinicalRecommendation(SQLModel, table=True):
    """ClinicalRecommendation表 - 临床推荐关系（核心表）"""
    __tablename__ = "clinical_recommendations"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    semantic_id: str = Field(max_length=50, unique=True, index=True, description="语义化ID: CR000001, CR000002...")
    scenario_id: str = Field(foreign_key="clinical_scenarios.semantic_id", ondelete="CASCADE", description="关联的场景ID")
    procedure_id: str = Field(foreign_key="procedure_dictionary.semantic_id", ondelete="CASCADE", description="关联的检查项目ID")
    appropriateness_rating: Optional[int] = Field(default=None, description="适宜性评分 1-9")
    appropriateness_category: Optional[str] = Field(default=None, max_length=100, description="适宜性类别")
    appropriateness_category_zh: Optional[str] = Field(default=None, max_length=100, description="适宜性类别中文")
    reasoning_en: Optional[str] = Field(default=None, sa_column=Column(Text), description="英文推荐理由")
    reasoning_zh: Optional[str] = Field(default=None, sa_column=Column(Text), description="中文推荐理由")
    evidence_level: Optional[str] = Field(default=None, max_length=50, description="证据强度")
    median_rating: Optional[float] = Field(default=None, description="中位数评分")
    rating_variance: Optional[float] = Field(default=None, description="评分方差")
    consensus_level: Optional[str] = Field(default=None, max_length=50, description="共识水平")
    adult_radiation_dose: Optional[str] = Field(default=None, max_length=50, description="成人辐射剂量")
    pediatric_radiation_dose: Optional[str] = Field(default=None, max_length=50, description="儿童辐射剂量")
    contraindications: Optional[str] = Field(default=None, sa_column=Column(Text), description="禁忌症")
    special_considerations: Optional[str] = Field(default=None, sa_column=Column(Text), description="特殊考虑")
    pregnancy_safety: Optional[str] = Field(default=None, max_length=50, description="妊娠安全性：安全、禁忌、谨慎使用")
    is_generated: bool = Field(default=False, description="是否AI生成")
    confidence_score: float = Field(default=1.0, description="置信度评分")
    last_reviewed_date: Optional[date] = Field(default=None, description="最后审查日期")
    reviewer_id: Optional[int] = Field(default=None, description="审查者ID")
    is_active: bool = Field(default=True, description="是否激活")
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
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1024)), description="完整临床决策向量嵌入")
    
    # Relationships
    scenario: Optional["ClinicalScenario"] = Relationship(back_populates="recommendations")
    procedure: Optional["ProcedureDictionary"] = Relationship(back_populates="recommendations")
    
    def __repr__(self):
        return f"<ClinicalRecommendation(semantic_id='{self.semantic_id}', rating={self.appropriateness_rating})>"

# 辅助表
class VectorSearchLog(SQLModel, table=True):
    """向量搜索日志表"""
    __tablename__ = "vector_search_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    query_text: str = Field(sa_column=Column(Text), description="搜索文本")
    query_type: Optional[str] = Field(default=None, max_length=50, description="查询类型")
    search_vector: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(1024)), description="搜索向量")
    results_count: Optional[int] = Field(default=None, description="结果数量")
    search_time_ms: Optional[int] = Field(default=None, description="搜索耗时（毫秒）")
    user_id: Optional[int] = Field(default=None, description="用户ID")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="创建时间"
    )
    
    def __repr__(self):
        return f"<VectorSearchLog(id={self.id}, query='{self.query_text[:50]}...')>"

class DataUpdateHistory(SQLModel, table=True):
    """数据更新历史表"""
    __tablename__ = "data_update_history"
    
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    table_name: str = Field(max_length=50, description="表名")
    record_id: str = Field(max_length=50, description="记录ID")
    operation: str = Field(max_length=20, description="操作类型：INSERT, UPDATE, DELETE")
    old_data: Optional[str] = Field(default=None, sa_column=Column(Text), description="旧数据（JSON格式）")
    new_data: Optional[str] = Field(default=None, sa_column=Column(Text), description="新数据（JSON格式）")
    user_id: Optional[int] = Field(default=None, description="操作用户ID")
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.now()),
        description="创建时间"
    )
    
    def __repr__(self):
        return f"<DataUpdateHistory(id={self.id}, table='{self.table_name}', operation='{self.operation}')>"