from app.service.rag_v2.prompt.detail_rerank_prompt import DetailRerankPrompt
from app.service.rag_v2.rerank.base_reranker import BaseReranker
from app.utils.logger.simple_logger import get_logger

from app.service.rag_v2.rerank.adaptive_reranker import AdaptiveReranker

logger=get_logger(__name__)
class DetailReranker(BaseReranker):


      def __init__(self,
                   adaptive_recommendation_engine_service:AdaptiveReranker
                   ):
          super().__init__()
          self.prompt_builder=DetailRerankPrompt()
          self.adaptive_recommendation_engine_service = adaptive_recommendation_engine_service




      async def _handle_llm_recommendation_only_strategy(self,
                                                         all_scenarios,
                                                         patient_info,
                                                         clinical_context,
                                                         min_rating,
                                                         max_scenarios,
                                                         max_recommendations_per_scenario,
                                                         direct_return):
          """策略4: 仅LLM推荐项目重排序"""
          logger.info(f"策略4-LLM_RECOMMENDATION_ONLY: 对前{max_scenarios}个场景进行LLM推荐项目重排序")

          # 先选择前max_scenarios个场景
          ranked_scenarios = all_scenarios[:max_scenarios * 3]
          # 获取这些场景的推荐项目
          scenario_with_recommendations = await self.get_scenarios_with_recommends(
              ranked_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
          )
          filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                  scenario_with_recommendations if
                                                  scenario_with_recommendation["recommendations"]]
          final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
              scenario_with_recommendations,
              filter_scenario_with_recommendations,
              max_scenarios
          )
          # 使用自适应引擎进行LLM推荐项目重排序
          recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
              confirmed_scenarios=final_scenario_with_recommendations,
              patient_info=patient_info,
              clinical_context=clinical_context,
              max_scenarios=max_scenarios,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return,
              use_adaptive=True
          )

          return recommendations


      async def _handle_rule_and_llm_recommendation_strategy(self,
                                                             all_scenarios,
                                                             patient_info,
                                                             clinical_context,
                                                             min_rating,
                                                             max_scenarios,
                                                             max_recommendations_per_scenario,
                                                             direct_return,
                                                             ):
          """策略6: 规则+LLM推荐项目重排序"""
          logger.info(f"策略6-RULE_AND_LLM_RECOMMENDATION: 规则重排序后LLM推荐项目重排序")

          # 第一步：规则重排序
          # 获取这些场景的推荐项目
          scenario_with_recommendations = await self.get_scenarios_with_recommends(
              all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
          )

          filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                  scenario_with_recommendations if
                                                  scenario_with_recommendation["recommendations"]]
          rule_ranked_scenarios = await self.hybrid_rank_scenarios(
              scenarios=filter_scenario_with_recommendations,
              patient_info=patient_info,
              clinical_context=clinical_context,
              top_k=max_scenarios,
              enable_llm=False
          )

          # 第二步：LLM推荐项目重排序
          recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
              confirmed_scenarios=rule_ranked_scenarios,
              patient_info=patient_info,
              clinical_context=clinical_context,
              max_recommendations_per_scenario=max_recommendations_per_scenario,
              direct_return=direct_return,
              use_adaptive=True
          )

          return recommendations

      async def _handle_llm_scenario_and_recommendation_strategy(self,
                                                                 all_scenarios,
                                                                 patient_info,
                                                                 clinical_context,
                                                                 min_rating,
                                                                 max_scenarios,
                                                                 max_recommendations_per_scenario,
                                                                 direct_return,
                                                                 ):
          """策略7: LLM场景+推荐项目重排序"""
          logger.info(f"策略7-LLM_SCENARIO_AND_RECOMMENDATION: LLM场景重排序+推荐项目重排序")
          # 先选择前max_scenarios个场景
          ranked_scenarios = all_scenarios
          # 获取所有场景的推荐项目
          scenario_with_recommendations = await self.get_scenarios_with_recommends(
              ranked_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
          )

          filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                  scenario_with_recommendations if
                                                  scenario_with_recommendation["recommendations"]]

          # 构建提示词并检查token数量
          prompt = self.prompt_builder.build_comprehensive_prompt_with_grading(
              filter_scenario_with_recommendations, patient_info, clinical_context,
              max_scenarios, max_recommendations_per_scenario
          )

          token_nums = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(prompt)
          threshold = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]

          if token_nums < threshold - 1500:
              logger.info(f"Token数量({token_nums})小于阈值({threshold})，使用单次LLM调用")
              # 单次LLM调用同时处理场景选择和推荐项目分级
              return await self._llm_recommend_scenarios(
                  filter_scenario_with_recommendations, prompt, patient_info,
                  max_scenarios, max_recommendations_per_scenario
              )
          else:
              logger.info(f"Token数量({token_nums})超过阈值({threshold})，分开处理场景选择和推荐项目")
              # 分开处理：先LLM场景重排序，再LLM推荐项目重排序
              # 第一步：LLM场景重排序
              llm_ranked_scenarios = await self.llm_rank_scenarios(
                  scenarios=filter_scenario_with_recommendations,
                  patient_info=patient_info,
                  clinical_context=clinical_context,
                  top_k=max_scenarios
              )

              # 筛选出对应的推荐数据
              scenarios_id_set = {scenario["scenario_id"] for scenario in llm_ranked_scenarios}
              filtered_scenarios_with_recommends = [
                  scenario_rec for scenario_rec in filter_scenario_with_recommendations
                  if scenario_rec["scenario_id"] in scenarios_id_set
              ]

              # 第二步：LLM推荐项目重排序
              recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
                  filtered_scenarios_with_recommends, patient_info, clinical_context,
                  max_recommendations_per_scenario, direct_return, use_adaptive=True
              )

              return recommendations


      async def _handle_all_strategy(self, all_scenarios, patient_info, clinical_context, min_rating, direct_return,
                                         max_scenarios, max_recommendations_per_scenario):
        """策略8: 全部启用 - 规则重排序 + LLM场景重排序 + LLM推荐项目重排序"""
        logger.info(f"策略8-ALL: 规则重排序 + LLM场景重排序 + LLM推荐项目重排序")

        # 第一步：规则重排序（宽松一些）
        # 第二步：使用策略7的逻辑处理LLM场景+推荐项目重排序
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        ranked_scenarios = await self.hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=True
        )
        # 如果是直接返回json数据
        # 第二步：LLM推荐项目重排序

        recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
            confirmed_scenarios=ranked_scenarios,
            patient_info=patient_info,
            clinical_context=clinical_context,

            max_recommendations_per_scenario=max_recommendations_per_scenario,
            direct_return=direct_return, use_adaptive=True
        )

        return recommendations
        # 如果是直接让llm返回推荐

      async def _llm_recommend_scenarios(self,
                                         all_scenarios,
                                         prompt,
                                         patient_info,
                                         max_scenarios,
                                         max_recommendations_per_scenarios):
          # scenario_with_recommendations = await self.get_screnarios_with_recommends(all_scenarios,max_scenarios,max_recommendations_per_scenario, min_rating)
          # 开始让llm根据病症做推荐
          # prompt=self._build_comprehensive_prompt_with_grading(scenario_with_recommendations, patient_info, clinical_context,max_scenarios,max_recommendations_per_scenario)
          try:
              # 单次LLM调用
              response = await self.ai_service._call_llm(prompt)

              # 解析JSON结果
              import re
              import json

              json_match = re.search(r'\{.*\}', response, re.DOTALL)
              if not json_match:
                  logger.error("LLM返回格式错误，使用降级方案")
                  return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

              try:
                  result = json.loads(json_match.group())
              except json.JSONDecodeError as e:
                  logger.error(f"JSON解析错误: {e}")
                  return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

              # 处理选中的场景和分级推荐
              selected_scenarios_data = result.get('selected_scenarios', [])
              final_results = []

              for selected_data in selected_scenarios_data:
                  scenario_index = selected_data.get('scenario_index')
                  scenario_id = selected_data.get('scenario_id')
                  grading_data = selected_data.get('recommendation_grades', {})

                  # 验证场景索引
                  if not (1 <= scenario_index <= len(all_scenarios)):
                      logger.warning(f"无效的场景索引: {scenario_index}")
                      continue

                  original_scenario_data = all_scenarios[scenario_index - 1]
                  original_recommendations = original_scenario_data.get('recommendations', [])
                  scenario = original_scenario_data['scenario']

                  # 按推荐等级组织推荐项目
                  graded_recommendations = {
                      "highly_recommended": [],
                      "recommended": [],
                      "less_recommended": []
                  }

                  # 处理各等级推荐项目
                  recommendation_levels = [
                      ('highly_recommended', '极其推荐'),
                      ('recommended', '推荐'),
                      ('less_recommended', '不太推荐')
                  ]

                  for level_key, level_zh in recommendation_levels:
                      for rec_idx in grading_data.get(level_key, []):
                          if 1 <= rec_idx <= len(original_recommendations):
                              rec_data = original_recommendations[rec_idx - 1].copy()
                              rec_data['recommendation_level'] = level_key
                              rec_data['recommendation_level_zh'] = level_zh

                              # 添加完整的检查项目信息
                              procedure = rec_data['procedure']
                              recommendation = rec_data['recommendation']

                              # 构建详细的检查项目信息
                              rec_data['procedure_details'] = {
                                  'semantic_id': procedure.semantic_id,
                                  'name_zh': procedure.name_zh,
                                  'name_en': procedure.name_en,
                                  'modality': procedure.modality,
                                  'body_part': procedure.body_part,
                                  'contrast_used': procedure.contrast_used,
                                  'radiation_level': procedure.radiation_level,
                                  'exam_duration': procedure.exam_duration,
                                  'preparation_required': procedure.preparation_required,
                                  'standard_code': procedure.standard_code,
                                  'description_zh': procedure.description_zh
                              }

                              # 构建详细的推荐信息
                              rec_data['recommendation_details'] = {
                                  'appropriateness_rating': recommendation.appropriateness_rating,
                                  'appropriateness_category_zh': recommendation.appropriateness_category_zh,
                                  'evidence_level': recommendation.evidence_level,
                                  'consensus_level': recommendation.consensus_level,
                                  'adult_radiation_dose': recommendation.adult_radiation_dose,
                                  'pediatric_radiation_dose': recommendation.pediatric_radiation_dose,
                                  'pregnancy_safety': recommendation.pregnancy_safety,
                                  'contraindications': recommendation.contraindications,
                                  'reasoning_zh': recommendation.reasoning_zh,
                                  'special_considerations': recommendation.special_considerations
                              }

                              graded_recommendations[level_key].append(rec_data)
                          else:
                              logger.warning(f"场景{scenario_index}的无效{level_zh}索引: {rec_idx}")

                  # 构建返回结果
                  final_results.append({
                      'comprehensive_score': selected_data.get('comprehensive_score', 0),
                      'scenario_reasoning': selected_data.get('scenario_reasoning', ''),
                      'grading_reasoning': selected_data.get('grading_reasoning', ''),
                      'overall_reasoning': result.get('overall_reasoning', ''),
                      'graded_recommendations': graded_recommendations,
                      'recommendation_summary': {
                          'highly_recommended_count': len(graded_recommendations['highly_recommended']),
                          'recommended_count': len(graded_recommendations['recommended']),
                          'less_recommended_count': len(graded_recommendations['less_recommended']),
                          'total_recommendations': len(original_recommendations)
                      },
                      'scenario_metadata': {
                          'scenario_id': scenario_id or scenario.semantic_id,
                          'description': scenario.description_zh,
                          'panel': scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知',
                          'patient_population': scenario.patient_population,
                          'clinical_context': scenario.clinical_context,
                          'original_index': scenario_index
                      }
                  })

              # 按综合评分排序
              final_results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

              # 记录详细的分级统计
              logger.info(f"✅ 单次LLM调用完成，选出{len(final_results)}个最佳场景")
              for idx, result in enumerate(final_results, 1):
                  summary = result['recommendation_summary']
                  metadata = result['scenario_metadata']
                  logger.info(
                      f"  场景#{idx}: {metadata['description'][:50]}... | "
                      f"评分={result['comprehensive_score']} | "
                      f"分级[极其:{summary['highly_recommended_count']}/"
                      f"推荐:{summary['recommended_count']}/"
                      f"不太:{summary['less_recommended_count']}]"
                  )

              return final_results

          except Exception as e:
              logger.error(f"❌ 综合场景分级筛选失败: {str(e)}", exc_info=True)
              return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

