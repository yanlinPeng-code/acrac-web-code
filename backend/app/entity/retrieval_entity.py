from enum import Enum

class RerankingStrategy(Enum):
    """重排序策略枚举"""
    NONE = "none"                    # 无重排序
    RULE_ONLY = "rule_only"          # 仅规则重排序
    LLM_SCENARIO_ONLY = "llm_scenario_only"      # 仅LLM场景重排序
    LLM_RECOMMENDATION_ONLY = "llm_recommendation_only"  # 仅LLM推荐项目排序
    RULE_AND_LLM_SCENARIO = "rule_and_llm_scenario"      # 规则+LLM场景重排序
    RULE_AND_LLM_RECOMMENDATION = "rule_and_llm_recommendation"  # 规则+LLM推荐项目
    LLM_SCENARIO_AND_RECOMMENDATION = "llm_scenario_and_recommendation"  # LLM场景+推荐项目
    ALL = "all"                      # 全部启用