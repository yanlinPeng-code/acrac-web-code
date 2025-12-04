import time
from typing import List, Dict, Any, Tuple, Optional
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v2.base import Base
from app.utils.helper.helper import safe_parse_llm_response, safe_process_recommendation_grades
from app.utils.logger.simple_logger import get_logger

from app.service.rag_v2.prompt.base_prompt import BasePrompt

logger=get_logger(__name__)
class AdaptiveThresholdStrategy:
    """基础阈值策略"""

    def __init__(self):
        self.threshold_config = {
            'token_threshold':  4096,
            'max_scenarios_single_call': 5,
            'max_total_recommendations': 30,
            'max_avg_recommendations_per_scenario': 8
        }

        self.weights = {
            'token_ratio': 0.5,
            'scenario_ratio': 0.2,
            'total_recommendations_ratio': 0.2,
            'avg_recommendations_ratio': 0.1
        }

    def should_use_concurrent(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            estimated_tokens: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """决定是否使用并发处理"""

        scenario_count = len(confirmed_scenarios)
        total_recommendations = sum(
            len(scenario.get('recommendations', []))
            for scenario in confirmed_scenarios
        )
        avg_recommendations = total_recommendations / max(scenario_count, 1)

        # 计算各维度比率
        token_ratio = estimated_tokens / self.threshold_config['token_threshold']
        scenario_ratio = scenario_count / self.threshold_config['max_scenarios_single_call']
        total_rec_ratio = total_recommendations / self.threshold_config['max_total_recommendations']
        avg_rec_ratio = avg_recommendations / self.threshold_config['max_avg_recommendations_per_scenario']

        # 计算综合评分
        composite_score = (
                token_ratio * self.weights['token_ratio'] +
                scenario_ratio * self.weights['scenario_ratio'] +
                total_rec_ratio * self.weights['total_recommendations_ratio'] +
                avg_rec_ratio * self.weights['avg_recommendations_ratio']
        )

        # 硬性条件
        hard_conditions = [
            token_ratio > 1.0,
            scenario_ratio > 1.5,
            total_rec_ratio > 2.0,
            avg_rec_ratio > 1.8
        ]

        use_concurrent = composite_score > 1.0 or any(hard_conditions)

        decision_metrics = {
            'composite_score': composite_score,
            'dimensions': {
                'tokens': {
                    'value': estimated_tokens,
                    'threshold': self.threshold_config['token_threshold'],
                    'ratio': token_ratio
                },
                'scenarios': {
                    'value': scenario_count,
                    'threshold': self.threshold_config['max_scenarios_single_call'],
                    'ratio': scenario_ratio
                },
                'total_recommendations': {
                    'value': total_recommendations,
                    'threshold': self.threshold_config['max_total_recommendations'],
                    'ratio': total_rec_ratio
                },
                'avg_recommendations': {
                    'value': avg_recommendations,
                    'threshold': self.threshold_config['max_avg_recommendations_per_scenario'],
                    'ratio': avg_rec_ratio
                }
            },
            'hard_conditions_triggered': [
                'token_exceeded' if token_ratio > 1.0 else None,
                'scenarios_exceeded' if scenario_ratio > 1.5 else None,
                'total_recommendations_exceeded' if total_rec_ratio > 2.0 else None,
                'avg_recommendations_exceeded' if avg_rec_ratio > 1.8 else None
            ],
            'decision_reason': self._get_decision_reason(composite_score, hard_conditions)
        }

        return use_concurrent, decision_metrics

    def _get_decision_reason(self, composite_score: float, hard_conditions: List[bool]) -> str:
        """生成决策理由"""
        if composite_score > 1.0:
            return f"综合评分{composite_score:.2f}超过阈值1.0"

        triggered = [cond for cond in hard_conditions if cond]
        if triggered:
            return f"触发{len(triggered)}个硬性条件"

        return f"综合评分{composite_score:.2f}未超过阈值"


class LearningThresholdStrategy(AdaptiveThresholdStrategy):
    """基于历史性能学习的阈值策略"""

    def __init__(self):
        super().__init__()
        self.performance_history = []
        self.learning_enabled = True

    def update_based_on_performance(
            self,
            decision_metrics: Dict[str, Any],
            actual_processing_time: float,
            success: bool,
            strategy_used: str
    ):
        """根据实际性能更新阈值"""
        if not self.learning_enabled:
            return

        record = {
            'decision_metrics': decision_metrics,
            'processing_time': actual_processing_time,
            'success': success,
            'strategy_used': strategy_used,
            'timestamp': time.time()
        }

        self.performance_history.append(record)

        # 保留最近100条记录
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

        # 定期调整阈值
        if len(self.performance_history) % 20 == 0:
            self._adjust_thresholds_based_on_history()

    def _adjust_thresholds_based_on_history(self):
        """基于历史性能调整阈值"""
        single_call_records = [r for r in self.performance_history if r['strategy_used'] == 'single']
        concurrent_records = [r for r in self.performance_history if r['strategy_used'] == 'concurrent']

        if len(single_call_records) < 5 or len(concurrent_records) < 5:
            return

        # 计算平均处理时间
        try:
            avg_single_time = sum(r['processing_time'] for r in single_call_records) / len(single_call_records)
            avg_concurrent_time = sum(r['processing_time'] for r in concurrent_records) / len(concurrent_records)

            # 计算成功率
            single_success_rate = sum(1 for r in single_call_records if r['success']) / len(single_call_records)
            concurrent_success_rate = sum(1 for r in concurrent_records if r['success']) / len(concurrent_records)

            # 根据性能差异调整阈值
            time_ratio = avg_single_time / avg_concurrent_time if avg_concurrent_time > 0 else 1.0
            success_ratio = single_success_rate / concurrent_success_rate if concurrent_success_rate > 0 else 1.0

            # 如果单次调用性能更好，适当提高阈值
            if time_ratio < 0.8 and success_ratio > 0.9:
                self.threshold_config['token_threshold'] = min(
                    self.threshold_config['token_threshold'] * 1.1,
                    8000
                )
                logger.info(f"📈 基于性能数据提高token阈值至: {self.threshold_config['token_threshold']}")

            # 如果并发调用性能更好，适当降低阈值
            elif time_ratio > 1.2 or success_ratio < 0.8:
                self.threshold_config['token_threshold'] = max(
                    self.threshold_config['token_threshold'] * 0.9,
                    2000
                )
                logger.info(f"📉 基于性能数据降低token阈值至: {self.threshold_config['token_threshold']}")
        except Exception as e:
            logger.warning(f"调整阈值时出错: {e}")
class AdaptiveReranker(BasePrompt):
    """自适应推荐引擎"""

    def __init__(self, environment: str = "production", use_adaptive: bool = True):
        super().__init__()
        self.environment = environment
        self.use_adaptive = use_adaptive


        # 初始化策略
        if use_adaptive:
            self.strategy = LearningThresholdStrategy()
            logger.info("🔄 启用自适应策略")
        else:
            self.strategy = AdaptiveThresholdStrategy()
            logger.info("⚡ 使用固定阈值策略")

        self._initialize_strategy()

    def _initialize_strategy(self):
        """初始化策略配置"""
        env_config = self.get_environment_specific_config(self.environment)
        self.strategy.threshold_config.update(env_config)
        logger.info(f"✅ 策略初始化完成，环境: {self.environment}")
    def get_environment_specific_config(self, environment: str) -> Dict[str, Any]:
        """获取环境特定配置"""
        configs = {
            'development': {
                'token_threshold': 4000,
                'max_scenarios_single_call': 3,
                'max_total_recommendations': 20,
                'max_avg_recommendations_per_scenario': 6,
            },
            'production': {
                'token_threshold': 4000,
                'max_scenarios_single_call': 5,
                'max_total_recommendations': 30,
                'max_avg_recommendations_per_scenario': 10,
            },
            'local-qwen': {
                'token_threshold': 4000,
                'max_scenarios_single_call': 4,
                'max_total_recommendations': 25,
                'max_avg_recommendations_per_scenario': 7,
            }
        }
        return configs.get(environment, configs['production'])

    def estimate_tokens_with_tiktoken(self, text: str, model_name: str = "cl100k_base") -> int:
        """使用tiktoken计算token数量"""
        try:
            try:
                return len(self.tokenizer.encode(text))
            except KeyError:
                import qwen_token_counter
                encoding = qwen_token_counter.get_token_count(text)
                return encoding
        except ImportError:
            logger.warning("tiktoken未安装，使用回退估算方法")
            return self._estimate_tokens_fallback(text)

    def _estimate_tokens_fallback(self, text: str) -> int:
        """tiktoken不可用时的回退估算方法"""
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        numbers = len(re.findall(r'\d+', text))
        punctuation = len(re.findall(r'[^\w\s\u4e00-\u9fff]', text))
        spaces = len(re.findall(r'\s', text))

        estimated_tokens = (
                chinese_chars * 2.3 +
                english_words * 1.3 +
                numbers * 0.8 +
                punctuation * 0.5 +
                spaces * 0.1
        )
        return int(estimated_tokens)

    def _build_single_call_prompt(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_scenarios:int,
            max_recommendations_per_scenario: int,
            direct_return: bool,

    ) -> str:
        """构建单次调用提示词"""

        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)
        scenarios_content = self.build_scenarios_with_recommend(confirmed_scenarios)
        task_instruction = self.build_task_instruction(
            max_scenarios, max_recommendations_per_scenario, direct_return
        )

        return f"{patient_info_content}\n{clinical_context_content}\n{scenarios_content}\n{task_instruction}"

    async def get_recommendations(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_scenarios:int=3,
            max_recommendations_per_scenario: int = 3,
            direct_return:bool=False,
            use_adaptive: Optional[bool] = None,  # 可覆盖初始设置
            max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """主入口函数 - 获取推荐结果"""

        # 确定是否使用自适应策略
        adaptive_mode = use_adaptive if use_adaptive is not None else self.use_adaptive
        # 1. 计算token数
        single_prompt = self._build_single_call_prompt(
            confirmed_scenarios,
            patient_info,
            clinical_context,
            max_scenarios,
            max_recommendations_per_scenario,
            direct_return
        )



        if adaptive_mode:
            return await self._get_recommendations_adaptive(
                confirmed_scenarios, patient_info, clinical_context,
                max_recommendations_per_scenario, max_concurrent,single_prompt,direct_return
            )
        else:
            # 非自适应模式，默认使用单次调用
            return await self._get_recommendations_single_call(
                confirmed_scenarios, patient_info, clinical_context,
                max_recommendations_per_scenario, len(confirmed_scenarios),single_prompt,direct_return
            )
    async def _get_recommendations_adaptive(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int,
            max_concurrent: int,
            single_prompt: str,
            direct_return:bool,
    ) -> List[Dict[str, Any]]:
        """自适应模式处理"""

        start_time = time.time()
        estimated_tokens = self.estimate_tokens_with_tiktoken(single_prompt)
        if not direct_return:
            # 2. 使用策略决策
            use_concurrent, decision_metrics = self.strategy.should_use_concurrent(
                confirmed_scenarios, estimated_tokens
            )

            # 3. 记录决策详情
            self._log_decision_metrics(decision_metrics, estimated_tokens)

            # 4. 执行相应策略并记录性能
            try:
                if use_concurrent:
                    logger.info("⚡ 使用并发处理策略")
                    results = await self._get_recommendations_for_confirmed_scenarios_concurrent(
                        confirmed_scenarios, patient_info, clinical_context,
                        max_recommendations_per_scenario, max_concurrent
                    )
                    strategy_used = 'concurrent'
                else:
                    logger.info("🔄 使用单次调用策略")
                    results = await self._get_recommendations_single_call(
                        confirmed_scenarios, patient_info, clinical_context,
                        max_recommendations_per_scenario, len(confirmed_scenarios),single_prompt
                    )
                    strategy_used = 'single'

                processing_time = time.time() - start_time
                success = True

            except Exception as e:
                logger.error(f"处理失败: {str(e)}")
                processing_time = time.time() - start_time
                results = self._fallback_for_confirmed_scenarios(confirmed_scenarios)
                success = False
                strategy_used = 'single' if not use_concurrent else 'concurrent'

            # 5. 如果是学习策略，更新性能数据
            if isinstance(self.strategy, LearningThresholdStrategy):
                self.strategy.update_based_on_performance(
                    decision_metrics=decision_metrics,
                    actual_processing_time=processing_time,
                    success=success,
                    strategy_used=strategy_used
                )

            return results
        else:
             total_token=self.strategy.threshold_config["token_threshold"]
             if total_token-1500<estimated_tokens:
                 #重新规整现有数据结构重新构成提示词
                 results = await self._get_recommendations_single_call(
                     confirmed_scenarios, patient_info, clinical_context,
                     max_recommendations_per_scenario, len(confirmed_scenarios), single_prompt,direct_return
                 )
                 return results
             else:
                 # 2. 使用策略决策
                 use_concurrent, decision_metrics = self.strategy.should_use_concurrent(
                     confirmed_scenarios, estimated_tokens
                 )

                 # 3. 记录决策详情
                 self._log_decision_metrics(decision_metrics, estimated_tokens)

                 # 4. 执行相应策略并记录性能
                 try:
                     if use_concurrent:
                         logger.info("⚡ 使用并发处理策略")
                         results = await self._get_recommendations_for_confirmed_scenarios_concurrent(
                             confirmed_scenarios, patient_info, clinical_context,
                             max_recommendations_per_scenario, max_concurrent
                         )
                         strategy_used = 'concurrent'
                     else:
                         logger.info("🔄 使用单次调用策略")
                         results = await self._get_recommendations_single_call(
                             confirmed_scenarios, patient_info, clinical_context,
                             max_recommendations_per_scenario, len(confirmed_scenarios), single_prompt
                         )
                         strategy_used = 'single'

                     processing_time = time.time() - start_time
                     success = True

                 except Exception as e:
                     logger.error(f"处理失败: {str(e)}")
                     processing_time = time.time() - start_time
                     results = self._fallback_for_confirmed_scenarios(confirmed_scenarios)
                     success = False
                     strategy_used = 'single' if not use_concurrent else 'concurrent'

                 # 5. 如果是学习策略，更新性能数据
                 if isinstance(self.strategy, LearningThresholdStrategy):
                     self.strategy.update_based_on_performance(
                         decision_metrics=decision_metrics,
                         actual_processing_time=processing_time,
                         success=success,
                         strategy_used=strategy_used
                     )

                 return results
    def _log_decision_metrics(self, decision_metrics: Dict[str, Any], estimated_tokens: int):
        """记录决策指标"""
        metrics = decision_metrics['dimensions']

        logger.info("📊 决策分析:")
        logger.info(
            f"  Token数: {estimated_tokens}/{metrics['tokens']['threshold']} ({metrics['tokens']['ratio'] * 100:.1f}%)")
        logger.info(
            f"  场景数: {metrics['scenarios']['value']}/{metrics['scenarios']['threshold']} ({metrics['scenarios']['ratio'] * 100:.1f}%)")
        logger.info(
            f"  总推荐数: {metrics['total_recommendations']['value']}/{metrics['total_recommendations']['threshold']} ({metrics['total_recommendations']['ratio'] * 100:.1f}%)")
        logger.info(
            f"  平均推荐数: {metrics['avg_recommendations']['value']:.1f}/{metrics['avg_recommendations']['threshold']} ({metrics['avg_recommendations']['ratio'] * 100:.1f}%)")
        logger.info(f"  综合评分: {decision_metrics['composite_score']:.2f}")
        logger.info(f"  决策理由: {decision_metrics['decision_reason']}")


    async def _get_recommendations_for_confirmed_scenarios_concurrent(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int,
            max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """并发处理"""
        """并发处理已确认场景的推荐项目分级
    
            Args:
                confirmed_scenarios: 已确认的场景列表
                patient_info: 患者信息
                clinical_context: 临床上下文
                max_recommendations_per_scenario: 每个场景最大推荐项目数
                max_concurrent: 最大并发数
    
            Returns:
                格式化的推荐结果，与原函数格式相同
            """
        import asyncio
        from typing import List, Dict, Any

        async def process_single_scenario(scenario_data: Dict[str, Any], scenario_index: int) -> Dict[str, Any]:
            """处理单个场景的推荐项目分级"""
            try:
                # 构建单个场景的提示词
                prompt = self._build_single_scenario_prompt(
                    scenario_data,
                    scenario_index,
                    patient_info,
                    clinical_context,
                    max_recommendations_per_scenario
                )

                # 调用LLM
                response = await self.ai_service._call_llm(prompt)

                # 解析JSON结果
                import re
                import json

                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    logger.error(f"场景{scenario_index} LLM返回格式错误，使用降级方案")
                    return self._fallback_single_scenario(scenario_data, scenario_index)

                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    logger.error(f"场景{scenario_index} JSON解析错误: {e}")
                    return self._fallback_single_scenario(scenario_data, scenario_index)

                # 处理分级推荐结果
                return self._process_single_scenario_result(result, scenario_data, scenario_index,
                                                            max_recommendations_per_scenario)

            except Exception as e:
                logger.error(f"处理场景{scenario_index}时发生错误: {str(e)}")
                return self._fallback_single_scenario(scenario_data, scenario_index)

        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_process(scenario_data, scenario_index):
            async with semaphore:
                return await process_single_scenario(scenario_data, scenario_index)

        # 并发处理所有场景
        tasks = [
            bounded_process(scenario_data, idx + 1)
            for idx, scenario_data in enumerate(confirmed_scenarios)
        ]

        single_scenario_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        final_results = []
        for result in single_scenario_results:
            if isinstance(result, Exception):
                logger.error(f"场景处理异常: {result}")
                continue
            if result:  # 只添加有效结果
                final_choices=result.get("final_choices",[])
                if not final_choices:
                    procedures=result.get('graded_recommendations')["highly_recommended"]
                    res=[ p['procedure_details']['name_zh'] for p in procedures]
                    final_choices=res
                final_results.append(final_choices)

        # 按综合评分排序

        # 生成总体推理
        res =await self._generate_overall_reasoning(patient_info,clinical_context,max_recommendations_per_scenario,final_results)

        # 为所有结果添加总体推理


        # 记录详细的分级统计
        logger.info(f"✅ 并发场景推荐分级完成，处理了{len(final_results)}个场景")


        return res
    def _build_single_scenario_prompt(
            self,
            scenario_data: Dict[str, Any],
            scenario_index: int,
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int
    ) -> str:
        """为单个场景构建提示词"""

        scenario = scenario_data['scenario']
        recommendations = scenario_data.get('recommendations', [])

        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)
        scenario_content = self._build_single_scenario_content(scenario_data, scenario_index)
        task_instruction = self._build_single_scenario_task_instruction(
            scenario_index,
            len(recommendations),
            max_recommendations_per_scenario
        )

        return f"""{patient_info_content}

        {clinical_context_content}

        {scenario_content}

        {task_instruction}"""
    async def _get_recommendations_single_call(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int,
            expected_scenario_count: int,
            single_prompt: str,
            direct_return:bool=False
    ) -> List[Dict[str, Any]]:
        """单次调用处理"""
        # 这里实现单次LLM调用逻辑
        # 返回格式化的结果
        # 2. 根据token数选择策略
        return await self._get_recommendations_single_call_by_llm(
                confirmed_scenarios,single_prompt,direct_return
            )
    async def _get_recommendations_single_call_by_llm(self, confirmed_scenarios,
                                                       single_prompt,direct_return):

            try:

                response = await self.ai_service._call_llm(single_prompt)

                if not direct_return:


                    # 使用增强的JSON解析
                    result = safe_parse_llm_response(response=response, expected_scenario_count=len(confirmed_scenarios))

                    if result is None:
                        logger.error("JSON解析失败，使用降级方案")
                        return self._fallback_for_confirmed_scenarios(confirmed_scenarios)

                    # 处理选中的场景数据
                    selected_scenarios_data = result.get('selected_scenarios', [])
                    final_results = []

                    for selected_data in selected_scenarios_data:
                        scenario_index = selected_data.get('scenario_index')
                        scenario_id = selected_data.get('scenario_id')
                        grading_data = selected_data.get('recommendation_grades', {})
                        final_choices=selected_data.get("final_choices",[])
                        # 验证场景索引范围
                        if not (1 <= scenario_index <= len(confirmed_scenarios)):
                            logger.warning(f"无效的场景索引: {scenario_index}，跳过该场景")
                            continue

                        # 获取原始场景数据
                        original_scenario_data = confirmed_scenarios[scenario_index - 1]
                        original_recommendations = original_scenario_data.get('recommendations', [])
                        scenario = original_scenario_data['scenario']

                        # 安全处理推荐分级
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
                            "final_choices":final_choices,
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

                    logger.info(f"✅ 单次调用完成，成功处理{len(final_results)}个场景")
                    return final_results
                else:
                    return response
            except Exception as e:
                logger.error(f"❌ 单次调用失败: {str(e)}")
                if not direct_return:
                    return self._fallback_for_confirmed_scenarios(confirmed_scenarios)
                return "执行出错"
    def _fallback_for_confirmed_scenarios(self, confirmed_scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """降级方案"""
        logger.info("使用降级方案...")
        return []
    async def _generate_overall_reasoning(self,
                                    patient_info,
                                    clinical_context,
                                    max_recommendations_per_scenario,
                                    final_results: List[Dict[str, Any]]) :
        """生成总体推理说明"""
        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)
        choices_content=""
        a=[]
        for choices in final_results:
            if isinstance(choices,list) and choices:
                a.extend(choices)
        choices_content="\n".join(a)
        task_content = f"""
                          你是一个专业的医学影像专家，请你根据提供给你的医学影像推荐项目以及患者的信息和临床上下文，选择{max_recommendations_per_scenario}个最适合该病人的医学影像推荐项目
                          这是患者的信息：
                                 {patient_info_content}
                          这是临床上下文：
                                 {clinical_context_content}
                          这是对应的医学影像推荐：
                                  {choices_content}               

                          请你务必选择{max_recommendations_per_scenario}个推荐项目。
                          这是输出格式
                          {{
                             "final_choices":[这里是选择的{max_recommendations_per_scenario}个医学影像推荐项目]
                             "overall_reason":..

                          }}
                          务必以json格式输出！


                """
        response = await self.ai_service._call_llm(task_content)
        try:
            res=safe_parse_llm_response(response)
        except Exception as e:
            logger.info(f"解析json出错：{e}")

        choices=res.get("final_choices",[])
        reason=res.get( "overall_reason","")
        return [{"final_choices":choices,"overall_reason":reason}]





    def _fallback_single_scenario(
            self,
            scenario_data: Dict[str, Any],
            scenario_index: int,
            top_k: int = 3  # 新增top_k参数
    ) -> Dict[str, Any]:
        """单个场景处理的降级方案"""

        scenario = scenario_data['scenario']
        original_recommendations = scenario_data.get('recommendations', [])

        # 构建空的推荐分级
        graded_recommendations = {
            "highly_recommended": [],
            "recommended": [],
            "less_recommended": []
        }

        # 将所有推荐项目标记为"推荐"作为降级方案
        for rec_data in original_recommendations:
            rec_copy = rec_data.copy()
            rec_copy['recommendation_level'] = 'recommended'
            rec_copy['recommendation_level_zh'] = '推荐'

            # 添加详细信息的降级处理
            procedure = rec_copy['procedure']
            recommendation = rec_copy['recommendation']

            rec_copy['procedure_details'] = {
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

            rec_copy['recommendation_details'] = {
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

            graded_recommendations['recommended'].append(rec_copy)

        # 构建 final_choices 降级方案，选择前top_k个
        final_choices = []
        if original_recommendations:
            # 选择前top_k个推荐项目作为最终选择
            selected_count = min(top_k, len(original_recommendations))
            final_choices = [original_recommendations[i]['procedure'].name_zh
                             for i in range(selected_count)]

        return {
            'comprehensive_score': 50,  # 默认中等评分
            'scenario_reasoning': '系统降级处理：无法获取详细分析',
            'grading_reasoning': '系统降级处理：所有推荐项目标记为推荐级别',
            'overall_reasoning': '',
            'graded_recommendations': graded_recommendations,
            'recommendation_summary': {
                'highly_recommended_count': 0,
                'recommended_count': len(original_recommendations),
                'less_recommended_count': 0,
                'total_recommendations': len(original_recommendations)
            },
            'final_choices': final_choices,
            'scenario_metadata': {
                'scenario_id': scenario.semantic_id,
                'description': scenario.description_zh,
                'panel': scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知',
                'patient_population': scenario.patient_population,
                'clinical_context': scenario.clinical_context,
                'original_index': scenario_index
            }
        }
    def _process_single_scenario_result(
            self,
            result: Dict[str, Any],
            scenario_data: Dict[str, Any],
            scenario_index: int,
            top_k: int = 3  # 新增 top_k 参数，默认选择前3个
    ) -> Dict[str, Any]:
        """处理单个场景的LLM返回结果"""

        scenario = scenario_data['scenario']
        original_recommendations = scenario_data.get('recommendations', [])
        grading_data = result.get('recommendation_grades', {})

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

        # 获取 final_choices，按优先级顺序选择 top_k 个项目
        final_choices = []

        # 方法1: 如果LLM返回了final_choices，使用它（但限制数量）
        llm_final_choices = result.get('final_choices', [])
        if llm_final_choices:
            final_choices = llm_final_choices[:top_k]  # 限制为top_k个
        else:
            # 方法2: 降级方案 - 按推荐等级优先级选择top_k个项目
            selected_recommendations = []

            # 优先选择极其推荐的项目
            if graded_recommendations['highly_recommended']:
                selected_count = min(top_k, len(graded_recommendations['highly_recommended']))
                selected_recommendations.extend(graded_recommendations['highly_recommended'][:selected_count])

            # 如果还不够，补充推荐的项目
            if len(selected_recommendations) < top_k and graded_recommendations['recommended']:
                remaining_slots = top_k - len(selected_recommendations)
                additional_count = min(remaining_slots, len(graded_recommendations['recommended']))
                selected_recommendations.extend(graded_recommendations['recommended'][:additional_count])

            # 如果还不够，补充不太推荐的项目（通常不推荐，但作为备选）
            if len(selected_recommendations) < top_k and graded_recommendations['less_recommended']:
                remaining_slots = top_k - len(selected_recommendations)
                additional_count = min(remaining_slots, len(graded_recommendations['less_recommended']))
                selected_recommendations.extend(graded_recommendations['less_recommended'][:additional_count])

            # 提取检查项目名称
            final_choices = [rec['procedure_details']['name_zh'] for rec in selected_recommendations]

            # 如果没有选择任何项目，添加提示
            if not final_choices:
                final_choices = ["无合适推荐项目"]

        # 构建返回结果 - 统一格式
        return {
            'comprehensive_score': result.get('comprehensive_score', 0),
            'scenario_reasoning': result.get('scenario_reasoning', ''),
            'grading_reasoning': result.get('grading_reasoning', ''),
            'overall_reasoning': '',  # 将在外层统一设置
            'graded_recommendations': graded_recommendations,
            'recommendation_summary': {
                'highly_recommended_count': len(graded_recommendations['highly_recommended']),
                'recommended_count': len(graded_recommendations['recommended']),
                'less_recommended_count': len(graded_recommendations['less_recommended']),
                'total_recommendations': len(original_recommendations)
            },
            'final_choices': final_choices,  # 现在包含最多top_k个项目
            'scenario_metadata': {
                'scenario_id': result.get('scenario_id') or scenario.semantic_id,
                'description': scenario.description_zh,
                'panel': scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知',
                'patient_population': scenario.patient_population,
                'clinical_context': scenario.clinical_context,
                'original_index': scenario_index
            }
        }

