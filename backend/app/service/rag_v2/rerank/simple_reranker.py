from app.service.rag_v2.prompt.simple_rerank_prompt import SimpleRerankPrompt
from app.service.rag_v2.rerank.base_reranker import BaseReranker
from app.utils.helper.helper import safe_parse_llm_response, safe_process_recommendation_grades
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)

class SimpleReranker(BaseReranker,SimpleRerankPrompt):

    def __init__(self):
        super().__init__()






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

        # 获取这些场景的推荐项目
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        # 可以过滤，也可以不过滤
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        # 使用自适应引擎进行LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            filter_scenario_with_recommendations,
            patient_info,
            clinical_context,
            max_scenarios,
            max_recommendations_per_scenario,
            direct_return
        )

        return recommendations

    async def _handle_rule_and_llm_recommendation_strategy(self,
                                                             all_scenarios,
                                                             patient_info,
                                                             clinical_context,
                                                             min_rating,
                                                             max_scenarios,
                                                             max_recommendations_per_scenario,
                                                             direct_return,):
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
            top_k=len(all_scenarios),
            enable_llm=False
        )

        # 第二步：LLM推荐项目重排序
        # 使用自适应引擎进行LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            rule_ranked_scenarios,
            patient_info,
            clinical_context,
            max_scenarios,
            max_recommendations_per_scenario,
            direct_return,
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

        # 第二步：LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            filter_scenario_with_recommendations,
            patient_info,
            clinical_context,
             max_scenarios,
            max_recommendations_per_scenario,
            direct_return,
        )

        return recommendations

    async def _handle_all_strategy(self,
                                   all_scenarios,
                                   patient_info,
                                   clinical_context,
                                   min_rating,
                                   max_scenarios,
                                   max_recommendations_per_scenario,
                                   direct_return,
                                   ):
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
            top_k=len(all_scenarios),
            enable_llm=False
        )



        # 第二步：LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            ranked_scenarios,
            patient_info,
            clinical_context,
            max_scenarios,
            max_recommendations_per_scenario,
            direct_return,
        )

        return recommendations
    async def get_recommendations_simple(self,
                                         filter_scenario_with_recommendations,
                                         patient_info,
                                         clinical_context,
                                         max_scenarios,
                                         max_recommendations_per_scenario,
                                         direct_return,
                                         ):
        # 开始让llm根据病症做推荐
        prompt = self.build_comprehensive_prompt_with_grading(filter_scenario_with_recommendations, patient_info,
                                                               clinical_context, direct_return, max_scenarios,
                                                               max_recommendations_per_scenario)
        try:
            # 单次LLM调用
            response = await self.ai_service._call_llm(prompt)
            if direct_return:
                return response
            # 解析JSON结果
            import re
            import json

            json_match = safe_parse_llm_response(response)
            if not json_match:
                logger.error("LLM返回格式错误，使用降级方案")
                return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations,
                                                                           max_scenarios, patient_info)

            try:
                result = json_match
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {e}")
                return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations,
                                                                           max_scenarios, patient_info)

            # 处理选中的场景和分级推荐
            selected_scenarios_data = result.get('selected_scenarios', [])
            final_results = []

            for selected_data in selected_scenarios_data:
                scenario_index = selected_data.get('scenario_index')
                scenario_id = selected_data.get('scenario_id')
                grading_data = selected_data.get('recommendation_grades', {})
                final_choices = selected_data.get("final_choices", [])
                # 验证场景索引
                if not (1 <= scenario_index <= len(filter_scenario_with_recommendations)):
                    logger.warning(f"无效的场景索引: {scenario_index}")
                    continue

                original_scenario_data = filter_scenario_with_recommendations[scenario_index - 1]
                original_recommendations = original_scenario_data.get('recommendations', [])
                scenario = original_scenario_data['scenario']

                graded_recommendations = safe_process_recommendation_grades(
                    grading_data, original_recommendations, scenario_index
                )
                # 构建返回结果
                final_result = {
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
                    "final_choices": final_choices,
                    'scenario_metadata': {
                        'scenario_id': scenario_id or scenario.semantic_id,
                        'description': scenario.description_zh,
                        'panel': scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知',
                        'patient_population': scenario.patient_population,
                        'clinical_context': scenario.clinical_context,
                        'original_index': scenario_index
                    }
                }

                final_results.append(final_result)

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
            if not direct_return:
                logger.error(f"❌ 综合场景分级筛选失败: {str(e)}", exc_info=True)
                return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations,
                                                                           max_scenarios, patient_info)
            return "出错了，请联系管理人员"