from typing import Optional

import pydantic
from fastapi import UploadFile
from pydantic import BaseModel, Field


class EvalRequest(BaseModel):
      file:Optional[UploadFile]|None=None
      top_scenarios: int = Field(default=3,description="要获取的scenarios个数"),
      top_recommendations_per_scenario: int = Field(default=3,description="每个scenarios的推荐个数"),
      similarity_threshold: float = Field(default=0.7,description="最大相似度阈值"),
      min_appropriateness_rating: int = Field(default=0.5,description="最大可信度阈值"),

class EvalParams(BaseModel):
    enable_reranking: Optional[bool] = Field(True, description="是否启用llm重排序")
    need_llm_recommendations: Optional[bool] = Field(True, description="是否基于这些场景进行llm的推荐")
    apply_rule_filter: Optional[bool] = Field(True, description="是否应用规则过滤")
    top_scenarios: Optional[int] = Field(3, description="返回的场景数量", ge=1, le=4)
    top_recommendations_per_scenario: Optional[int] = Field(3, description="每个场景的推荐数量", ge=1, le=3)
    similarity_threshold: Optional[float] = Field(0.6, description="相似度阈值", ge=0.1, le=0.9)
    min_appropriateness_rating: Optional[int] = Field(None, description="最低适宜性评分", ge=1, le=9)
    show_reasoning:Optional[bool]=Field(False,description="是否包含原因"),
    include_raw_data:Optional[bool]=Field(False,description="是否包含原始行"),
    debug_mode:Optional[bool]=Field(False,description="是否是debug模式"),
    compute_ragas:Optional[bool]=Field(False,description="是否开启ragas"),
    ground_truth:Optional[str]=Field("",description="真相"),