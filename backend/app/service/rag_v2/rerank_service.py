from typing import List, Dict, Any

from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext, RerankingStrategy
from backend.app.service.rag_v2.rerank.detail_reranker import DetailReranker
from backend.app.service.rag_v2.rerank.simple_reranker import SimpleReranker

from backend.app.service.rag_v2.rerank.final_choice_reranker import FinalChoiceReranker
from backend.app.service.rag_v2.rerank.simple_final_choice_reranker import SimpleFinalChoiceReranker


class RerankService:



      def __init__(self,
                   detail_reranker:DetailReranker,
                   simple_reranker:SimpleReranker,
                   final_choice_reranker:FinalChoiceReranker,
                   simple_final_choice_reranker:SimpleFinalChoiceReranker
                   ):
          self.detail_reranker=detail_reranker
          self.simple_reranker=simple_reranker
          self.final_choice_reranker=final_choice_reranker
          self.simple_final_choice_reranker=simple_final_choice_reranker



      async def llm_rank_all_scenarios(
              self,
              all_scenarios: List[Dict[str, Any]],
              patient_info: PatientInfo,
              clinical_context: ClinicalContext,
              strategy: RerankingStrategy,
              min_rating: int = 5,
              direct_return: bool = False,
              max_scenarios: int = 3,
              max_recommendations_per_scenario: int = 3
      ) -> List[Dict[str, Any]]:
          response=await self.detail_reranker.execute_rerank(
              strategy=strategy,
              all_scenarios=all_scenarios,
              patient_info=patient_info,
              clinical_context=clinical_context,
              min_rating=min_rating,
              max_scenarios=max_scenarios,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return

          )
          return response

      async def simple_rank_all_scenarios(self,
                                          all_scenarios: List[Dict[str, Any]],
                                          patient_info: PatientInfo,
                                          clinical_context: ClinicalContext,
                                          strategy: RerankingStrategy,
                                          min_rating: int = 5,
                                          direct_return: bool = False,
                                          max_scenarios: int = 3,
                                          max_recommendations_per_scenario: int = 3
                                          ):
          response = await self.simple_reranker.execute_rerank(
              strategy=strategy,
              all_scenarios=all_scenarios,
              patient_info=patient_info,
              clinical_context=clinical_context,
              min_rating=min_rating,
              max_scenarios=max_scenarios,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return

          )
          return response

      async def llm_rerank_final_choices(self,
                                         all_scenarios: List[Dict[str, Any]],
                                         patient_info: PatientInfo,
                                         clinical_context: ClinicalContext,
                                         strategy: RerankingStrategy,
                                         min_rating: int = 5,
                                         max_scenarios: int = 3,
                                         max_recommendations_per_scenario: int = 3,
                                         direct_return: bool = False,

                                         ):
          return await self.final_choice_reranker.execute_rerank(
              all_scenarios=all_scenarios,
              patient_info=patient_info,
              clinical_context=clinical_context,
              strategy=strategy,
              min_rating=min_rating,
              max_scenarios=max_scenarios,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return



          )
      async def simple_llm_rank_final_choices(self,
                                              all_scenarios: List[Dict[str, Any]],
                                              patient_info: PatientInfo,
                                              clinical_context: ClinicalContext,
                                              strategy: RerankingStrategy,
                                              min_rating: int = 5,
                                              direct_return: bool = False,
                                              max_scenarios: int = 3,
                                              max_recommendations_per_scenario: int = 3

                                              ):
          return await self.simple_final_choice_reranker.execute_rerank(

              all_scenarios=all_scenarios,
              patient_info=patient_info,
              clinical_context=clinical_context,
              strategy=strategy,
              min_rating=min_rating,
              max_scenarios=max_scenarios,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return

          )




