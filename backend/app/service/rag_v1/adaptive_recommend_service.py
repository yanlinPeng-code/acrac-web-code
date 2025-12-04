
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
import dashscope
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v1.ai_service import AiService
from app.utils.helper.helper import safe_parse_llm_response, safe_process_recommendation_grades

# 设置日志
logger = logging.getLogger(__name__)




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


class AdaptiveRecommendationEngineService:
    """自适应推荐引擎"""

    def __init__(self, environment: str = "production", use_adaptive: bool = True):
        self.environment = environment
        self.use_adaptive = use_adaptive
        self.tokenizer=dashscope.get_tokenizer("qwen-7b-chat")
        self.ai_service = AiService()


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
                'token_threshold': 4096,
                'max_scenarios_single_call': 3,
                'max_total_recommendations': 20,
                'max_avg_recommendations_per_scenario': 6,
            },
            'production': {
                'token_threshold': 4096,
                'max_scenarios_single_call': 5,
                'max_total_recommendations': 50,
                'max_avg_recommendations_per_scenario': 10,
            },
            'local-qwen': {
                'token_threshold': 4096,
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
            max_recommendations_per_scenario: int,
            direct_return:bool,

    ) -> str:
        """构建单次调用提示词"""

        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)
        scenarios_content = self._build_optimized_scenarios_content(confirmed_scenarios)
        task_instruction = self._build_optimized_task_instruction(
            len(confirmed_scenarios), max_recommendations_per_scenario,direct_return
        )

        return f"{patient_info_content}\n{clinical_context_content}\n{scenarios_content}\n{task_instruction}"

    def build_patient_context(self, patient_info: PatientInfo) -> str:
          """构建患者信息"""
          # 患者和临床信息
          patient_context = f"""
             ## 患者基本信息
             - **年龄**: {patient_info.age}岁
             - **性别**: {patient_info.gender}
             - **妊娠状态**: {patient_info.pregnancy_status or '非妊娠期'}
             - **过敏史**: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
             - **合并症**: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
            """
          return patient_context

    def build_clinical_context(self, clinical_context: ClinicalContext) -> str:
        """构建临床上下文（示例实现）"""
        ## 临床上下文
        clinical_context_content = f"""
                   ### 临床信息
                   - **就诊科室**: {clinical_context.department}
                   - **主诉**: {clinical_context.chief_complaint}
                   - **既往病史**: {clinical_context.medical_history or '无'}
                   - **现病史**: {clinical_context.present_illness or '无'}
                   - **主诊断**: {clinical_context.diagnosis or '待诊断'}
                   - **症状严重程度**: {clinical_context.symptom_severity or '未知'}
                   - **症状持续时间**: {clinical_context.symptom_duration or '未知'}
                   """
        return clinical_context_content

    def _build_optimized_scenarios_content(self, confirmed_scenarios: List[Dict[str, Any]]) -> str:
        """构建优化的场景内容"""
        # 所有场景和推荐项目（利用完整字段信息）
        scenarios_text = "## 可选临床场景及推荐项目\n\n"

        for scenario_idx, scenario_data in enumerate(confirmed_scenarios, 1):
            scenario = scenario_data['scenario']
            recommendations = scenario_data.get('recommendations', [])

            scenarios_text += f"### 场景{scenario_idx}: {scenario.description_zh}\n"
            scenarios_text += f"- **场景ID**: {scenario.semantic_id}\n"
            scenarios_text += f"- **适用科室**: {scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知'}\n"
            scenarios_text += f"- **适用人群**: {scenario.patient_population or '未知'}\n"
            scenarios_text += f"- **临床背景**: {scenario.clinical_context or '无'}\n\n"

            if not recommendations:
                scenarios_text += "  暂无推荐项目\n\n"
                continue

            scenarios_text += "#### 推荐项目清单:\n"
            for rec_idx, rec_data in enumerate(recommendations, 1):
                recommendation = rec_data['recommendation']
                procedure = rec_data['procedure']

                # 检查项目基本信息
                scenarios_text += f"{rec_idx}. **{procedure.name_zh}** ({procedure.name_en})\n"

                # 检查技术细节
                tech_details = []
                if procedure.modality:
                    tech_details.append(f"检查方式: {procedure.modality}")
                if procedure.body_part:
                    tech_details.append(f"检查部位: {procedure.body_part}")
                # if procedure.exam_duration:
                #     tech_details.append(f"检查时长: {procedure.exam_duration}分钟")
                # if tech_details:
                #     scenarios_text += f"   - 技术细节: {', '.join(tech_details)}\n"

                # 安全性和准备信息
                safety_info = []
                if procedure.contrast_used:
                    safety_info.append("使用对比剂")
                if procedure.radiation_level:
                    safety_info.append(f"辐射等级: {procedure.radiation_level}")
                # if procedure.preparation_required:
                #     safety_info.append("需要准备")
                if safety_info:
                    scenarios_text += f"   - 安全信息: {', '.join(safety_info)}\n"

                # ACR推荐信息
                scenarios_text += f"   - **ACR适宜性评分**: {recommendation.appropriateness_rating}/9\n"
                if recommendation.appropriateness_category_zh:
                    scenarios_text += f"   - 适宜性类别: {recommendation.appropriateness_category_zh}\n"

                # 证据和共识
                evidence_info = []
                if recommendation.evidence_level:
                    evidence_info.append(f"证据强度: {recommendation.evidence_level}")
                # if recommendation.consensus_level:
                #     evidence_info.append(f"共识水平: {recommendation.consensus_level}")
                # if recommendation.median_rating:
                #     evidence_info.append(f"中位数评分: {recommendation.median_rating}")
                # if evidence_info:
                #     scenarios_text += f"   - 证据质量: {', '.join(evidence_info)}\n"

                # 辐射剂量信息
                dose_info = []
                if recommendation.adult_radiation_dose:
                    dose_info.append(f"成人剂量: {recommendation.adult_radiation_dose}")
                if recommendation.pediatric_radiation_dose:
                    dose_info.append(f"儿童剂量: {recommendation.pediatric_radiation_dose}")
                if dose_info:
                    scenarios_text += f"   - 辐射剂量: {', '.join(dose_info)}\n"

                # 安全性信息
                safety_info = []
                if recommendation.pregnancy_safety:
                    safety_info.append(f"妊娠安全: {recommendation.pregnancy_safety}")
                if recommendation.contraindications:
                    contra = recommendation.contraindications[:50] + "..." if len(
                        recommendation.contraindications) > 50 else recommendation.contraindications
                    safety_info.append(f"禁忌症: {contra}")
                if safety_info:
                    scenarios_text += f"   - 安全考虑: {', '.join(safety_info)}\n"

                # 推荐理由
                # if recommendation.reasoning_zh:
                #     reasoning = recommendation.reasoning_zh[:80] + "..." if len(
                #         recommendation.reasoning_zh) > 80 else recommendation.reasoning_zh
                #     scenarios_text += f"   - 推荐理由: {reasoning}\n"


                if recommendation.special_considerations:
                    special = recommendation.special_considerations[:80] + "..." if len(
                        recommendation.special_considerations) > 80 else recommendation.special_considerations
                    scenarios_text += f"   - 特殊考虑: {special}\n"

                # 标准编码（如有）
                # code_info = []
                # if procedure.standard_code:
                #     code_info.append(f"标准码: {procedure.standard_code}")
                # if procedure.icd10_code:
                #     code_info.append(f"ICD10: {procedure.icd10_code}")
                # if procedure.cpt_code:
                #     code_info.append(f"CPT: {procedure.cpt_code}")
                # if code_info:
                #     scenarios_text += f"   - 标准编码: {', '.join(code_info)}\n"

                scenarios_text += "\n"

            scenarios_text += "---\n\n"
        return scenarios_text

    def _build_optimized_task_instruction(self, scenario_count: int, max_recommendations_per_scenario: int,direct_return:bool) -> str:
        """构建优化的任务指令"""
        prompt=f"""
              ## 任务说明
    
              基于患者信息和临床上下文，对{scenario_count}个已确认临床场景的所有推荐项目进行**三级推荐等级划分**。
    
              ### 分级标准
                      - **极其推荐 (Highly Recommended)**: 评分高，证据充分，与患者情况完美匹配，安全性和诊断价值俱佳，无明显禁忌
                      - **推荐 (Recommended)**: 评分中等，临床适用性良好，风险收益比合理，可能存在轻微限制
                      - **不太推荐 (Less Recommended)**: 评分低，或存在安全隐患，或有明确禁忌症，或与当前临床需求匹配度不高
              ##注意
                  - 每个场景的最终推荐项目必须为{max_recommendations_per_scenario}个。
                  - 每个场景你都要做推荐的评级，不能掠过。
              ### 输出格式
              {{
                  "selected_scenarios": [
                      {{
                          "scenario_index": 这里是索引id(例如：1),
                          "scenario_id": "场景语义ID",
                          "comprehensive_score": "0-100综合评分",
                          "scenario_reasoning": "场景匹配度分析",
                          "recommendation_grades": {{
                              "highly_recommended": [1, 3],
                              "recommended": [2, 4],
                              "less_recommended": [5]
                          }},
                          "grading_reasoning": "分级临床理由"
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
                          "grading_reasoning": "分级临床理由"
                      }},
                  ],
                  "overall_choices":[这是总体的选择项目，注意！填推荐项目的名字,要求你综合性的考量之后，选择最符合患者信息和临床场景的推荐项目！必须为{max_recommendations_per_scenario}个]
                  "overall_reasoning": "总体策略说明"
              }}
              **重要：请只输出纯JSON格式，不要包含任何其他文字、说明或Markdown标记！确保JSON格式完全正确。**
              """

        if not direct_return:
            return  prompt




        else:
            return f"""
            ## 任务说明
            基于患者信息与临床上下文，以及给定的场景下可供选择的推荐项目，直接给出最终推荐及其原因。
    
            ### 输出要求（纯文本，中文）
            - 仅输出文本，不要JSON或其他标记，不要包含额外的解释性段落。
            - 
              1) 先输出“推荐项目”：列出最适合患者信息和临床上下文{max_recommendations_per_scenario} 个项目，按优先级从高到低，仅写项目名称，用顿号或逗号分隔。
              2) 再输出“推荐理由”：简要说明选择依据，结合患者与场景信息，语言精炼。
            - 严格遵守“先推荐项目，再推荐理由”的顺序。
    
            ### 文本示例（示意）：
            推荐项目：项目A，项目B，项目C
            推荐理由：……
            """

    async def get_recommendations(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int = 10,
            direct_return:bool=False,
            use_adaptive: Optional[bool] = None,  # 可覆盖初始设置
            max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """主入口函数 - 获取推荐结果"""

        # 确定是否使用自适应策略
        adaptive_mode = use_adaptive if use_adaptive is not None else self.use_adaptive
        # 1. 计算token数
        single_prompt = self._build_single_call_prompt(
            confirmed_scenarios, patient_info, clinical_context, max_recommendations_per_scenario,direct_return
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
                 prompt=self._build_comprehensive_prompt_with_grading(confirmed_scenarios,patient_info,clinical_context,direct_return,len(confirmed_scenarios),max_recommendations_per_scenario)
                 results = await self._get_recommendations_single_call(
                     confirmed_scenarios, patient_info, clinical_context,
                     max_recommendations_per_scenario, len(confirmed_scenarios),  prompt,direct_return
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




    def _build_comprehensive_prompt_with_grading(
                         self,
                         all_scenarios: List[Dict[str, Any]],
                         patient_info: PatientInfo,
                         clinical_context: ClinicalContext,
                         direct_return: bool,
                         max_scenarios: int,
                         max_recommendations_per_scenario: int
                 ) -> str:
                     """构建完整的提示词，确保总token数不超过3600"""
                     # 构建各个部分
                     try:

                         patient_info_content = self.build_patient_context(patient_info)
                         clinical_context_content = self.build_clinical_context(clinical_context)

                         # 计算固定部分的token数
                         fixed_parts = patient_info_content + clinical_context_content
                         fixed_tokens = len(self.tokenizer.encode(fixed_parts))

                         # 为任务指令预留空间（估计约500-800 token）
                         task_reserve_tokens = 900
                         available_scenario_tokens = \
                             self.strategy.threshold_config[
                                 "token_threshold"] - 1500 - fixed_tokens - task_reserve_tokens
                         logger.info(f"可用的提示词token数{available_scenario_tokens}")
                         # 构建场景内容，限制在可用token数内
                         scenarios_content = self.build_scenarios_with_recommend(
                             all_scenarios,
                             patient_info,
                             max_tokens=available_scenario_tokens
                         )

                         # 构建任务指令，使用实际显示的场景数量
                         task_instruction = self.build_task_instruction(
                             direct_return=direct_return,
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
                         total_tokens = len(self.tokenizer.encode(comprehensive_prompt))
                         if total_tokens > self.strategy.threshold_config[
                             "token_threshold"] - 1500:
                             logger.info(f"仍然超出{4096 - 1500 - total_tokens}个token,进行截断")
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
                     except Exception as e:
                         logger.info(f"构建提示词错误：{e}")
                         return ""

    def _truncate_scenarios_further(self, scenarios_content: str, max_tokens: int) -> str:
        """进一步截断场景内容"""
        current_tokens = len(self.tokenizer.encode(scenarios_content))
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
            current_tokens = len(self.tokenizer.encode(scenarios_content))

        return scenarios_content
    def build_scenarios_with_recommend(self, all_scenarios: List[Dict[str, Any]], patient_info: PatientInfo,
                                       max_tokens: int = 2500):
        """构建场景内容，限制在指定token数内"""

        scenarios_text = "## 可选临床场景及推荐项目\n\n"

        # 计算初始token数
        total_tokens = len(self.tokenizer.encode(scenarios_text))
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
            current_scenario_tokens = len(self.tokenizer.encode((current_scenario_text)))

            # 检查添加整个场景后是否会超过限制
            if total_tokens + current_scenario_tokens <= max_tokens:
                scenarios_text += current_scenario_text
                total_tokens += current_scenario_tokens
                scenarios_added += 1
            else:
                # 如果超过限制，添加截断提示并跳出循环
                remaining_scenarios = len(all_scenarios) - scenario_idx
                if remaining_scenarios > 0:
                    logger.info(f"### 场景{scenario_idx}及后续{remaining_scenarios}个场景由于token限制未显示\n")
                    # scenarios_text += f"---\n\n"
                break

        # 添加统计信息
        stats_text = f"\n<!-- 场景部分使用token: {total_tokens}/{max_tokens}, 显示场景: {scenarios_added}/{len(all_scenarios)}, 显示推荐项目: {recommendations_added} -->\n"
        # stats_tokens = qwen_token_counter.get_token_count(stats_text)
        logger.info(stats_text)

        return scenarios_text

    def build_task_instruction(self, direct_return: bool, max_scenarios: int,
                               max_recommendations_per_scenario: int):
        """构建任务指令"""
        if direct_return:
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
                        "grading_reasoning": "分级临床理由"
                              }},
                ],
                "overall_choices":[这是总体的选择项目，注意！填推荐项目的名字,要求你综合性的考量之后，选择最符合患者信息和临床场景的推荐项目！必须为{max_recommendations_per_scenario}个]
                "overall_reasoning": "总体选择策略，重点说明安全性考量和诊断路径"
            }}
             **重要：
                  -请只输出纯JSON格式，不要包含任何其他文字、说明或Markdown标记！确保JSON格式完全正确。**
                  -注意选择的临床场景数一定不能超过{max_scenarios}个！
            """

            return task_instruction
        return f"""
        ## 任务说明
        基于患者信息与临床上下文，以及给定的场景下可供选择的推荐项目，直接给出最终推荐及其原因。

        ### 输出要求（纯文本，中文）
        - 仅输出文本，不要JSON或其他标记，不要包含额外的解释性段落。
        - 
          1) 先输出“推荐项目”：列出最适合患者信息和临床上下文{max_recommendations_per_scenario} 个项目，按优先级从高到低，仅写项目名称，用顿号或逗号分隔。
          2) 再输出“推荐理由”：简要说明选择依据，结合患者与场景信息，语言精炼。
        - 严格遵守“先推荐项目，再推荐理由”的顺序。

        ### 文本示例（示意）：
        推荐项目：项目A，项目B，项目C
        推荐理由：……
        """


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

    async def _get_recommendations_for_confirmed_scenarios_concurrent(
            self,
            confirmed_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_recommendations_per_scenario: int,
            max_concurrent: int=3
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
                return self._process_single_scenario_result(result, scenario_data, scenario_index,max_recommendations_per_scenario)

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
        final_choices=[]
        for result in single_scenario_results:
            if isinstance(result, Exception):
                logger.error(f"场景处理异常: {result}")
                continue
            if result:
                choices = result.get("final_choices", [])
                if not choices:
                    procedures = result.get('graded_recommendations')["highly_recommended"]
                    res = [p['procedure_details']['name_zh'] for p in procedures]
                    final_choices.append(res)
                # 只添加有效结果
                final_results.append(result)

        # 按综合评分排序
        final_results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

        # 生成总体推理
        overall_choices = await self._generate_overall_reasoning(patient_info=patient_info,clinical_context=clinical_context,max_recommendations_per_scenario=max_recommendations_per_scenario,final_results=final_choices)


        res={"result":final_results,"overall_choices":overall_choices.get("final_choices"),"overall_reason":overall_choices.get("overall_reason")}

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

    def _build_single_scenario_content(self, scenario_data: Dict[str, Any], scenario_index: int) -> str:
        """构建单个场景的内容描述"""
        scenario = scenario_data['scenario']
        recommendations = scenario_data.get('recommendations', [])

        content = f"""## 场景 {scenario_index}: {scenario.description_zh}

        ### 场景信息
        - **场景ID**: {scenario.semantic_id}
        - **适用科室**: {scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知'}
        - **适用人群**: {scenario.patient_population or '未知'}
        - **临床背景**: {scenario.clinical_context or '无'}

        ### 推荐项目清单
        """

        if not recommendations:
            content += "暂无推荐项目\n"
            return content

        for rec_idx, rec_data in enumerate(recommendations, 1):
            recommendation = rec_data['recommendation']
            procedure = rec_data['procedure']

            # 检查项目基本信息
            content += f"{rec_idx}. **{procedure.name_zh}** ({procedure.name_en})\n"

            # 检查技术细节
            tech_details = []
            if procedure.modality:
                tech_details.append(f"检查方式: {procedure.modality}")
            if procedure.body_part:
                tech_details.append(f"检查部位: {procedure.body_part}")
            # if procedure.exam_duration:
            #     tech_details.append(f"检查时长: {procedure.exam_duration}分钟")
            # if tech_details:
            #     content += f"   - 技术细节: {', '.join(tech_details)}\n"

            # 安全性和准备信息
            safety_info = []
            if procedure.contrast_used:
                safety_info.append("使用对比剂")
            if procedure.radiation_level:
                safety_info.append(f"辐射等级: {procedure.radiation_level}")
            # if procedure.preparation_required:
            #     safety_info.append("需要准备")
            if safety_info:
                content += f"   - 安全信息: {', '.join(safety_info)}\n"

            # ACR推荐信息
            content += f"   - **ACR适宜性评分**: {recommendation.appropriateness_rating}/9\n"
            if recommendation.appropriateness_category_zh:
                content += f"   - 适宜性类别: {recommendation.appropriateness_category_zh}\n"

            # 证据和共识
            evidence_info = []
            if recommendation.evidence_level:
                evidence_info.append(f"证据强度: {recommendation.evidence_level}")
            # if recommendation.consensus_level:
            #     evidence_info.append(f"共识水平: {recommendation.consensus_level}")
            # if evidence_info:
            #     content += f"   - 证据质量: {', '.join(evidence_info)}\n"

            # 辐射剂量信息
            dose_info = []
            if recommendation.adult_radiation_dose:
                dose_info.append(f"成人剂量: {recommendation.adult_radiation_dose}")
            if recommendation.pediatric_radiation_dose:
                dose_info.append(f"儿童剂量: {recommendation.pediatric_radiation_dose}")
            if dose_info:
                content += f"   - 辐射剂量: {', '.join(dose_info)}\n"

            # 安全性信息
            safety_info = []
            if recommendation.pregnancy_safety:
                safety_info.append(f"妊娠安全: {recommendation.pregnancy_safety}")
            if recommendation.contraindications:
                contra = recommendation.contraindications[:60] + "..." if len(
                    recommendation.contraindications) > 60 else recommendation.contraindications
                safety_info.append(f"禁忌症: {contra}")
            if safety_info:
                content += f"   - 安全考虑: {', '.join(safety_info)}\n"

            # 推荐理由
            if recommendation.reasoning_zh:
                reasoning = recommendation.reasoning_zh[:50] + "..." if len(
                    recommendation.reasoning_zh) > 50 else recommendation.reasoning_zh
                content += f"   - 推荐理由: {reasoning}\n"

            content += "\n"

        return content

    def _build_single_scenario_task_instruction(
            self,
            scenario_index: int,
            recommendation_count: int,
            max_recommendations_per_scenario: int
    ) -> str:
        """为单个场景构建任务指令"""

        task_instruction = f"""
        ## 任务说明

        作为经验丰富的临床医生，请基于患者信息和临床上下文，对**场景{scenario_index}**的{recommendation_count}个推荐项目进行**三级推荐等级划分**。

        ### 推荐项目三级分级评估
        对该场景的所有推荐项目，进行**三级推荐等级划分**：

        - **极其推荐 (Highly Recommended)**: 评分高，证据充分，与患者情况完美匹配，安全性和诊断价值俱佳，无明显禁忌
        - **推荐 (Recommended)**: 评分中等，临床适用性良好，风险收益比合理，可能存在轻微限制  
        - **不太推荐 (Less Recommended)**: 评分低，或存在安全隐患，或有明确禁忌症，或与当前临床需求匹配度不高

        ### 评估要点
        1. **患者匹配度**: 考虑患者年龄、性别、症状、病史等
        2. **临床相关性**: 与当前临床表现和诊断需求的匹配程度
        3. **安全性**: 辐射剂量、对比剂使用、禁忌症等安全因素
        4. **证据强度**: ACR评分、证据等级、共识水平
        5. **实用性**: 检查可行性、准备要求、时长等

        ## 输出格式
        请严格按以下JSON格式输出，不要额外解释：

        ```json
        {{
            "scenario_index": {scenario_index},
            "scenario_id": "填写场景语义ID",
            "comprehensive_score": "根据推荐项目质量给出的0-100综合评分",
            "scenario_reasoning": "该场景与患者情况的匹配度分析（50字）",
            "recommendation_grades": {{
                "highly_recommended": [推荐项目索引列表, 从1开始],
                "recommended": [推荐项目索引列表, 从1开始],
                "less_recommended": [推荐项目索引列表, 从1开始]
            }},
            "final_choices":["这里填入最终选择的最符合当前患者信息的检查项目推荐"]
            "grading_reasoning": "对该场景推荐项目分级的临床理由（50字），重点说明分级依据"
        }}"""
        return task_instruction

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

    async def _generate_overall_reasoning(self,
                                          patient_info,
                                          clinical_context,
                                          max_recommendations_per_scenario,
                                          final_results: List[Dict[str, Any]]):
        """生成总体推理说明"""
        patient_info_content = self.build_patient_context(patient_info)
        clinical_context_content = self.build_clinical_context(clinical_context)
        choices_content = ""
        a = []
        for choices in final_results:
            if isinstance(choices, list) and choices:
                a.extend(choices)
        choices_content = "\n".join(a)
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
            res = safe_parse_llm_response(response)
        except Exception as e:
            logger.info(f"解析json出错：{e}")

        choices = res.get("final_choices", [])
        reason = res.get("overall_reason", "")
        return {"final_choices": choices, "overall_reason": reason}

    def _fallback_for_confirmed_scenarios(self, confirmed_scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """降级方案"""
        logger.info("使用降级方案...")
        return []

    def get_strategy_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        status = {
            'environment': self.environment,
            'use_adaptive': self.use_adaptive,
            'threshold_config': self.strategy.threshold_config,
            'strategy_type': self.strategy.__class__.__name__
        }

        if isinstance(self.strategy, LearningThresholdStrategy):
            status.update({
                'learning_enabled': self.strategy.learning_enabled,
                'history_size': len(self.strategy.performance_history)
            })

        return status

    def set_adaptive_mode(self, enabled: bool):
        """动态设置自适应模式"""
        old_mode = self.use_adaptive
        self.use_adaptive = enabled

        if enabled and not isinstance(self.strategy, LearningThresholdStrategy):
            self.strategy = LearningThresholdStrategy()
            self._initialize_strategy()
            logger.info("🔄 切换到自适应学习模式")
        elif not enabled and isinstance(self.strategy, LearningThresholdStrategy):
            self.strategy = AdaptiveThresholdStrategy()
            self._initialize_strategy()
            logger.info("⚡ 切换到固定阈值模式")

        logger.info(f"📝 自适应模式从 {old_mode} 改为 {enabled}")

    def enable_learning(self, enabled: bool = True):
        """启用/禁用学习功能（仅对学习策略有效）"""
        if isinstance(self.strategy, LearningThresholdStrategy):
            self.strategy.learning_enabled = enabled
            status = "启用" if enabled else "禁用"
            logger.info(f"📚 学习功能已{status}")
        else:
            logger.warning("当前不是学习策略，无法启用学习功能")

    def reset_learning(self):
        """重置学习数据"""
        if isinstance(self.strategy, LearningThresholdStrategy):
            self.strategy.performance_history = []
            logger.info("🔄 学习数据已重置")
        else:
            logger.warning("当前不是学习策略，无法重置学习数据")

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
                    overall_choices= result.get('overall_choices', ''),
                    final_results = []

                    for selected_data in selected_scenarios_data:
                        scenario_index = selected_data.get('scenario_index')
                        scenario_id = selected_data.get('scenario_id')
                        grading_data = selected_data.get('recommendation_grades', {})
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
                        }

                        final_results.append(final_result)

                    # 按综合评分排序
                    final_results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

                    logger.info(f"✅ 单次调用完成，成功处理{len(final_results)}个场景")
                    return {"result":final_results,"overall_choices":overall_choices,'overall_reasoning':result.get('overall_reasoning', '')}
                else:
                    return response
            except Exception as e:
                logger.error(f"❌ 单次调用失败: {str(e)}")
                if not direct_return:
                    return self._fallback_for_confirmed_scenarios(confirmed_scenarios)
                return "执行出错"



