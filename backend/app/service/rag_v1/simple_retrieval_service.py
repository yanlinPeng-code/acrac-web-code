import asyncio
import copy
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_
from app.config.database import async_db_manager
from app.config.redis_config import redis_manager
from app.entity.retrieval_entity import RerankingStrategy
from app.model import ClinicalRecommendation, ProcedureDictionary, ClinicalScenario
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v1.adaptive_recommend_service import AdaptiveRecommendationEngineService
from app.service.rag_v1.ai_service import AiService
from app.service.rag_v1.vector_database_service import VectorDatabaseService
from app.utils.helper.helper import assemble_database_results, safe_parse_llm_response, \
    safe_process_recommendation_grades
from app.utils.logger.simple_logger import get_logger
import qwen_token_counter
logger=get_logger(__name__)

class SimpleRetrievalService:
    def __init__(self,
                 session: AsyncSession,
                 ai_service: AiService,
                 vector_service: VectorDatabaseService,
                 ):
        """
        初始化检索服务

        Args:
            session: 数据库会话（主要用于非并发场景）
        """
        self.session = session

        # 初始化AI服务（使用requests调用API）
        self.ai_service = ai_service
        self.vector_service = vector_service
        self.redis_client = redis_manager.async_client
        self.adaptive_recommendation_engine_service = AdaptiveRecommendationEngineService(environment="production")

        # 性别映射
        self.gender_mapping = {
            '男性': [
                '男', '男性', '男人', '男士', '男患者', '男童', '男孩', '男生', '男婴', '男青年',
                '男子', '男病人', '男科', '雄性', '公', '雄', 'male', 'm', 'man', 'boy', 'gentleman'
            ],
            '女性': [
                '女', '女性', '女人', '女士', '女患者', '女童', '女孩', '女生', '女婴', '女青年',
                '女子', '女病人', '妇科', '雌性', '母', '雌', 'female', 'f', 'woman', 'girl', 'lady'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', '男女', '男女均可', '男女皆可',
                'any', 'all', 'both', 'either', '通用', 'common', 'general', "成人", "成年人"
            ]
        }

        # 妊娠状态映射
        self.pregnancy_mapping = {
            '妊娠期': [
                '妊娠', '怀孕', '孕妇', '孕期', '妊娠期', '孕产妇', '孕产期', '孕周', '孕早期',
                '孕中期', '孕晚期', '早孕', '中孕', '晚孕', '怀孕期', 'pregnancy', 'pregnant',
                'gestation', 'gestational', 'prenatal', 'antenatal'
            ],
            '非妊娠期': [
                '非妊娠', '非孕妇', '未怀孕', '未妊娠', '非孕期', '未孕', '非孕', 'non-pregnancy',
                'not pregnant', 'non-pregnant', 'non-gestational'
            ],
            '哺乳期': [
                '哺乳', '哺乳期', '母乳喂养', '母乳', '哺乳期妇女', '哺乳母亲', 'lactation',
                'breastfeeding', 'nursing', 'lactating'
            ],
            '备孕期': [
                '备孕', '备孕期', '计划怀孕', '准备怀孕', 'preconception', 'trying to conceive',
                'fertility', 'pre-pregnancy'
            ],
            '产后': [
                '产后', '分娩后', '生产后', 'postpartum', 'postnatal', 'after delivery',
                'puerperium', 'post-partum'
            ],
            '不孕': [
                '不孕', '不孕症', '不育', '不育症', 'infertility', 'infertile', 'sterility'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', 'any', 'all', 'both', 'either',
                '通用', 'common', 'general'
            ]
        }

        # 年龄组映射
        self.age_group_mapping = {
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'pediatric', 'children'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager'],
            '成人': ['成人', '成年人', 'adult'],
            '老年': ['老年', '老年人', '老人', 'elderly', 'geriatric', 'senior'],
            '不限': ['不限', '通用', 'all', 'both', 'any', '均可']
        }

        # 科室别名映射
        self.department_mapping = {
            '心内科': ['心血管内科', '心脏内科', ' Cardiology', 'cardiology'],
            '消化科': ['消化内科', ' Gastroenterology', 'gastroenterology'],
            '神经科': ['神经内科', ' Neurology', 'neurology'],
            '骨科': ['骨科', ' Orthopedics', 'orthopedics'],
            '儿科': ['小儿科', ' Pediatrics', 'pediatrics'],
            '妇产科': ['妇科', '产科', ' Obstetrics', 'Gynecology', 'obstetrics', 'gynecology'],
            '急诊科': ['急诊', ' Emergency', 'emergency'],
            '肿瘤科': ['肿瘤内科', ' Oncology', 'oncology']
        }

        # 紧急程度映射
        self.urgency_mapping = {
            '紧急': ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute'],
            '中度': ['中度', '中等', 'moderate', 'serious'],
            '常规': ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine'],
            '复发性': ['复发性', '复发', '反复', 'recurrent', 'relapse'],
            '亚急性': ['亚急性', 'subacute'],
            '重度': ['重度', '严重', 'severe'],
            '轻微': ['轻微', '轻度', 'mild', 'minor'],
            '稳定': ['稳定', 'stable'],
            '不稳定': ['不稳定', 'unstable'],
            '危及生命': ['危及生命', '生命危险', 'life-threatening', 'critical condition'],
            '择期': ['择期', 'elective'],
            '预防性': ['预防性', '预防', 'preventive', 'prophylactic'],
            '筛查': ['筛查', 'screening'],
            '随访': ['随访', 'follow-up'],
            '康复': ['康复', '康复期', 'rehabilitation', 'recovery'],
            '终末期': ['终末期', '晚期', '末期', 'end-stage', 'terminal'],
            '姑息治疗': ['姑息治疗', '姑息', 'palliative'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

    async def _get_independent_session(self) -> AsyncSession:
        """
        为并发检索创建独立的session

        高并发优化：每个检索方法使用独立的session，避免事务冲突
        从连接池中获取连接，自动管理生命周期
        """
        return async_db_manager.async_session_factory()

    async def simple_rank_all_scenarios(self, all_scenarios, patient_info, clinical_context, strategy, min_rating,
                                        max_scenarios, max_recommendations_per_scenario):

        """
               根据策略枚举执行不同的场景和推荐项目处理逻辑
               """
        if not all_scenarios:
            logger.warning("输入场景为空")
            return []

        try:
            # 根据策略执行不同的处理逻辑
            if strategy.value == RerankingStrategy.NONE.value:
                return await self._simple_handle_none_strategy(all_scenarios, max_scenarios)
            elif strategy.value == RerankingStrategy.RULE_ONLY.value:
                return await self._simple_handle_rule_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.LLM_SCENARIO_ONLY.value:
                return await self._simple_handle_llm_scenario_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.LLM_RECOMMENDATION_ONLY.value:
                return await self._simple_handle_llm_recommendation_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.RULE_AND_LLM_SCENARIO.value:
                return await self._simple_handle_rule_and_llm_scenario_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.RULE_AND_LLM_RECOMMENDATION.value:
                return await self._simple_handle_rule_and_llm_recommendation_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.LLM_SCENARIO_AND_RECOMMENDATION.value:
                return await self._simple_handle_llm_scenario_and_recommendation_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy.value == RerankingStrategy.ALL.value:
                return await self._simple_handle_all_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            else:
                logger.warning(f"未知策略: {strategy}，使用默认处理")
                return all_scenarios[:max_scenarios]

        except Exception as e:
            logger.error(f"处理策略 {strategy} 时发生错误: {e}")
            return []

    async def _simple_handle_none_strategy(self, all_scenarios, max_scenarios):
        """策略1: 无重排序，直接返回"""
        logger.info(f"策略1-NONE: 直接返回前{max_scenarios}个场景")
        return all_scenarios[:max_scenarios]




    async def _simple_handle_all_strategy(self, all_scenarios, patient_info, clinical_context, min_rating,
                                          max_scenarios, max_recommendations_per_scenario):
        """策略8: 全部启用 - 规则重排序 + LLM场景重排序 + LLM推荐项目重排序"""
        logger.info(f"策略8-ALL: 规则重排序 + LLM场景重排序 + LLM推荐项目重排序")

        # 第一步：规则重排序（宽松一些）
        # 第二步：使用策略7的逻辑处理LLM场景+推荐项目重排序
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        ranked_scenarios = await self.simple_hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=len(all_scenarios),
            enable_llm=False
        )

        # 构建提示词并检查token数量
        # prompt = self._build_comprehensive_prompt_with_grading(
        #     final_scenario_with_recommendations, patient_info, clinical_context,
        #     max_scenarios, max_recommendations_per_scenario
        # )
        #
        # token_nums = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(prompt)
        # threshold = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]

        # if token_nums < threshold:
        #     logger.info(f"Token数量({token_nums})小于阈值({threshold})，使用单次LLM调用")
        #     # 单次LLM调用同时处理场景选择和推荐项目分级
        #     return await self._llm_recommend_scenarios(
        #         final_scenario_with_recommendations, prompt, patient_info,
        #         max_scenarios, max_recommendations_per_scenario
        #     )
        # else:
        # logger.info(f"Token数量({token_nums})超过阈值({threshold})，分开处理场景选择和推荐项目")
        # 分开处理：先LLM场景重排序，再LLM推荐项目重排序
        # 第一步：LLM场景重排序
        # llm_ranked_scenarios = await self.llm_rank_scenarios(
        #     filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios
        # )
        #
        # # 筛选出对应的推荐数据
        # scenarios_id_set = {scenario["scenario_id"] for scenario in llm_ranked_scenarios}
        # filtered_scenarios_with_recommends = [
        #     scenario_rec for scenario_rec in filter_scenario_with_recommendations
        #     if scenario_rec["scenario_id"] in scenarios_id_set
        # ]

        # 第二步：LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            ranked_scenarios, patient_info, clinical_context, max_scenarios,
            max_recommendations_per_scenario
        )

        return recommendations



    async def _simple_handle_llm_scenario_and_recommendation_strategy(self, all_scenarios, patient_info,
                                                                      clinical_context, min_rating, max_scenarios,
                                                                      max_recommendations_per_scenario):

        """策略7: LLM场景+推荐项目重排序"""
        logger.info(f"策略7-LLM_SCENARIO_AND_RECOMMENDATION: LLM场景重排序+推荐项目重排序")
        # 先选择前max_scenarios个场景
        ranked_scenarios = all_scenarios
        # 获取所有场景的推荐项目
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            ranked_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]

        # 第二步：LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios,
            max_recommendations_per_scenario
        )

        return recommendations

    async def _simple_handle_rule_and_llm_recommendation_strategy(self, all_scenarios, patient_info, clinical_context,
                                                                  min_rating, max_scenarios,
                                                                  max_recommendations_per_scenario):
        """策略6: 规则+LLM推荐项目重排序"""
        logger.info(f"策略6-RULE_AND_LLM_RECOMMENDATION: 规则重排序后LLM推荐项目重排序")

        # 第一步：规则重排序
        # 获取这些场景的推荐项目
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        rule_ranked_scenarios = await self.simple_hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=len(all_scenarios),
            enable_llm=False
        )

        # 第二步：LLM推荐项目重排序
        # 使用自适应引擎进行LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            rule_ranked_scenarios , patient_info, clinical_context, max_scenarios,
            max_recommendations_per_scenario
        )

        return recommendations


    async def _simple_handle_rule_and_llm_scenario_strategy(self, all_scenarios, patient_info, clinical_context,
                                                            min_rating, max_scenarios,
                                                            max_recommendations_per_scenario):

        """策略5: 规则+LLM场景重排序"""
        logger.info(f"策略5-RULE_AND_LLM_SCENARIO: 规则重排序后LLM重排序{max_scenarios}个场景")

        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]


        ranked_scenarios = await self.simple_hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=True
        )

        # 第二步：LLM场景重排序
        # llm_ranked_scenarios = await self.llm_rank_scenarios(
        #     rule_ranked_scenarios, patient_info, clinical_context, max_scenarios
        # )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results(ranked_scenarios, patient_info, clinical_context,
                                         max_scenarios, max_recommendations_per_scenario)



    async def _simple_handle_llm_recommendation_only_strategy(self, all_scenarios, patient_info, clinical_context,
                                                              min_rating, max_scenarios,
                                                              max_recommendations_per_scenario):
        """策略4: 仅LLM推荐项目重排序"""
        logger.info(f"策略4-LLM_RECOMMENDATION_ONLY: 对前{max_scenarios}个场景进行LLM推荐项目重排序")

        # 先选择前max_scenarios个场景

        # 获取这些场景的推荐项目
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        #可以过滤，也可以不过滤
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        # 使用自适应引擎进行LLM推荐项目重排序
        recommendations = await self.get_recommendations_simple(
            filter_scenario_with_recommendations, patient_info, clinical_context,max_scenarios,
            max_recommendations_per_scenario
        )

        return recommendations

    async def _simple_handle_llm_scenario_only_strategy(self, all_scenarios, patient_info, clinical_context, min_rating,
                                                        max_scenarios, max_recommendations_per_scenario):
        """策略3: 仅LLM场景重排序"""
        logger.info(f"策略3-LLM_SCENARIO_ONLY: LLM重排序{max_scenarios}个场景")

        # LLM场景重排序
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        llm_ranked_scenarios = await self.llm_rank_scenarios(
            filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios
        )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results(llm_ranked_scenarios, patient_info, clinical_context, max_scenarios,
                                         max_recommendations_per_scenario)

    async def _simple_handle_rule_only_strategy(self, all_scenarios, patient_info, clinical_context, min_rating,
                                                max_scenarios, max_recommendations_per_scenario):
        """策略2: 仅规则重排序"""
        logger.info(f"策略2-RULE_ONLY: 规则重排序{max_scenarios}个场景")

        # 应用规则重排序
        scenario_with_recommendations = await self.simple_get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        rule_ranked_scenarios = await self.simple_hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=False
        )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results(rule_ranked_scenarios, patient_info, clinical_context, max_scenarios,
                                         max_recommendations_per_scenario)

    async def simple_get_scenarios_with_recommends(
            self,
            all_scenarios: List[Dict[str, Any]],
            max_scenarios: int,
            max_recommendations_per_scenario: int,
            min_rating: int = None
    ):
        semaphore = asyncio.Semaphore(8)
        # 设置单个任务的超时时间（例如30秒）
        timeout_duration = 30

        async def get_recommendations_with_semaphore(scenario_data):
            async with semaphore:
                try:
                    scenario = scenario_data['scenario']
                    buffer_multiplier = 2
                    candidate_cap = max(
                        max_recommendations_per_scenario * (max_scenarios + buffer_multiplier),
                        max_recommendations_per_scenario * 2
                    )
                    top_k = min(candidate_cap, 50)

                    # 使用超时包装
                    try:
                        recommendations = await asyncio.wait_for(
                            self.get_scenario_recommendations(
                                scenario_id=scenario.semantic_id,
                                top_k=top_k,
                                min_rating=min_rating or 5
                            ),
                            timeout=timeout_duration
                        )
                        return scenario_data, recommendations
                    except asyncio.TimeoutError:
                        logger.error(f"获取场景 {scenario.semantic_id} 推荐超时，超过 {timeout_duration} 秒")
                        return scenario_data, []

                except Exception as e:
                    logger.error(
                        f"获取场景 {scenario_data.get('scenario', {}).get('semantic_id', 'unknown')} 推荐时发生异常: {e}")
                    return scenario_data, []

        # 创建所有任务
        tasks = [get_recommendations_with_semaphore(scenario_data) for scenario_data in all_scenarios]

        # 并发执行，捕获所有异常
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果，分离正常结果和异常
        scenarios_with_recommendations = []
        successful_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                # 处理异常情况
                failed_count += 1
                logger.error(f"任务执行失败: {result}")
                continue

            scenario_data, recommendations = result
            scenario = scenario_data['scenario']

            scenarios_with_recommendations.append({
                'scenario': scenario,
                'scenario_id': scenario.id,
                'semantic_id': scenario.semantic_id,
                'scenario_description': scenario.description_zh,
                'patient_population': scenario.patient_population,
                'clinical_context': scenario.clinical_context,

                'final_score': scenario_data.get('final_score', 0),
                'semantic_score': scenario_data.get('semantic_score', 0),
                'keyword_score': scenario_data.get('jieba_score', 0),
                'rule_score': scenario_data.get('rule_score', 0),
                'llm_rank': scenario_data.get('llm_rank', None),
                'selection_source': scenario_data.get('selection_source_by_llm', 'Unknown') or scenario_data.get(
                    'selection_source_by_rule', 'Unknown'),

                'llm_reasoning': scenario_data.get('llm_reasoning', ''),
                'recommendations': recommendations,
                'recommendation_count': len(recommendations)
            })
            successful_count += 1

        total_recommendations = sum(len(s['recommendations']) for s in scenarios_with_recommendations)
        logger.info(
            f"📊 共获取 {total_recommendations} 条推荐项目（来自{successful_count}个成功场景，{failed_count}个失败场景）")

        return scenarios_with_recommendations

    async def get_scenario_recommendations(
            self,
            scenario_id: str,
            top_k: int = 10,
            min_rating: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取指定临床场景的推荐项目

        Args:
            scenario_id: 临床场景ID
            top_k: 返回的推荐数量
            min_rating: 最低适宜性评分

        Returns:
            推荐项目列表，按appropriateness_rating降序排序
        """
        session = await self._get_independent_session()
        try:
            # 构建查询
            statement = (
                select(ClinicalRecommendation, ProcedureDictionary)
                .join(ProcedureDictionary, ClinicalRecommendation.procedure_id == ProcedureDictionary.semantic_id)
                .where(
                    and_(
                        ClinicalRecommendation.scenario_id == scenario_id,
                        ClinicalRecommendation.is_active == True,
                        ProcedureDictionary.is_active == True
                    )
                )
            )

            if min_rating is not None:
                statement = statement.where(ClinicalRecommendation.appropriateness_rating >= min_rating)

            statement = statement.order_by(ClinicalRecommendation.appropriateness_rating.desc())
            statement = statement.limit(top_k)

            result = await session.exec(statement)
            rows = result.all()

            recommendations_list = []
            for recommendation, procedure in rows:
                recommendations_list.append({
                    "recommendation": recommendation,
                    "procedure": procedure
                })

            return recommendations_list

        except Exception as e:
            logger.error(f"获取场景 {scenario_id} 推荐项目失败: {e}")
            # 可以选择返回空列表或重新抛出异常
            return []
        finally:
            await session.close()

    async def simple_hybrid_rank_scenarios(self, scenarios, patient_info, clinical_context, top_k, enable_llm):
        llm_results = None
        rule_results = None

        llm_top_k = (top_k + 1) // 2  # 向上取整
        rule_top_k = top_k // 2  # 向下取整
        if not scenarios:
            logger.warning("输入场景为空")
            return []
        if len(scenarios) < top_k:
            top_k = len(scenarios)
        # 深拷贝scenarios，防止并行处理时产生数据冲突
        # 注意：scenario对象本身不拷贝（数据库对象），只拷贝外层字典结构
        scenarios_for_llm = copy.deepcopy(scenarios)
        scenarios_for_rule = copy.deepcopy(scenarios)

        # 并行执行LLM和规则排序
        if enable_llm:
            logger.info("🚀 开始并行执行LLM排序和规则排序...")
            llm_task = self.llm_rank_scenarios(
                scenarios_for_llm, patient_info, clinical_context, llm_top_k
            )
            rule_task = self.rule_rank_scenarios(
                scenarios_for_rule, patient_info, clinical_context, rule_top_k
            )

            llm_results, rule_results = await asyncio.gather(
                llm_task, rule_task, return_exceptions=True
            )

            # 异常处理
            if isinstance(llm_results, Exception):
                logger.warning(f"⚠️ LLM排序失败，使用规则排序: {llm_results}")
                llm_results = []
            if isinstance(rule_results, Exception):
                logger.error(f"❌ 规则排序失败: {rule_results}")
                rule_results = []

        logger.info("🔧 仅使用规则排序")
        rule_results = await self.rule_rank_scenarios(
            scenarios, patient_info, clinical_context, top_k
        )

        # 去重合并逻辑
        final_scenarios = []
        seen_ids = set()

        # # 1. 优先选择LLM结果
        if llm_results:
            for item in llm_results:
                scenario_id = item['scenario'].id
                if scenario_id not in seen_ids:
                    final_scenarios.append(item)
                    seen_ids.add(scenario_id)
            logger.info(f"✅ LLM贡献 {len(llm_results)} 个场景")

        # 2. 补充规则排序结果（去重）
        if rule_results:
            for item in rule_results:
                scenario_id = item['scenario'].id
                if scenario_id not in seen_ids and len(final_scenarios) < top_k:
                    final_scenarios.append(item)
                    seen_ids.add(scenario_id)
            llm_nums = len(llm_results) if llm_results else 0
            logger.info(f"🔧 规则补充 {len(final_scenarios) - llm_nums} 个场景")

        # 统计信息
        llm_count = len([s for s in final_scenarios if s.get('selection_source_by_llm') == 'LLM'])
        rule_count = len([s for s in final_scenarios if s.get('selection_source_by_rule') == 'Rule'])

        logger.info(
            f"🎯 混合排序完成: 总数{len(final_scenarios)}, LLM({llm_count}), 规则({rule_count})"
        )

        return final_scenarios[:top_k]

    async def llm_rank_scenarios(
            self,
            scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        使用LLM根据患者信息智能选择最匹配的临床场景

        Args:
            scenarios: 候选场景列表（来自混合检索）
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            top_k: 返回的场景数量

        Returns:
            LLM选择的场景列表，包含llm_reasoning和llm_rank字段
        """
        if not scenarios:
            logger.warning("输入场景为空，LLM选择跳过")
            return []

        try:
            # 1. 构建场景列表文本

            # 2. 构建患者信息文本
            patient_text = f"""患者信息:
                            - 年龄: {patient_info.age}岁
                            - 性别: {patient_info.gender}
                            - 妊娠状态: {patient_info.pregnancy_status or '非妊娠期'}
                            - 过敏史: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
                            - 合并症: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
                            - 检查报告: {patient_info.physical_examination or '无'}
                            临床信息:
                            - 科室: {clinical_context.department}
                            - 主诉: {clinical_context.chief_complaint}
                            - 既往病史: {clinical_context.medical_history or '无'}
                            - 现病史: {clinical_context.present_illness or '无'}
                            - 主诊断结果: {clinical_context.diagnosis or '待诊断'}
                            - 症状严重程度: {clinical_context.symptom_severity or '未知'}
                            - 症状持续时间: {clinical_context.symptom_duration or '未知'}
                           """
            patient_token = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(patient_text)
            available_tokens = self.adaptive_recommendation_engine_service.strategy.threshold_config[
                                   "token_threshold"] - 400 - patient_token - 300
            scenario_texts = []
            total_scenarios_token = 0
            included_scenarios = 0

            for idx, item in enumerate(scenarios, 1):
                scenario = item['scenario']
                scenario_text = f"""场景{idx}:
                                    - ID: {scenario.id}
                                    - 科室: {scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'}
                                    - 主题: {scenario.topic.name_zh if hasattr(scenario, 'topic') and scenario.topic else '未知'}
                                    - 描述: {scenario.description_zh}
                                    - 适用人群: {scenario.patient_population or '不限'}
                                    - 年龄组: {scenario.age_group or '不限'}
                                    - 性别: {scenario.gender or '不限'}
                                    - 妊娠状态: {scenario.pregnancy_status or '不限'}
                                    - 紧急程度: {scenario.urgency_level or '不限'}
                                    - 症状分类: {scenario.symptom_category or '未知'}
                                    """

                scenario_token = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(
                    scenario_text)

                # 检查是否还有足够的token空间
                if total_scenarios_token + scenario_token <= available_tokens:
                    scenario_texts.append(scenario_text)
                    total_scenarios_token += scenario_token
                    included_scenarios += 1
                else:
                    logger.warning(
                        f"Token限制，只包含前{included_scenarios}个场景，跳过后{len(scenarios) - included_scenarios}个场景")
                    break

            # 5. 如果token仍然超限，尝试简化场景描述
            if total_scenarios_token > available_tokens and scenario_texts:
                # 简化最后一个场景的描述
                last_scenario = scenarios[included_scenarios - 1]
                scenario = last_scenario['scenario']
                simplified_text = f"""场景{included_scenarios}:
                                    - ID: {scenario.id}
                                    - 科室: {scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'}
                                    - 主题: {scenario.topic.name_zh if hasattr(scenario, 'topic') and scenario.topic else '未知'}
                                    - 描述: {scenario.description_zh[:100]}...  # 截断描述
                                    """
                simplified_token = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(
                    simplified_text)

                if total_scenarios_token - scenario_token + simplified_token <= available_tokens:
                    scenario_texts[-1] = simplified_text
                    total_scenarios_token = total_scenarios_token - scenario_token + simplified_token
                else:
                    # 如果简化后仍然超限，移除最后一个场景
                    scenario_texts.pop()
                    included_scenarios -= 1
                    logger.warning(f"移除最后一个场景以符合token限制，最终包含{included_scenarios}个场景")

            # 3. 构建Prompt
            prompt = f"""你是一位经验丰富的临床医生，需要根据患者情况从以下临床场景中选择最匹配的{top_k}个场景。

                        {patient_text}

                        可选临床场景:
                        {''.join(scenario_texts)}

                        请综合考虑以下因素进行选择：
                        1. 患者年龄、性别、妊娠状态是否符合场景要求
                        2. 主诉与场景描述的匹配度（语义相关性）
                        3. 科室是否对应
                        4. 症状严重程度与场景的紧急程度匹配
                        5. 是否存在禁忌症（如孕妇避免辐射检查相关场景）

                        请直接输出选择的场景ID列表（数字ID，不是语义ID），格式为JSON，这是一个例子：
                        {{"selected_scenario_ids": [1, 5, 8], "reasoning": "这里填写你选择的原因"}}

                        要求：
                        - 输出必须是完整的、可解析的JSON格式
                        - 根据实际用户情况和临床场景严谨的选择{top_k}个场景（为了专业性，可以选择的比top_k小，但不能为0个）
                        - 按匹配度从高到低排序
                        - 不要输出其他解释文字，只输出JSON格式结果
                        """

            # 4. 调用LLM（使用ai_service）
            response = await self.ai_service._call_llm(prompt)

            try:
                # ... 构建prompt和调用LLM的代码保持不变 ...

                # 5. 解析LLM返回的JSON - 增强健壮性
                import re
                import json

                def robust_json_parse(response: str) -> Dict[str, Any]:
                    """增强的JSON解析，处理不完整的JSON响应"""
                    # 方法1: 尝试直接解析
                    try:
                        return json.loads(response.strip())
                    except json.JSONDecodeError:
                        pass

                    # 方法2: 提取JSON对象部分
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        try:
                            json_str = json_match.group()
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass

                    # 方法3: 修复常见的JSON格式问题
                    # 修复未闭合的字符串
                    json_str = response.strip()
                    if '"reasoning": "' in json_str and not json_str.endswith('"}'):
                        # 查找reasoning字段的开始位置
                        reasoning_start = json_str.find('"reasoning": "') + len('"reasoning": "')
                        # 从reasoning开始到结尾都是reasoning的内容
                        reasoning_content = json_str[reasoning_start:]
                        # 转义特殊字符并闭合字符串
                        reasoning_content_escaped = reasoning_content.replace('"', '\\"')
                        fixed_json = json_str[:reasoning_start] + reasoning_content_escaped + '"}'
                        try:
                            return json.loads(fixed_json)
                        except json.JSONDecodeError:
                            pass

                    # 方法4: 最后尝试，构建最小有效JSON
                    try:
                        # 提取selected_scenario_ids
                        ids_match = re.search(r'"selected_scenario_ids":\s*\[([^\]]+)\]', response)
                        if ids_match:
                            ids_str = ids_match.group(1)
                            ids = [int(id_str.strip()) for id_str in ids_str.split(',')]
                            reasoning_match = re.search(r'"reasoning":\s*"([^"]*)', response)
                            reasoning = reasoning_match.group(1) if reasoning_match else "解析失败，使用默认推理"
                            return {
                                "selected_scenario_ids": ids[:top_k],
                                "reasoning": reasoning
                            }
                    except:
                        pass

                    raise json.JSONDecodeError("无法解析LLM响应", response, 0)

                # 使用增强的JSON解析
                try:
                    result = robust_json_parse(response)
                    selected_ids = result.get('selected_scenario_ids', [])
                    reasoning = result.get('reasoning', 'LLM返回格式不完整')

                    if not selected_ids:
                        logger.warning("LLM未返回选择的场景ID")
                        return []

                    # 6. 根据ID筛选场景
                    selected_scenarios = []
                    id_to_item = {item['scenario'].id: item for item in scenarios}

                    for rank, scenario_id in enumerate(selected_ids, 1):
                        if scenario_id in id_to_item:
                            item = id_to_item[scenario_id]
                            item['llm_reasoning'] = reasoning
                            item['llm_rank'] = rank
                            item['selection_source_by_llm'] = 'LLM'
                            selected_scenarios.append(item)
                        else:
                            logger.warning(f"LLM返回的场景ID {scenario_id} 不在候选列表中")

                    logger.info(f"✅ LLM选择了{len(selected_scenarios)}个场景: {selected_ids}")
                    logger.info(f"📝 LLM推理: {reasoning}")

                    return selected_scenarios[:top_k]

                except Exception as parse_error:
                    logger.error(f"❌ LLM响应解析失败: {str(parse_error)}")
                    logger.error(f"原始响应: {response}")
                    return []

            except Exception as e:
                logger.error(f"❌ LLM场景选择失败: {str(e)}")
                return []
        except Exception as e:
            logger.info(f"rananker失败{str(e)}")

    async def rule_rank_scenarios(
            self,
            scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        传统多维度打分排序（保底方案）

        Args:
            scenarios: 候选场景列表
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            top_k: 返回的场景数量

        Returns:
            规则排序的场景列表
        """
        if not scenarios:
            return []

        scored_scenarios = []
        for item in scenarios:
            scenario = item['scenario']

            # 1. 语义相似度得分（来自向量检索）
            semantic_score = item.get('semantic_score')

            # 2. 关键词匹配得分（来自jieba检索）
            keyword_score = item.get('jieba_score')

            # 3. 结构化匹配
            structure_score = self._calculate_structure_match(scenario, patient_info)

            # 4. 临床优先级
            priority_score = self._calculate_priority(scenario, clinical_context)

            # 5. MMR多样性
            diversity_score = item.get('mmr_score')

            # 修正条件判断逻辑
            if structure_score != 0 and priority_score != 0:
                # 两个都不为0的情况
                if semantic_score and diversity_score:
                    final_score = (
                            0.3 * semantic_score +
                            0.2 * structure_score +
                            0.2 * priority_score +
                            0.3 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            elif structure_score != 0:
                # 只有structure_score不为0
                if semantic_score and diversity_score:
                    final_score = (
                            0.35 * semantic_score +
                            0.3 * structure_score +
                            0.35 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            elif priority_score != 0:
                # 只有priority_score不为0
                if semantic_score and diversity_score:
                    final_score = (
                            0.35 * semantic_score +
                            0.3 * priority_score +
                            0.35 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            else:
                # 两个都为0的情况
                if semantic_score and diversity_score:
                    final_score = (
                            0.5 * semantic_score +
                            0.5 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score

            item['rule_score'] = final_score
            item['selection_source_by_rule'] = 'Rule'
            item['score_breakdown'] = {
                'semantic_score': semantic_score,
                'keyword_score': keyword_score,
                'structure_score': structure_score,
                'priority_score': priority_score,
                'diversity_score': diversity_score
            }
            scored_scenarios.append(item)

        scored_scenarios.sort(key=lambda x: x["rule_score"], reverse=True)
        return scored_scenarios

    def _calculate_structure_match(
            self,
            scenario: ClinicalScenario,
            patient_info: PatientInfo
    ) -> float:
        """
        计算结构化匹配得分

        Args:
            scenario: 临床场景
            patient_info: 患者信息

        Returns:
            结构化匹配得分 (0-1)
        """
        score = 0
        count = 0

        # 年龄匹配（支持别名和范围解析）
        if patient_info.age or scenario.age_group:
            age_match_score = self._match_age(patient_info.age, scenario)
            score += age_match_score
            if age_match_score != 0:
                count += 1

        # 性别匹配（支持别名）
        if scenario.gender or patient_info.gender:
            gender_match_score = self._match_gender(patient_info.gender, scenario.gender, scenario)
            score += gender_match_score
            if gender_match_score != 0:
                count += 1

        # 妊娠状态匹配（支持别名）
        if scenario.pregnancy_status or patient_info.pregnancy_status:
            pregnancy_match_score = self._match_pregnancy_status(
                patient_info.pregnancy_status, scenario.pregnancy_status, scenario
            )
            score += pregnancy_match_score
            if pregnancy_match_score != 0:
                count += 1
        if score == 0:
            return score
        return score / count if count > 0 else 0

    def _match_age(self, patient_age: int, scenario) -> float:
        """
        年龄匹配（支持范围解析和别名）

        Args:
            patient_age: 患者年龄
            scenario: 临床场景对象

        Returns:
            匹配得分 (0-1)
        """
        import re
        import jieba

        if not scenario:
            return 0

        # 首先尝试使用age_group
        age_group = scenario.age_group
        description_zh = scenario.description_zh or ""

        # 如果age_group为空，则从description_zh中提取年龄信息
        if not age_group and description_zh:
            age_group = self._extract_age_from_description(description_zh)

        # 标准化年龄组描述
        normalized_group = (age_group or "").lower().replace(' ', '').replace('岁', '')
        normalized_desc = description_zh.lower().replace(' ', '').replace('岁', '')

        # 检查"不限"
        if any(unlimited in normalized_group for unlimited in ['不限', '通用', 'all', 'both', 'any']) or \
                any(unlimited in normalized_desc for unlimited in ['不限', '通用', 'all', 'both', 'any']):
            return 1.0

        # 解析数字范围（从age_group或description中）
        range_pattern = r'(\d+)[-~至](\d+)'
        matches = []

        if age_group:
            matches.extend(re.findall(range_pattern, age_group))
        if description_zh and not matches:  # 如果age_group中没有找到范围，再从description中找
            matches.extend(re.findall(range_pattern, description_zh))

        if matches:
            for min_age, max_age in matches:
                if int(min_age) <= patient_age <= int(max_age):
                    return 1.0
            # 不在范围内，检查是否接近边界
            for min_age, max_age in matches:
                min_age_int, max_age_int = int(min_age), int(max_age)
                if abs(patient_age - min_age_int) <= 2 or abs(patient_age - max_age_int) <= 2:
                    return 0.7  # 接近边界，给较高分数
            return 0.3  # 不在范围内，给部分分数

        # 基于关键词的匹配（同时检查age_group和description）
        search_text = normalized_group + normalized_desc

        # 完整的年龄映射
        age_mapping = {
            '胎儿': ['胎儿', 'fetus', 'fetal'],
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn', '出生', '刚出生'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby', '婴孩'],
            '幼儿': ['幼儿', 'toddler', '幼童'],
            '学龄前': ['学龄前', 'preschool'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'children', 'kid'],
            '学龄期': ['学龄期', '学龄儿童', 'school-age'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager', '青春期', 'puberty'],
            '青年': ['青年', 'young adult', 'young'],
            '成人': ['成人', '成年', 'adult', 'grown-up'],
            '中年': ['中年', 'middle-aged', 'midlife'],
            '老年': ['老年', '老人', 'elderly', 'aged', 'senior', 'geriatric', '老年人', '高龄'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        # 定义各年龄段的年龄范围
        age_ranges = {
            '胎儿': (0, 0),  # 特殊处理
            '新生儿': (0, 1),  # 0-1个月
            '婴儿': (0, 2),  # 0-2岁
            '幼儿': (2, 5),  # 2-5岁
            '学龄前': (3, 6),  # 3-6岁
            '儿童': (6, 12),  # 6-12岁
            '学龄期': (6, 12),  # 6-12岁
            '青少年': (12, 18),  # 12-18岁
            '青年': (18, 40),  # 18-40岁
            '成人': (18, 65),  # 18-65岁
            '中年': (40, 65),  # 40-65岁
            '老年': (65, 150)  # 65岁以上
        }

        # 检查每个年龄段的关键词
        for age_group_name, keywords in age_mapping.items():
            if any(keyword in search_text for keyword in keywords):
                if age_group_name == '不限':
                    return 1.0
                elif age_group_name == '胎儿':
                    # 胎儿是特殊情况，通常无法匹配实际年龄
                    return 0.5
                elif age_group_name in age_ranges:
                    min_age, max_age = age_ranges[age_group_name]
                    if min_age <= patient_age <= max_age:
                        return 1.0
                    else:
                        # 不在范围内，检查是否接近边界
                        if abs(patient_age - min_age) <= 2 or abs(patient_age - max_age) <= 2:
                            return 0.7
                        else:
                            return 0.3

        return 0  # 默认分数

    def _extract_age_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取年龄信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的年龄信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 使用正则表达式提取明显的年龄范围
        range_pattern = r'(\d+)[-~至](\d+)岁?'
        range_matches = re.findall(range_pattern, description_zh)
        if range_matches:
            for min_age, max_age in range_matches:
                return f"{min_age}-{max_age}岁"

        # 完整的年龄映射
        age_mapping = {
            '胎儿': ['胎儿', 'fetus', 'fetal'],
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn', '出生', '刚出生'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby', '婴孩'],
            '幼儿': ['幼儿', 'toddler', '幼童'],
            '学龄前': ['学龄前', 'preschool'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'children', 'kid'],
            '学龄期': ['学龄期', '学龄儿童', 'school-age'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager', '青春期', 'puberty'],
            '青年': ['青年', 'young adult', 'young'],
            '成人': ['成人', '成年', 'adult', 'grown-up'],
            '中年': ['中年', 'middle-aged', 'midlife'],
            '老年': ['老年', '老人', 'elderly', 'aged', 'senior', 'geriatric', '老年人', '高龄'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        # 使用jieba分词并查找年龄相关关键词
        words = jieba.cut(description_zh)

        for word in words:
            word_lower = word.lower()
            for age_group, keywords in age_mapping.items():
                if word_lower in [kw.lower() for kw in keywords]:
                    return age_group

        return ""

    def _match_gender(self, patient_gender: str, scenario_gender: str, scenario: ClinicalScenario = None) -> float:
        """
        性别匹配（支持别名）

        Args:
            patient_gender: 患者性别
            scenario_gender: 场景性别要求
            scenario: 临床场景对象（可选，用于从描述中提取性别）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_gender:
            return 0  # 患者性别为空时返回中等分数

        # 如果scenario_gender为空，尝试从场景描述中提取
        if not scenario_gender and scenario and scenario.description_zh:
            scenario_gender = self._extract_gender_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_gender:
            return 0

        # 标准化输入
        patient_gender_norm = patient_gender.strip().lower()
        scenario_gender_norm = scenario_gender.strip().lower()

        # 检查是否匹配任何别名
        for standard_gender, aliases in self.gender_mapping.items():
            # 患者性别匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_gender_norm in patient_aliases_lower

            # 场景性别要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_gender_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_gender == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_gender_norm in scenario_gender_norm or scenario_gender_norm in patient_gender_norm:
            return 0.8

        return 0.0

    def _extract_gender_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取性别信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的性别信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 扩展的性别映射
        gender_mapping = {
            '男性': [
                '男', '男性', '男人', '男士', '男患者', '男童', '男孩', '男生', '男婴', '男青年',
                '男子', '男病人', '男科', '雄性', '公', '雄', 'male', 'm', 'man', 'boy', 'gentleman'
            ],
            '女性': [
                '女', '女性', '女人', '女士', '女患者', '女童', '女孩', '女生', '女婴', '女青年',
                '女子', '女病人', '妇科', '雌性', '母', '雌', 'female', 'f', 'woman', 'girl', 'lady'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', '男女', '男女均可', '男女皆可',
                'any', 'all', 'both', 'either', '通用', 'common', 'general', "成人", "成年人"
            ]
        }

        # 使用正则表达式提取明显的性别信息
        gender_patterns = [
            r'([男女])性?患者?',
            r'患者?([男女])',
            r'([男女])性',
            r'([男女])子',
            r'([男女])',
            r'(雄性|雌性)',
            r'(男性|女性)',
            r'(男科|妇科)'
        ]

        for pattern in gender_patterns:
            matches = re.findall(pattern, description_zh)
            if matches:
                gender_char = matches[0]
                if gender_char in ['男', '男性', '男科', '雄性']:
                    return '男性'
                elif gender_char in ['女', '女性', '妇科', '雌性']:
                    return '女性'

        # 使用jieba分词并查找性别相关关键词
        words = jieba.cut(description_zh)

        # 创建关键词到标准性别的映射
        keyword_to_gender = {}
        for gender, keywords in gender_mapping.items():
            for keyword in keywords:
                keyword_to_gender[keyword.lower()] = gender

        # 检查每个分词是否匹配性别关键词
        for word in words:
            word_lower = word.lower()
            if word_lower in keyword_to_gender:
                return keyword_to_gender[word_lower]

        # 检查整个描述中是否包含性别关键词（用于处理未正确分词的情况）
        description_lower = description_zh.lower()
        for gender, keywords in gender_mapping.items():
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    return gender

        return ""

    def _match_pregnancy_status(self, patient_status: str, scenario_status: str,
                                scenario: ClinicalScenario = None) -> float:
        """
        妊娠状态匹配（支持别名）

        Args:
            patient_status: 患者妊娠状态
            scenario_status: 场景妊娠状态要求
            scenario: 临床场景对象（可选，用于从描述中提取妊娠状态）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_status:
            return 0  # 患者妊娠状态为空时返回中等分数

        # 如果scenario_status为空，尝试从场景描述中提取
        if not scenario_status and scenario and scenario.description_zh:
            scenario_status = self._extract_pregnancy_status_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_status:
            return 0

        # 标准化输入
        patient_status_norm = patient_status.strip().lower()
        scenario_status_norm = scenario_status.strip().lower()

        # 检查是否匹配任何别名
        for standard_status, aliases in self.pregnancy_mapping.items():
            # 患者状态匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_status_norm in patient_aliases_lower

            # 场景状态要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_status_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_status == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_status_norm in scenario_status_norm or scenario_status_norm in patient_status_norm:
            return 0.8

        return 0.0

    def _extract_pregnancy_status_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取妊娠状态信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的妊娠状态信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 扩展的妊娠状态映射
        pregnancy_mapping = {
            '妊娠期': [
                '妊娠', '怀孕', '孕妇', '孕期', '妊娠期', '孕产妇', '孕产期', '孕周', '孕早期',
                '孕中期', '孕晚期', '早孕', '中孕', '晚孕', '怀孕期', 'pregnancy', 'pregnant',
                'gestation', 'gestational', 'prenatal', 'antenatal'
            ],
            '非妊娠期': [
                '非妊娠', '非孕妇', '未怀孕', '未妊娠', '非孕期', '未孕', '非孕', 'non-pregnancy',
                'not pregnant', 'non-pregnant', 'non-gestational'
            ],
            '哺乳期': [
                '哺乳', '哺乳期', '母乳喂养', '母乳', '哺乳期妇女', '哺乳母亲', 'lactation',
                'breastfeeding', 'nursing', 'lactating'
            ],
            '备孕期': [
                '备孕', '备孕期', '计划怀孕', '准备怀孕', 'preconception', 'trying to conceive',
                'fertility', 'pre-pregnancy'
            ],
            '产后': [
                '产后', '分娩后', '生产后', 'postpartum', 'postnatal', 'after delivery',
                'puerperium', 'post-partum'
            ],
            '不孕': [
                '不孕', '不孕症', '不育', '不育症', 'infertility', 'infertile', 'sterility'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', 'any', 'all', 'both', 'either',
                '通用', 'common', 'general'
            ]
        }

        # 使用正则表达式提取明显的妊娠状态信息
        pregnancy_patterns = [
            r'(妊娠|怀孕|孕妇|孕期|孕周|孕早期|孕中期|孕晚期)',
            r'(非妊娠|非孕妇|未怀孕|未妊娠|未孕|非孕)',
            r'(哺乳|哺乳期|母乳喂养)',
            r'(备孕|备孕期|计划怀孕)',
            r'(产后|分娩后|生产后)',
            r'(不孕|不孕症|不育|不育症)'
        ]

        for pattern in pregnancy_patterns:
            matches = re.findall(pattern, description_zh)
            if matches:
                status_char = matches[0]
                if status_char in ['妊娠', '怀孕', '孕妇', '孕期', '孕周', '孕早期', '孕中期', '孕晚期']:
                    return '妊娠期'
                elif status_char in ['非妊娠', '非孕妇', '未怀孕', '未妊娠', '未孕', '非孕']:
                    return '非妊娠期'
                elif status_char in ['哺乳', '哺乳期', '母乳喂养']:
                    return '哺乳期'
                elif status_char in ['备孕', '备孕期', '计划怀孕']:
                    return '备孕期'
                elif status_char in ['产后', '分娩后', '生产后']:
                    return '产后'
                elif status_char in ['不孕', '不孕症', '不育', '不育症']:
                    return '不孕'

        # 使用jieba分词并查找妊娠状态相关关键词
        words = jieba.cut(description_zh)

        # 创建关键词到标准状态的映射
        keyword_to_status = {}
        for status, keywords in pregnancy_mapping.items():
            for keyword in keywords:
                keyword_to_status[keyword.lower()] = status

        # 检查每个分词是否匹配妊娠状态关键词
        for word in words:
            word_lower = word.lower()
            if word_lower in keyword_to_status:
                return keyword_to_status[word_lower]

        # 检查整个描述中是否包含妊娠状态关键词（用于处理未正确分词的情况）
        description_lower = description_zh.lower()
        for status, keywords in pregnancy_mapping.items():
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    return status

        return ""

    def _calculate_priority(
            self,
            scenario: ClinicalScenario,
            clinical_context: ClinicalContext
    ) -> float:
        """
        计算临床优先级得分（支持科室别名）

        Args:
            scenario: 临床场景
            clinical_context: 临床上下文

        Returns:
            优先级得分 (0-1)
        """
        score = 0.0  # 基础分
        count = 0
        # 科室匹配（支持别名和模糊匹配）
        if clinical_context.department and scenario.panel:
            panel_name = scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else ''
            department_score = self._match_department(clinical_context.department, panel_name)
            score += department_score
            if department_score != 0:
                count += 1

        # 症状严重程度匹配
        severity_score = self._match_urgency(clinical_context.symptom_severity, scenario.urgency_level, scenario)
        score += severity_score
        if severity_score != 0:
            count += 1

        if score == 0:
            return score

        return min(score // count, 1.0)

    def _match_department(self, patient_dept: str, scenario_dept: str) -> float:
        """
        科室匹配（支持别名和模糊匹配）

        Args:
            patient_dept: 患者科室
            scenario_dept: 场景科室

        Returns:
            匹配得分 (0-1)
        """
        if not patient_dept or not scenario_dept:
            return 0.0

        patient_dept_norm = patient_dept.lower().strip()
        scenario_dept_norm = scenario_dept.lower().strip()

        # 完全匹配
        if patient_dept_norm == scenario_dept_norm:
            return 1.0

        # 包含关系
        if patient_dept_norm in scenario_dept_norm or scenario_dept_norm in patient_dept_norm:
            return 0.8

        # 常见科室别名映射
        for standard_dept, aliases in self.department_mapping.items():
            patient_aliases = [standard_dept] + aliases
            scenario_aliases = [standard_dept] + aliases

            patient_match = any(alias.lower() in patient_dept_norm for alias in patient_aliases)
            scenario_match = any(alias.lower() in scenario_dept_norm for alias in scenario_aliases)

            if patient_match and scenario_match:
                return 0.9

        return 0.0

    def _match_urgency(self, patient_urgency: str, scenario_urgency: str, scenario: ClinicalScenario = None) -> float:
        """
        紧急程度匹配（支持别名）

        Args:
            patient_urgency: 患者紧急程度
            scenario_urgency: 场景紧急程度要求
            scenario: 临床场景对象（可选，用于从描述中提取紧急程度）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_urgency:
            return 0

        # 如果scenario_urgency为空，尝试从场景描述中提取
        if not scenario_urgency and scenario and scenario.description_zh:
            scenario_urgency = self._extract_urgency_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_urgency:
            return 0

        # 标准化输入
        patient_urgency_norm = patient_urgency.strip().lower()
        scenario_urgency_norm = scenario_urgency.strip().lower()

        # 检查是否匹配任何别名
        for standard_urgency, aliases in self.urgency_mapping.items():
            # 患者紧急程度匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_urgency_norm in patient_aliases_lower

            # 场景紧急程度要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_urgency_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_urgency == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_urgency_norm in scenario_urgency_norm or scenario_urgency_norm in patient_urgency_norm:
            return 0.8

        return 0.0

    def _extract_urgency_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取紧急程度信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的紧急程度信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 使用正则表达式提取明显的紧急程度信息
        urgency_patterns = [
            r'(危及生命|生命危险|life-threatening|critical condition)',
            r'(紧急|急诊|急症|急性|urgent|emergency|critical|acute)',
            r'(重度|严重|severe)',
            r'(中度|中等|moderate|serious)',
            r'(亚急性|subacute)',
            r'(复发性|复发|反复|recurrent|relapse)',
            r'(常规|慢性|常规检查|mild|chronic|routine)',
            r'(轻微|轻度|mild|minor)',
            r'(不稳定|unstable)',
            r'(稳定|stable)',
            r'(择期|elective)',
            r'(预防性|预防|preventive|prophylactic)',
            r'(筛查|screening)',
            r'(随访|follow-up)',
            r'(康复|康复期|rehabilitation|recovery)',
            r'(终末期|晚期|末期|end-stage|terminal)',
            r'(姑息治疗|姑息|palliative)'
        ]

        for pattern in urgency_patterns:
            matches = re.findall(pattern, description_zh, re.IGNORECASE)
            if matches:
                urgency_char = matches[0]
                if urgency_char in ['危及生命', '生命危险', 'life-threatening', 'critical condition']:
                    return '危及生命'
                elif urgency_char in ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute']:
                    return '紧急'
                elif urgency_char in ['重度', '严重', 'severe']:
                    return '重度'
                elif urgency_char in ['中度', '中等', 'moderate', 'serious']:
                    return '中度'
                elif urgency_char in ['亚急性', 'subacute']:
                    return '亚急性'
                elif urgency_char in ['复发性', '复发', '反复', 'recurrent', 'relapse']:
                    return '复发性'
                elif urgency_char in ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine']:
                    return '常规'
                elif urgency_char in ['轻微', '轻度', 'mild', 'minor']:
                    return '轻微'
                elif urgency_char in ['不稳定', 'unstable']:
                    return '不稳定'
                elif urgency_char in ['稳定', 'stable']:
                    return '稳定'
                elif urgency_char in ['择期', 'elective']:
                    return '择期'
                elif urgency_char in ['预防性', '预防', 'preventive', 'prophylactic']:
                    return '预防性'
                elif urgency_char in ['筛查', 'screening']:
                    return '筛查'
                elif urgency_char in ['随访', 'follow-up']:
                    return '随访'
                elif urgency_char in ['康复', '康复期', 'rehabilitation', 'recovery']:
                    return '康复'
                elif urgency_char in ['终末期', '晚期', '末期', 'end-stage', 'terminal']:
                    return '终末期'
                elif urgency_char in ['姑息治疗', '姑息', 'palliative']:
                    return '姑息治疗'

        # 使用jieba分词并查找紧急程度相关关键词
        words = jieba.cut(description_zh)

        urgency_keywords = {
            '危及生命': ['危及生命', '生命危险', 'life-threatening', 'critical condition'],
            '紧急': ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute'],
            '重度': ['重度', '严重', 'severe'],
            '中度': ['中度', '中等', 'moderate', 'serious'],
            '亚急性': ['亚急性', 'subacute'],
            '复发性': ['复发性', '复发', '反复', 'recurrent', 'relapse'],
            '常规': ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine'],
            '轻微': ['轻微', '轻度', 'mild', 'minor'],
            '不稳定': ['不稳定', 'unstable'],
            '稳定': ['稳定', 'stable'],
            '择期': ['择期', 'elective'],
            '预防性': ['预防性', '预防', 'preventive', 'prophylactic'],
            '筛查': ['筛查', 'screening'],
            '随访': ['随访', 'follow-up'],
            '康复': ['康复', '康复期', 'rehabilitation', 'recovery'],
            '终末期': ['终末期', '晚期', '末期', 'end-stage', 'terminal'],
            '姑息治疗': ['姑息治疗', '姑息', 'palliative'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        for word in words:
            word_lower = word.lower()
            for urgency, keywords in urgency_keywords.items():
                if word_lower in [kw.lower() for kw in keywords]:
                    return urgency

        return ""

    async def get_recommendations_simple(self, filter_scenario_with_recommendations, patient_info, clinical_context,max_scenarios,
                                         max_recommendations_per_scenario):
        # 开始让llm根据病症做推荐
        prompt=self._build_comprehensive_prompt_with_grading(filter_scenario_with_recommendations, patient_info, clinical_context,max_scenarios,max_recommendations_per_scenario)
        try:
            # 单次LLM调用
            response = await self.ai_service._call_llm(prompt)

            # 解析JSON结果
            import re
            import json

            json_match = safe_parse_llm_response(response)
            if not json_match:
                logger.error("LLM返回格式错误，使用降级方案")
                return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations, max_scenarios, patient_info)

            try:
                result = json_match
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {e}")
                return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations, max_scenarios, patient_info)

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

                original_scenario_data =filter_scenario_with_recommendations[scenario_index - 1]
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
            logger.error(f"❌ 综合场景分级筛选失败: {str(e)}", exc_info=True)
            return self._fallback_comprehensive_selection_with_grading(filter_scenario_with_recommendations, max_scenarios, patient_info)

    def _build_comprehensive_prompt_with_grading(
            self,
            all_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_scenarios: int,
            max_recommendations_per_scenario: int
    ) -> str:
        """构建完整的提示词，确保总token数不超过3600"""

        # 构建各个部分
        import qwen_token_counter
        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)

        # 计算固定部分的token数
        fixed_parts = patient_info_content + clinical_context_content
        fixed_tokens = qwen_token_counter.get_token_count(fixed_parts)

        # 为任务指令预留空间（估计约500-800 token）
        task_reserve_tokens = 900
        available_scenario_tokens = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]-800 - fixed_tokens - task_reserve_tokens
        logger.info(f"可用的提示词token数{available_scenario_tokens}")
        # 构建场景内容，限制在可用token数内
        scenarios_content = self.build_scenarios_with_recommend(
            all_scenarios,
            patient_info,
            max_tokens=available_scenario_tokens
        )

        # 构建任务指令，使用实际显示的场景数量
        task_instruction = self.build_task_instruction(
            max_scenarios=max_scenarios,
            max_recommendations_per_scenario=max_recommendations_per_scenario
        )

        # 组合完整提示词
        comprehensive_prompt = (
                patient_info_content +
                clinical_context_content +
                scenarios_content +
                task_instruction
        )

        # 最终token计数验证
        total_tokens = qwen_token_counter.get_token_count(comprehensive_prompt)
        if total_tokens > self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]-800:
            logger.info(f"仍然超出{4096-800-total_tokens}个token,进行截断")
            # 如果仍然超出，进一步截断场景部分
            scenarios_content = self._truncate_scenarios_further(scenarios_content,
                                                                 available_scenario_tokens - fixed_tokens - task_reserve_tokens)
            comprehensive_prompt = (
                    patient_info_content +
                    clinical_context_content +
                    scenarios_content +
                    task_instruction
            )

        return comprehensive_prompt



    def _truncate_scenarios_further(self, scenarios_content: str, max_tokens: int) -> str:
        """进一步截断场景内容"""
        current_tokens = qwen_token_counter.get_token_count(scenarios_content)
        if current_tokens <= max_tokens:
            return scenarios_content

        # 逐步移除最后一个场景
        while current_tokens > max_tokens and "### 场景" in scenarios_content:
            # 找到最后一个场景的开始位置
            last_scenario_start = scenarios_content.rfind("### 场景")
            if last_scenario_start == -1:
                break

            # 找到这个场景的结束位置（下一个场景开始或文件结束）
            next_scenario_start = scenarios_content.find("### 场景", last_scenario_start + 1)
            if next_scenario_start != -1:
                scenarios_content = scenarios_content[:last_scenario_start] + scenarios_content[next_scenario_start:]
            else:
                scenarios_content = scenarios_content[:last_scenario_start]

            # 添加截断提示
            scenarios_content += "\n\n<!-- 由于token限制，部分场景未显示 -->\n"
            current_tokens = qwen_token_counter.get_token_count(scenarios_content)

        return scenarios_content

    def build_patient_context(self, patient_info: PatientInfo) -> str:
        """构建患者信息"""
        patient_context = f"""
       ## 患者基本信息
       - **年龄**: {patient_info.age}岁
       - **性别**: {patient_info.gender}
       - **妊娠状态**: {patient_info.pregnancy_status or '非妊娠期'}
       - **过敏史**: {', '.join(patient_info.allergies) if patient_info.allergies else '无已知过敏'}
       - **重要合并症**: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无已知合并症'}
       ### 风险评估
       """
        # 添加关键风险提示
        risk_notes = []
        if patient_info.pregnancy_status in ['妊娠', '怀孕', '妊娠期']:
            risk_notes.append("⚠️ **妊娠期患者**: 严格避免电离辐射检查")

        if any('碘' in allergy or '对比剂' in allergy for allergy in patient_info.allergies):
            risk_notes.append("⚠️ **对比剂过敏风险**: 慎用增强检查")

        if any('肾' in comorbidity for comorbidity in patient_info.comorbidities):
            risk_notes.append("⚠️ **肾功能关注**: 评估对比剂使用风险")

        if risk_notes:
            patient_context += "\n".join(risk_notes)
        else:
            patient_context += "无特殊风险提示"

        return patient_context

    def build_clinical_context(self, clinical_context: ClinicalContext) -> str:
        """构建临床信息"""
        clinical_content = f"""
        ## 临床信息
        ### 就诊背景
        - **就诊科室**: {clinical_context.department}
        - **主诉**: {clinical_context.chief_complaint}
        - **症状持续时间**: {clinical_context.symptom_duration or '未记录'}
        ### 诊断信息
        - **现病史**: {clinical_context.present_illness or '信息不足'}
        - **主诊断**: {clinical_context.diagnosis or '待明确诊断'}
        """
        # 添加临床关键点提取
        key_clinical_points = []
        if '急性' in clinical_context.chief_complaint or '急诊' in clinical_context.department:
            key_clinical_points.append("🔴 急性病程：需快速诊断")
        if '外伤' in clinical_context.chief_complaint:
            key_clinical_points.append("🟡 外伤相关：关注结构性损伤")
        if '肿瘤' in clinical_context.diagnosis or '占位' in clinical_context.diagnosis:
            key_clinical_points.append("🔵 肿瘤评估：需要精确分期")

        if key_clinical_points:
            clinical_content += f"\n### 临床特征\n" + "\n".join(f"- {point}" for point in key_clinical_points)

        return clinical_content

    def build_scenarios_with_recommend(self, all_scenarios: List[Dict[str, Any]],patient_info: PatientInfo, max_tokens: int = 2500):
        """构建场景内容，限制在指定token数内"""

        scenarios_text = "## 可选临床场景及推荐项目\n\n"

        # 计算初始token数
        total_tokens = qwen_token_counter.get_token_count(scenarios_text)
        scenarios_added = 0
        recommendations_added = 0

        for scenario_idx, scenario_data in enumerate(all_scenarios, 1):
            scenario = scenario_data['scenario']
            recommendations = scenario_data.get('recommendations', [])

            # 构建当前场景的完整文本
            current_scenario_text = f"### 场景{scenario_idx}: {scenario.description_zh}\n"
            current_scenario_text += f"- **场景ID**: {scenario.semantic_id}\n"
            current_scenario_text += f"- **适用科室**: {scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知'}\n"
            current_scenario_text += f"- **适用人群**: {scenario.patient_population or '未知'}\n"
            # current_scenario_text += f"- **临床背景**: {scenario.clinical_context or '无'}\n\n"

            if not recommendations:
                current_scenario_text += "  暂无推荐项目\n\n"
            else:
                current_scenario_text += "#### 推荐项目清单:\n"

                for rec_idx, rec_data in enumerate(recommendations, 1):
                    recommendation = rec_data['recommendation']
                    procedure = rec_data['procedure']

                    # 构建推荐项目文本
                    current_item_text = f"{rec_idx}. **{procedure.name_zh}**\n"

                    # 技术细节（简化）
                    # tech_details = []
                    # if procedure.modality:
                    #     tech_details.append(f"检查方式: {procedure.modality}")
                    # if procedure.body_part:
                    #     tech_details.append(f"检查部位: {procedure.body_part}")

                    # 安全性关键信息
                    # safety_flags = []
                    # if procedure.contrast_used and any('过敏' in allergy for allergy in getattr(patient_info, 'allergies', []) if allergy):
                    #         safety_flags.append("⚠️ 使用对比剂(注意过敏史)")
                    # elif procedure.contrast_used:
                    #         safety_flags.append("使用对比剂")

                    # if (procedure.radiation_level and
                    #             getattr(patient_info, 'pregnancy_status', '') in ['妊娠', '怀孕']):
                    #         safety_flags.append("⚠️ 有辐射(妊娠禁忌)")
                    # elif procedure.radiation_level:
                    #         safety_flags.append(f"辐射等级: {procedure.radiation_level}")
                    #
                    # if safety_flags:
                    #         current_item_text += f"   - 安全信息: {', '.join(safety_flags)}\n"
                    # 关键信息：ACR评分和安全性
                    current_item_text += f"   - **ACR适宜性评分**: {recommendation.appropriateness_rating}/9\n"
                    if recommendation.appropriateness_category_zh:
                        current_item_text += f"   - 推荐级别: {recommendation.appropriateness_category_zh}\n"


                    # critical_contraindications = []
                    # if (recommendation.pregnancy_safety and
                    #         getattr(patient_info, 'pregnancy_status', '') in ['妊娠', '怀孕'] and
                    #         '禁忌' in recommendation.pregnancy_safety):
                    #     critical_contraindications.append("妊娠禁忌")
                    #
                    # if recommendation.contraindications:
                    #     # 只显示前50个字符的关键禁忌
                    #     contra_preview = recommendation.contraindications[:50]
                    #     if '肾功能' in contra_preview and any('肾' in comorbidity for comorbidity in
                    #                                           getattr(patient_info, 'comorbidities', [])):
                    #         critical_contraindications.append("肾功能限制")
                    #
                    # if critical_contraindications:
                    #     current_item_text += f"   - ⚠️ 禁忌提示: {', '.join(critical_contraindications)}\n"
                    # 核心推荐理由(精简)
                    # if recommendation.reasoning_zh:
                    #     reasoning = recommendation.reasoning_zh[:50] + "..." if len(
                    #         recommendation.reasoning_zh) > 50 else recommendation.reasoning_zh
                    #     current_item_text += f"   - 主要优势: {reasoning}\n"

                    current_item_text += "\n"
                    current_scenario_text += current_item_text
                    recommendations_added += 1

            # 添加场景分隔符
            current_scenario_text += "---\n\n"

            # 计算当前场景的总token数
            current_scenario_tokens = qwen_token_counter.get_token_count(current_scenario_text)

            # 检查添加整个场景后是否会超过限制
            if total_tokens + current_scenario_tokens <= max_tokens:
                scenarios_text += current_scenario_text
                total_tokens += current_scenario_tokens
                scenarios_added += 1
            else:
                # 如果超过限制，添加截断提示并跳出循环
                remaining_scenarios = len(all_scenarios) - scenario_idx
                if remaining_scenarios > 0:
                    logger.info( f"### 场景{scenario_idx}及后续{remaining_scenarios}个场景由于token限制未显示\n")
                    # scenarios_text += f"---\n\n"
                break

        # 添加统计信息
        stats_text = f"\n<!-- 场景部分使用token: {total_tokens}/{max_tokens}, 显示场景: {scenarios_added}/{len(all_scenarios)}, 显示推荐项目: {recommendations_added} -->\n"
        # stats_tokens = qwen_token_counter.get_token_count(stats_text)
        logger.info(stats_text)

        return scenarios_text

    def build_task_instruction(self, max_scenarios: int,
                               max_recommendations_per_scenario: int):
        """构建任务指令"""
        task_instruction = f"""

        ## 🎯 任务目标
        基于循证医学原则，为当前患者选择最合适的影像学检查方案。

        ## 📋 决策框架

        ### 第一级：场景筛选
        从给你的上下文的临床场景中，选择{max_scenarios}个最相关的临床场景：
        - **临床匹配度**：场景描述与患者主诉、诊断的契合程度
        - **科室适用性**：场景与就诊科室专业特长的匹配度
        - **人群适应性**：场景适用人群与患者特征的符合度

        ### 第二级：检查项目分级
        对每个选中场景，按以下标准分级：

        #### 🟢 极其推荐 (Highly Recommended)
        - 无明确禁忌症
        - 与当前临床问题高度相关
        - 诊断价值明确且风险可控

        #### 🟡 推荐 (Recommended)  
        - 无重大禁忌症
        - 临床适用性良好
        - 可作为辅助或替代方案

        #### 🔴 不太推荐 (Less Recommended)
        - 存在明确禁忌症
        - 与临床需求匹配度低
        - 有更优的替代方案

        ## ⚠️ 安全优先原则

        ### 绝对禁忌
        1. **妊娠期**：严格避免电离辐射检查（CT、X线、PET-CT）
        2. **对比剂过敏**：禁用含碘/钆对比剂的增强检查
        3. **肾功能不全**：慎用对比剂，评估肾病风险

        ### 相对禁忌
        1. **幽闭恐惧症**：MRI检查需特殊准备
        2. **金属植入物**：部分MRI受限
        3. **肥胖患者**：考虑设备承重和图像质量限制

        ## 🎛️ 技术考量

        ### 诊断效能优先级
        1. **敏感性/特异性**：疾病的检测和排除能力
        2. **空间分辨率**：解剖细节显示能力
        3. **功能信息**：除形态学外的功能评估
        4. **检查时长**：患者耐受度和临床紧迫性

        ## 📊 输出要求

        请严格按照以下JSON格式输出推荐结果：

        ```json
        {{
            "selected_scenarios": [
                {{
                    "scenario_index": 1,
                    "scenario_id": "场景语义ID",
                    "comprehensive_score": 85,
                    "scenario_reasoning": "基于患者急性腹痛主诉和年龄因素，此腹部急症场景最为匹配",
                    "recommendation_grades": {{
                        "highly_recommended": [1, 2],
                        "recommended": [3],
                        "less_recommended": [4, 5]
                    }},
                    "final_choices": [该场景下针对该患者的最佳推荐项目，注意！填推荐项目的名字，且推荐项目名字必须为{max_recommendations_per_scenario}个！],
                    "grading_reasoning": "CT平扫ACR评分9分，对急腹症诊断价值最高；超声无辐射，适合初步筛查"
                }},
                {{
                    "scenario_index": 这里是索引id(例如：2),
                    "scenario_id": "场景语义ID",
                    "comprehensive_score": "0-100综合评分",
                    "scenario_reasoning": "场景匹配度分析",
                    "recommendation_grades": {{
                                  "highly_recommended": [1, 3],
                                  "recommended": [2, 4],
                                  "less_recommended": [5]
                              }},
                    "final_choices":[该场景下针对该患者的最佳推荐项目，注意！填推荐项目的名字，且推荐项目名字必须为{max_recommendations_per_scenario}个！]
                    "grading_reasoning": "分级临床理由"
                          }},
            ],
            "overall_reasoning": "总体选择策略，重点说明安全性考量和诊断路径"
        }}
         **重要：
              -请只输出纯JSON格式，不要包含任何其他文字、说明或Markdown标记！确保JSON格式完全正确。**
              -注意选择的临床场景数一定不能超过{max_scenarios}个！
        """



        return task_instruction





        # task_instruction = f"""
        #             ## 任务说明
        #
        #             作为经验丰富的临床医生，请根据患者信息和临床上下文，完成以下**两级智能筛选**：
        #
        #             ### 第一级：场景筛选
        #             从上下文的临床场景中选择最符合患者基本信息和临床信息的最相关的**{max_scenarios}个临床场景**，按临床优先级排序。
        #
        #             ### 第二级：推荐项目三级分级评估
        #             结合患者基本信息和临床信息对每个选中的临床场景的所有推荐项目进行**三级推荐等级划分**：
        #
        #             - **极其推荐 (Highly Recommended)**: 评分高，证据充分，与患者情况完美匹配，安全性和诊断价值俱佳，无明显禁忌
        #             - **推荐 (Recommended)**: 评分中等，临床适用性良好，风险收益比合理，可能存在轻微限制
        #             - **不太推荐 (Less Recommended)**: 评分低，或存在安全隐患，或有明确禁忌症，或与当前临床需求匹配度不高
        #             ##注意
        #               - 每个临床场景的推荐项目必须为{max_recommendations_per_scenario}个。
        #             ## 输出格式
        #             请严格按以下JSON格式输出，不要额外解释：
        #
        #             ```json
        #             {{
        #                 "selected_scenarios": [
        #                   {{
        #                       "scenario_index": 这里是索引id(例如：1),
        #                       "scenario_id": "场景语义ID",
        #                       "comprehensive_score": "0-100综合评分",
        #                       "scenario_reasoning": "场景匹配度分析",
        #                       "recommendation_grades": {{
        #                           "highly_recommended": [1, 3],
        #                           "recommended": [2, 4],
        #                           "less_recommended": [5]
        #                       }},
        #                       "final_choices":[该场景下针对该患者的最佳推荐项目，注意！填推荐项目的名字，且推荐项目名字必须为{max_recommendations_per_scenario}个！]
        #                       "grading_reasoning": "分级临床理由"
        #                   }},
        #                   {{
        #                       "scenario_index": 这里是索引id(例如：2),
        #                       "scenario_id": "场景语义ID",
        #                       "comprehensive_score": "0-100综合评分",
        #                       "scenario_reasoning": "场景匹配度分析",
        #                       "recommendation_grades": {{
        #                           "highly_recommended": [1, 3],
        #                           "recommended": [2, 4],
        #                           "less_recommended": [5]
        #                       }},
        #                       "final_choices":[该场景下针对该患者的最佳推荐项目，注意！填推荐项目的名字，且推荐项目名字必须为{max_recommendations_per_scenario}个！]
        #                       "grading_reasoning": "分级临床理由"
        #                   }},
        #               ],
        #                 "overall_reasoning": "总体选择策略说明，不超过100字"
        #             }}"""
    def _fallback_comprehensive_selection_with_grading(
            self,
            all_scenarios: List[Dict[str, Any]],
            max_scenarios: int,
            patient_info: PatientInfo
    ) -> List[Dict[str, Any]]:
        """降级方案：基于完整字段信息进行智能分级"""

        scored_scenarios = []

        for scenario_data in all_scenarios:
            recommendations = scenario_data.get('recommendations', [])
            if not recommendations:
                continue

            scenario = scenario_data['scenario']

            # 智能分级：考虑ACR评分 + 安全性 + 临床匹配度
            highly_recommended = []
            recommended = []
            less_recommended = []

            for rec_data in recommendations:
                recommendation = rec_data['recommendation']
                procedure = rec_data['procedure']
                acr_rating = recommendation.appropriateness_rating

                # 安全性检查
                safety_issues = []

                # 妊娠安全性检查
                if patient_info.pregnancy_status and patient_info.pregnancy_status != '非妊娠期':
                    if recommendation.pregnancy_safety and '禁忌' in recommendation.pregnancy_safety:
                        safety_issues.append("妊娠禁忌")

                # 辐射安全性考虑
                if procedure.radiation_level and procedure.radiation_level in ['高', '中']:
                    safety_issues.append(f"辐射{procedure.radiation_level}")

                # 禁忌症检查
                if recommendation.contraindications:
                    safety_issues.append("存在禁忌症")

                # 基于ACR评分和安全问题的分级逻辑
                if acr_rating >= 7 and not safety_issues:
                    level = 'highly_recommended'
                    level_zh = '极其推荐'
                    highly_recommended.append(rec_data)
                elif acr_rating >= 4 and len(safety_issues) <= 1:
                    level = 'recommended'
                    level_zh = '推荐'
                    recommended.append(rec_data)
                else:
                    level = 'less_recommended'
                    level_zh = '不太推荐'
                    less_recommended.append(rec_data)

                # 添加分级信息到副本
                rec_data_copy = rec_data.copy()
                rec_data_copy['recommendation_level'] = level
                rec_data_copy['recommendation_level_zh'] = level_zh
                rec_data_copy['safety_issues'] = safety_issues

            # 计算综合评分（基于高推荐项目比例和ACR平均分）
            if recommendations:
                highly_ratio = len(highly_recommended) / len(recommendations)
                avg_acr = sum(rec['recommendation'].appropriateness_rating for rec in recommendations) / len(
                    recommendations)
                comprehensive_score = int((highly_ratio * 0.7 + avg_acr / 9 * 0.3) * 100)
            else:
                comprehensive_score = 0

            scored_scenarios.append({
                'comprehensive_score': comprehensive_score,
                'scenario_reasoning': '基于ACR评分和安全性的降级分级',
                'grading_reasoning': f'ACR≥7且无安全问题:极其推荐; ACR4-6且安全問題≤1:推荐; 其他:不太推荐',
                'overall_reasoning': 'LLM调用失败，使用智能降级分级方案',
                'graded_recommendations': {
                    'highly_recommended': highly_recommended,
                    'recommended': recommended,
                    'less_recommended': less_recommended
                },
                'recommendation_summary': {
                    'highly_recommended_count': len(highly_recommended),
                    'recommended_count': len(recommended),
                    'less_recommended_count': len(less_recommended),
                    'total_recommendations': len(recommendations)
                },
                'scenario_metadata': {
                    'scenario_id': scenario.semantic_id,
                    'description': scenario.description_zh,
                    'panel': getattr(scenario.panel, 'name_zh', '未知'),
                    'patient_population': scenario.patient_population,
                    'fallback_used': True
                }
            })

        # 按评分排序
        scored_scenarios.sort(key=lambda x: x['comprehensive_score'], reverse=True)
        return scored_scenarios[:max_scenarios]