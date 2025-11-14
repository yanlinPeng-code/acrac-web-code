from enum import Enum
from typing import Optional, List, Union

from pydantic import BaseModel, Field




class PatientInfo(BaseModel):
    """患者基本信息"""
    age: Optional[int] = Field(None, description="患者年龄", ge=0, le=150)
    gender: Optional[str] = Field(None, description="患者性别：男/女")
    pregnancy_status: Optional[str] = Field(None, description="妊娠状态：妊娠期/哺乳期/非妊娠期")
    allergies: Optional[List[str]] = Field(None, description="过敏史列表")
    comorbidities: Optional[List[str]] = Field(None, description="合并症列表")
    physical_examination: Optional[str] = Field(None, description="检查报告")


class ClinicalContext(BaseModel):
    """临床上下文信息"""
    department: Optional[str]= Field(..., description="科室名称", min_length=2, max_length=50)
    chief_complaint: Optional[str] = Field(..., description="主诉", min_length=2, max_length=500)
    medical_history: Optional[str] = Field(None, description="既往病史", max_length=2000)
    present_illness: Optional[str] = Field(None, description="现病史", max_length=2000)
    diagnosis: Optional[str] = Field(None, description="医生主诊断结果", max_length=500)
    symptom_duration: Optional[str] = Field(None, description="症状持续时间")
    symptom_severity: Optional[str] = Field(None, description="症状严重程度：轻度/中度/重度")


class SearchStrategy(BaseModel):
    """检索策略配置"""
    vector_weight: Optional[float] = Field(0.4, description="向量检索权重", ge=0, le=1)
    keyword_weight: Optional[float] = Field(0.3, description="关键词检索权重", ge=0, le=1)
    diversity_weight: Optional[float] = Field(0.3, description="多样性权重", ge=0, le=1)


from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class RerankingStrategy(Enum):
    """重排序策略枚举"""
    NONE = "none"  # 无重排序
    RULE_ONLY = "rule_only"  # 仅规则重排序
    LLM_SCENARIO_ONLY = "llm_scenario_only"  # 仅LLM场景重排序
    LLM_RECOMMENDATION_ONLY = "llm_recommendation_only"  # 仅LLM推荐项目排序
    RULE_AND_LLM_SCENARIO = "rule_and_llm_scenario"  # 规则+LLM场景重排序
    RULE_AND_LLM_RECOMMENDATION = "rule_and_llm_recommendation"  # 规则+LLM推荐项目
    LLM_SCENARIO_AND_RECOMMENDATION = "llm_scenario_and_recommendation"  # LLM场景+推荐项目
    ALL = "all"  # 全部启用


class RetrievalRequest(BaseModel):
    enable_reranking: Optional[bool] = Field(True, description="是否启用llm重排序")
    need_llm_recommendations: Optional[bool] = Field(True, description="是否基于这些场景进行llm的推荐")
    apply_rule_filter: Optional[bool] = Field(True, description="是否应用规则过滤")
    top_scenarios: Optional[int] = Field(10, description="返回的场景数量", ge=1, le=50)
    top_recommendations_per_scenario: Optional[int] = Field(5, description="每个场景的推荐数量", ge=1, le=20)
    show_reasoning: Optional[bool] = Field(True, description="是否显示推荐理由")
    include_raw_data: Optional[bool] = Field(False, description="是否包含原始数据")
    similarity_threshold: Optional[float] = Field(0.6, description="相似度阈值", ge=0.1, le=0.9)
    min_appropriateness_rating: Optional[int] = Field(None, description="最低适宜性评分", ge=1, le=9)

    @property
    def reranking_strategy(self) -> RerankingStrategy:
        """根据三个布尔字段计算对应的重排序策略"""
        return self._map_to_strategy(
            self.apply_rule_filter or False,
            self.enable_reranking or False,
            self.need_llm_recommendations or False
        )

    def _map_to_strategy(self, apply_rule: bool, enable_rerank: bool, need_llm_rec: bool) -> RerankingStrategy:
        """映射三个布尔字段到策略枚举"""
        # 8种情况的完整映射
        if not apply_rule and not enable_rerank and not need_llm_rec:
            return RerankingStrategy.NONE
        elif apply_rule and not enable_rerank and not need_llm_rec:
            return RerankingStrategy.RULE_ONLY
        elif not apply_rule and enable_rerank and not need_llm_rec:
            return RerankingStrategy.LLM_SCENARIO_ONLY
        elif not apply_rule and enable_rerank and need_llm_rec:
            return RerankingStrategy.LLM_SCENARIO_AND_RECOMMENDATION
        elif apply_rule and enable_rerank and not need_llm_rec:
            return RerankingStrategy.RULE_AND_LLM_SCENARIO
        elif apply_rule and enable_rerank and need_llm_rec:
            return RerankingStrategy.ALL
        elif apply_rule and not enable_rerank and need_llm_rec:
            return RerankingStrategy.RULE_AND_LLM_RECOMMENDATION
        elif not apply_rule and not enable_rerank and need_llm_rec:
            return RerankingStrategy.LLM_RECOMMENDATION_ONLY
        else:
            return RerankingStrategy.RULE_ONLY


class IntelligentRecommendationRequest(BaseModel):
    """智能推荐请求模型"""
    patient_info: Optional[PatientInfo] = Field(..., description="患者基本信息")
    clinical_context: Optional[ClinicalContext] = Field(..., description="临床上下文信息")
    need_optimize_query:Optional[bool]=Field(...,description="是否要优化问题")
    search_strategy: Optional[SearchStrategy] = Field(None, description="检索权重配置")
    retrieval_strategy: Optional[RetrievalRequest] = Field(None, description="检索的策略配置")
    standard_query:Optional[str]=Field("",description="标准问题，该问题主要用于测试")

    @property
    def effective_retrieval_strategy(self) -> RetrievalRequest:
        """获取有效的检索策略（如果没有提供则使用默认）"""
        if self.retrieval_strategy is None:
            return RetrievalRequest()  # 使用默认值
        return self.retrieval_strategy

class IntelligentRecommendationResponse(BaseModel):
    """智能推荐响应模型"""
    query: Optional[str] = None
    best_recommendations: Union[Optional[list],Optional[str]] = Field(None, description="LLM选择的最佳推荐项目（Top3）")
    # contexts: Optional[List[str]] = Field(None, description="RAGAS评测用的上下文列表")
    processing_time_ms: Optional[int] = None# 处理时间（毫秒）
    model_used: Optional[str] = None
    reranker_model_used: Optional[str] = None
    similarity_threshold: Optional[float] = None
    # max_similarity: Optional[float] = None#最大相似度
    # is_low_similarity_mode: Optional[bool] = None#是否是低相似度模式
    # llm_raw_response: Optional[str] = None#模型的每行的回复
    # debug_info: Optional[Dict[str, Any]] = None
    # 为调试脚本（trace_five_cases.py）提供完整追踪信息
    # trace: Optional[Dict[str, Any]] = None


class BestRecommendation:
      pass


