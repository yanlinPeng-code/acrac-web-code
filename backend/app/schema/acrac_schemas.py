"""
ACRAC数据模式 - 优化后的五表分离架构
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date

# ==================== Panel Schemas ====================

class PanelBase(BaseModel):
    name_en: str = Field(..., description="英文名称")
    name_zh: str = Field(..., description="中文名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: bool = Field(True, description="是否激活")

class PanelCreate(PanelBase):
    pass

class PanelUpdate(BaseModel):
    name_en: Optional[str] = Field(None, description="英文名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: Optional[bool] = Field(None, description="是否激活")

class PanelResponse(PanelBase):
    id: int
    semantic_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Topic Schemas ====================

class TopicBase(BaseModel):
    panel_id: int = Field(..., description="Panel ID")
    name_en: str = Field(..., description="英文名称")
    name_zh: str = Field(..., description="中文名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: bool = Field(True, description="是否激活")

class TopicCreate(TopicBase):
    pass

class TopicUpdate(BaseModel):
    panel_id: Optional[int] = Field(None, description="Panel ID")
    name_en: Optional[str] = Field(None, description="英文名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: Optional[bool] = Field(None, description="是否激活")

class TopicResponse(TopicBase):
    id: int
    semantic_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Clinical Scenario Schemas ====================

class ClinicalScenarioBase(BaseModel):
    panel_id: int = Field(..., description="Panel ID")
    topic_id: int = Field(..., description="Topic ID")
    description_en: str = Field(..., description="英文描述")
    description_zh: str = Field(..., description="中文描述")
    clinical_context: Optional[str] = Field(None, description="临床上下文")
    patient_population: Optional[str] = Field(None, description="患者人群")
    risk_level: Optional[str] = Field(None, description="风险等级")
    age_group: Optional[str] = Field(None, description="年龄组")
    gender: Optional[str] = Field(None, description="性别")
    pregnancy_status: Optional[str] = Field(None, description="妊娠状态")
    urgency_level: Optional[str] = Field(None, description="紧急程度")
    symptom_category: Optional[str] = Field(None, description="症状分类")
    is_active: bool = Field(True, description="是否激活")

class ClinicalScenarioCreate(ClinicalScenarioBase):
    pass

class ClinicalScenarioUpdate(BaseModel):
    panel_id: Optional[int] = Field(None, description="Panel ID")
    topic_id: Optional[int] = Field(None, description="Topic ID")
    description_en: Optional[str] = Field(None, description="英文描述")
    description_zh: Optional[str] = Field(None, description="中文描述")
    clinical_context: Optional[str] = Field(None, description="临床上下文")
    patient_population: Optional[str] = Field(None, description="患者人群")
    risk_level: Optional[str] = Field(None, description="风险等级")
    age_group: Optional[str] = Field(None, description="年龄组")
    gender: Optional[str] = Field(None, description="性别")
    pregnancy_status: Optional[str] = Field(None, description="妊娠状态")
    urgency_level: Optional[str] = Field(None, description="紧急程度")
    symptom_category: Optional[str] = Field(None, description="症状分类")
    is_active: Optional[bool] = Field(None, description="是否激活")

class ClinicalScenarioResponse(ClinicalScenarioBase):
    id: int
    semantic_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Procedure Dictionary Schemas ====================

class ProcedureDictionaryBase(BaseModel):
    name_en: str = Field(..., description="英文名称")
    name_zh: str = Field(..., description="中文名称")
    modality: Optional[str] = Field(None, description="检查方式")
    body_part: Optional[str] = Field(None, description="检查部位")
    contrast_used: bool = Field(False, description="是否使用对比剂")
    radiation_level: Optional[str] = Field(None, description="辐射等级")
    exam_duration: Optional[int] = Field(None, description="检查时长（分钟）")
    preparation_required: bool = Field(False, description="是否需要准备")
    standard_code: Optional[str] = Field(None, description="标准编码")
    icd10_code: Optional[str] = Field(None, description="ICD10编码")
    cpt_code: Optional[str] = Field(None, description="CPT编码")
    description_en: Optional[str] = Field(None, description="英文描述")
    description_zh: Optional[str] = Field(None, description="中文描述")
    is_active: bool = Field(True, description="是否激活")

class ProcedureDictionaryCreate(ProcedureDictionaryBase):
    pass

class ProcedureDictionaryUpdate(BaseModel):
    name_en: Optional[str] = Field(None, description="英文名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    modality: Optional[str] = Field(None, description="检查方式")
    body_part: Optional[str] = Field(None, description="检查部位")
    contrast_used: Optional[bool] = Field(None, description="是否使用对比剂")
    radiation_level: Optional[str] = Field(None, description="辐射等级")
    exam_duration: Optional[int] = Field(None, description="检查时长（分钟）")
    preparation_required: Optional[bool] = Field(None, description="是否需要准备")
    standard_code: Optional[str] = Field(None, description="标准编码")
    icd10_code: Optional[str] = Field(None, description="ICD10编码")
    cpt_code: Optional[str] = Field(None, description="CPT编码")
    description_en: Optional[str] = Field(None, description="英文描述")
    description_zh: Optional[str] = Field(None, description="中文描述")
    is_active: Optional[bool] = Field(None, description="是否激活")

class ProcedureDictionaryResponse(ProcedureDictionaryBase):
    id: int
    semantic_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== Clinical Recommendation Schemas ====================

class ClinicalRecommendationBase(BaseModel):
    scenario_id: str = Field(..., description="临床场景ID")
    procedure_id: str = Field(..., description="检查项目ID")
    appropriateness_rating: int = Field(..., ge=1, le=9, description="适宜性评分 1-9")
    appropriateness_category: Optional[str] = Field(None, description="适宜性类别")
    appropriateness_category_zh: Optional[str] = Field(None, description="适宜性类别中文")
    reasoning_en: Optional[str] = Field(None, description="英文推荐理由")
    reasoning_zh: Optional[str] = Field(None, description="中文推荐理由")
    evidence_level: Optional[str] = Field(None, description="证据强度")
    median_rating: Optional[float] = Field(None, description="中位数评分")
    rating_variance: Optional[float] = Field(None, description="评分方差")
    consensus_level: Optional[str] = Field(None, description="共识水平")
    adult_radiation_dose: Optional[str] = Field(None, description="成人辐射剂量")
    pediatric_radiation_dose: Optional[str] = Field(None, description="儿童辐射剂量")
    contraindications: Optional[str] = Field(None, description="禁忌症")
    special_considerations: Optional[str] = Field(None, description="特殊考虑")
    pregnancy_safety: Optional[str] = Field(None, description="妊娠安全性")
    is_generated: bool = Field(False, description="是否AI生成")
    confidence_score: float = Field(1.0, ge=0.0, le=1.0, description="置信度评分")
    last_reviewed_date: Optional[date] = Field(None, description="最后审查日期")
    reviewer_id: Optional[int] = Field(None, description="审查者ID")
    is_active: bool = Field(True, description="是否激活")

class ClinicalRecommendationCreate(ClinicalRecommendationBase):
    pass

class ClinicalRecommendationUpdate(BaseModel):
    scenario_id: Optional[str] = Field(None, description="临床场景ID")
    procedure_id: Optional[str] = Field(None, description="检查项目ID")
    appropriateness_rating: Optional[int] = Field(None, ge=1, le=9, description="适宜性评分")
    appropriateness_category: Optional[str] = Field(None, description="适宜性类别")
    appropriateness_category_zh: Optional[str] = Field(None, description="适宜性类别中文")
    reasoning_en: Optional[str] = Field(None, description="英文推荐理由")
    reasoning_zh: Optional[str] = Field(None, description="中文推荐理由")
    evidence_level: Optional[str] = Field(None, description="证据强度")
    median_rating: Optional[float] = Field(None, description="中位数评分")
    rating_variance: Optional[float] = Field(None, description="评分方差")
    consensus_level: Optional[str] = Field(None, description="共识水平")
    adult_radiation_dose: Optional[str] = Field(None, description="成人辐射剂量")
    pediatric_radiation_dose: Optional[str] = Field(None, description="儿童辐射剂量")
    contraindications: Optional[str] = Field(None, description="禁忌症")
    special_considerations: Optional[str] = Field(None, description="特殊考虑")
    pregnancy_safety: Optional[str] = Field(None, description="妊娠安全性")
    is_generated: Optional[bool] = Field(None, description="是否AI生成")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="置信度评分")
    last_reviewed_date: Optional[date] = Field(None, description="最后审查日期")
    reviewer_id: Optional[int] = Field(None, description="审查者ID")
    is_active: Optional[bool] = Field(None, description="是否激活")

class ClinicalRecommendationResponse(ClinicalRecommendationBase):
    id: int
    semantic_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== 嵌套响应模式 ====================

class ProcedureInRecommendation(BaseModel):
    semantic_id: str
    name_zh: str
    modality: Optional[str]
    body_part: Optional[str]
    radiation_level: Optional[str]
    
    class Config:
        from_attributes = True

class ScenarioInRecommendation(BaseModel):
    semantic_id: str
    description_zh: str
    patient_population: Optional[str]
    risk_level: Optional[str]
    age_group: Optional[str]
    
    class Config:
        from_attributes = True

class RecommendationWithDetails(ClinicalRecommendationResponse):
    scenario: ScenarioInRecommendation
    procedure: ProcedureInRecommendation

# ==================== 搜索和分页模式 ====================

class VectorSearchRequest(BaseModel):
    query_text: str = Field(..., description="搜索文本")
    table_name: str = Field(..., description="搜索表名")
    limit: int = Field(10, ge=1, le=100, description="返回结果数量")
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0, description="相似度阈值")
    filters: Optional[dict] = Field(None, description="过滤条件")

class VectorSearchResult(BaseModel):
    semantic_id: str
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    description_zh: Optional[str] = None
    appropriateness_rating: Optional[int] = None
    similarity_score: float = Field(..., description="相似度分数")
    table_name: str = Field(..., description="来源表")

class VectorSearchResponse(BaseModel):
    query_text: str
    table_name: str
    total_results: int
    search_time_ms: int
    results: List[VectorSearchResult]

class IntelligentRecommendationRequest(BaseModel):
    clinical_query: str = Field(..., description="临床查询")
    patient_profile: Optional[dict] = Field(None, description="患者特征")
    filters: Optional[dict] = Field(None, description="过滤条件")
    limit: int = Field(10, ge=1, le=50, description="返回结果数量")

class IntelligentRecommendationResponse(BaseModel):
    query: str
    total_found: int
    recommendations: List[RecommendationWithDetails]
    search_time_ms: int

class PaginatedResponse(BaseModel):
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页记录数")
    total_pages: int = Field(..., description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")

class PaginatedPanels(PaginatedResponse):
    items: List[PanelResponse] = []

class PaginatedTopics(PaginatedResponse):
    items: List[TopicResponse] = []

class PaginatedScenarios(PaginatedResponse):
    items: List[ClinicalScenarioResponse] = []

class PaginatedProcedures(PaginatedResponse):
    items: List[ProcedureDictionaryResponse] = []

class PaginatedRecommendations(PaginatedResponse):
    items: List[RecommendationWithDetails] = []

# ==================== 统计和分析模式 ====================

class DataStatistics(BaseModel):
    panels_count: int
    topics_count: int
    scenarios_count: int
    procedures_count: int
    recommendations_count: int
    active_panels: int
    active_topics: int
    active_scenarios: int
    active_procedures: int
    active_recommendations: int
    generated_recommendations: int
    embedding_coverage: dict
    last_updated: datetime

class HealthCheckResponse(BaseModel):
    status: str
    database_status: str
    vector_index_status: str
    total_records: int
    total_vectors: int
    last_build_time: Optional[datetime]
    version: str = "2.0.0"

# ==================== 批量操作模式 ====================

class BatchCreateRequest(BaseModel):
    panels: Optional[List[PanelCreate]] = Field(None, description="批量创建Panels")
    topics: Optional[List[TopicCreate]] = Field(None, description="批量创建Topics")
    scenarios: Optional[List[ClinicalScenarioCreate]] = Field(None, description="批量创建Scenarios")
    procedures: Optional[List[ProcedureDictionaryCreate]] = Field(None, description="批量创建Procedures")
    recommendations: Optional[List[ClinicalRecommendationCreate]] = Field(None, description="批量创建Recommendations")

class BatchCreateResponse(BaseModel):
    success_count: int
    error_count: int
    created_ids: List[str]
    errors: List[str]
    total_time_ms: int

# ==================== 数据导入导出模式 ====================

class DataImportRequest(BaseModel):
    csv_file_path: str = Field(..., description="CSV文件路径")
    clear_existing: bool = Field(True, description="是否清空现有数据")
    batch_size: int = Field(100, ge=10, le=1000, description="批处理大小")
    generate_vectors: bool = Field(True, description="是否生成向量嵌入")

class DataImportResponse(BaseModel):
    import_id: str
    status: str
    total_records: int
    processed_records: int
    created_entities: dict
    errors: List[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[float]

class DataExportRequest(BaseModel):
    table_names: List[str] = Field(..., description="要导出的表名")
    output_format: str = Field("excel", description="输出格式: excel, csv, json")
    include_vectors: bool = Field(False, description="是否包含向量数据")
    filters: Optional[dict] = Field(None, description="过滤条件")

class DataExportResponse(BaseModel):
    export_id: str
    file_path: str
    file_size_bytes: int
    records_exported: dict
    created_at: datetime