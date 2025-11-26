from typing import Any, Dict, List
import time
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.language_model.model_client_wrapper import ChatClientSDK, EmbeddingClientSDK, RerankerClientSDK
from app.entity.model_entity import DEFAULT_APP_CONFIG
from app.entity.retrieval_entity import RerankingStrategy
from app.response.exception.exceptions import ValidationException, InternalServerException
from app.schema.IntelligentRecommendation_schemas import (
    IntelligentRecommendationRequest,
    IntelligentRecommendationResponse,
    SearchStrategy, RetrievalRequest
)
from app.service.rag_v1.model_service import ModelService
from app.service.rag_v1.retrieval_service import RetrievalService
from app.service.rag_v1.simple_retrieval_service import SimpleRetrievalService
from app.service.rag_v1.adaptive_recommend_service import AdaptiveRecommendationEngineService
from app.utils.logger.simple_logger import get_logger
logger = get_logger(__name__)
"""
科室: 心血管内科 ,
临床场景: 35岁男性，高血压病史3年，规律服药，青霉素过敏，主诉反复头痛、头晕伴耳鸣1周，
症状中度，体温36.8℃，血压130/85 mmHg，心肺听诊正常，考虑原发性高血压。
"""

class RagService:

      def __init__(self,
                   session: AsyncSession,
                   model_service: ModelService,
                   retrieval_service:RetrievalService,
                   simple_retrieval_service:SimpleRetrievalService,
                   ):
          self.session = session
          self.model_service = model_service
          self.retrieval_service = retrieval_service
          self.simple_retrieval_service=simple_retrieval_service

      async def generate_intelligent_recommendation(
              self,
              request: IntelligentRecommendationRequest,
              medical_dict: Dict[str, Any]
              ) -> IntelligentRecommendationResponse:
          """
          生成智能推荐 - 使用策略枚举统一处理

          流程：
          1. 执行四阶段混合检索
          2. 根据策略枚举执行相应的重排序逻辑
          3. 返回结构化结果
          """
          standard_query=""
          start_time = time.time()
          if request.standard_query and isinstance(request.standard_query, str):
              standard_query = request.standard_query
          try:
              # ========== 1. 执行四阶段混合检索 ==========


              search_strategy = request.search_strategy or SearchStrategy()

              # 获取检索策略配置
              retrieval_config = request.retrieval_strategy or RetrievalRequest()
              strategy = retrieval_config.reranking_strategy

              logger.info(f"🚀 开始智能推荐，使用策略: {strategy.value}")
              logger.info(f"   规则过滤: {retrieval_config.apply_rule_filter}, "
                          f"LLM重排序: {retrieval_config.enable_reranking}, "
                          f"LLM推荐: {retrieval_config.need_llm_recommendations}")

              # 计算初始检索数量
              initial_top_k = self._calculate_initial_top_k(retrieval_config)

              final_scenarios = await self.retrieval_service.retrieve_clinical_scenarios(
                  patient_info=request.patient_info,
                  clinical_context=request.clinical_context,
                  standard_query=standard_query,
                  search_strategy=search_strategy,
                  top_k=initial_top_k,
                  similarity_threshold=retrieval_config.similarity_threshold,
                  medical_dict=medical_dict
              )

              # ========== 2. 根据策略执行重排序 ==========
              best_recommendations = await self.retrieval_service.llm_rank_all_scenarios(
                  all_scenarios=final_scenarios,
                  patient_info=request.patient_info,
                  clinical_context=request.clinical_context,
                  strategy=strategy,
                  min_rating=retrieval_config.min_appropriateness_rating or 5,
                  direct_return=request.direct_return,
                  max_scenarios=retrieval_config.top_scenarios,
                  max_recommendations_per_scenario=retrieval_config.top_recommendations_per_scenario
              )

              # ========== 3. 计算处理时间 ==========
              processing_time_ms = int((time.time() - start_time) * 1000)

              # ========== 4. 返回结构化响应 ==========
              return IntelligentRecommendationResponse(
                  query=f"{request.clinical_context.chief_complaint} | {request.clinical_context.diagnosis or ''}",
                  best_recommendations=best_recommendations,
                  processing_time_ms=processing_time_ms,
                  similarity_threshold=retrieval_config.similarity_threshold,
                  strategy_used=strategy.value
              )

          except Exception as e:
              logger.error(f"❌ 智能推荐失败: {str(e)}")
              processing_time_ms = int((time.time() - start_time) * 1000)
              return IntelligentRecommendationResponse(
                  best_recommendations=[],
                  processing_time_ms=processing_time_ms,
                  error_message=str(e)
              )

      async def stream_direct_recommendation(
              self,
              request: IntelligentRecommendationRequest,
              medical_dict: Dict[str, Any]
      ):
          """流式返回LLM生成的直接推荐文本（先推荐项目，再推荐理由）。"""
          search_strategy = request.search_strategy or SearchStrategy()
          retrieval_config = request.retrieval_strategy or RetrievalRequest()
          initial_top_k = self._calculate_initial_top_k(retrieval_config)

          scenarios = await self.retrieval_service.retrieve_clinical_scenarios(
              patient_info=request.patient_info,
              clinical_context=request.clinical_context,
              standard_query=request.standard_query or "",
              search_strategy=search_strategy,
              need_optimize_query=request.need_optimize_query,
              top_k=initial_top_k,
              similarity_threshold=retrieval_config.similarity_threshold,
              medical_dict=medical_dict
          )
          scenarios_with_recs = await self.retrieval_service.get_scenarios_with_recommends(
              scenarios,
              max_scenarios=retrieval_config.top_scenarios,
              max_recommendations_per_scenario=retrieval_config.top_recommendations_per_scenario,
              min_rating=retrieval_config.min_appropriateness_rating or 5
          )
          engine = AdaptiveRecommendationEngineService()
          prompt = engine._build_single_call_prompt(
              confirmed_scenarios=scenarios_with_recs,
              patient_info=request.patient_info,
              clinical_context=request.clinical_context,
              max_recommendations_per_scenario=retrieval_config.top_recommendations_per_scenario,
              direct_return=True
          )
          async for chunk in self.retrieval_service.ai_service._stream_llm(prompt):
              yield chunk

      def _calculate_initial_top_k(self, retrieval_config: RetrievalRequest) -> int:
          """计算初始检索数量"""
          strategy = retrieval_config.reranking_strategy
          base_k = retrieval_config.top_scenarios

          # 根据策略决定初始检索数量
          strategy_multipliers = {
              RerankingStrategy.NONE: 1,
              RerankingStrategy.RULE_ONLY: 3,
              RerankingStrategy.LLM_SCENARIO_ONLY: 4,
              RerankingStrategy.LLM_RECOMMENDATION_ONLY: 1,
              RerankingStrategy.RULE_AND_LLM_SCENARIO: 5,
              RerankingStrategy.RULE_AND_LLM_RECOMMENDATION: 4,
              RerankingStrategy.LLM_SCENARIO_AND_RECOMMENDATION: 4,
              RerankingStrategy.ALL: 6
          }

          multiplier = strategy_multipliers.get(strategy, 3)
          return max(30, base_k * multiplier)

      async  def generate_simple_recommendation(self,
           request: IntelligentRecommendationRequest,
           medical_dict: Dict[str, Any]):
          standard_query=""
          start_time = time.time()
          try:
              if request.standard_query and isinstance(request.standard_query,str):
                  standard_query=request.standard_query


              if request.retrieval_strategy.top_scenarios>=5:
                  raise ValidationException(message="请求的最大场景数不能超过5个！")
             
              # ========== 1. 执行四阶段混合检索 ==========
              search_strategy = request.search_strategy or SearchStrategy()

              # 获取检索策略配置
              retrieval_config = request.retrieval_strategy or RetrievalRequest()
              strategy = retrieval_config.reranking_strategy

              logger.info(f"🚀 开始智能推荐，使用策略: {strategy.value}")
              logger.info(f"   规则过滤: {retrieval_config.apply_rule_filter}, "
                          f"LLM重排序: {retrieval_config.enable_reranking}, "
                          f"LLM推荐: {retrieval_config.need_llm_recommendations}")




              # 计算初始检索数量
              initial_top_k = self._calculate_initial_top_k(retrieval_config)

              final_scenarios = await self.retrieval_service.retrieve_clinical_scenarios(
                  patient_info=request.patient_info,
                  clinical_context=request.clinical_context,
                  standard_query=standard_query,
                  search_strategy=search_strategy,
                  top_k=initial_top_k,
                  similarity_threshold=retrieval_config.similarity_threshold,
                  medical_dict=medical_dict
              )
              # ========== 2. 根据策略执行重排序 ==========
              best_recommendations = await self.simple_retrieval_service.simple_rank_all_scenarios(
                  all_scenarios=final_scenarios,
                  patient_info=request.patient_info,
                  clinical_context=request.clinical_context,
                  strategy=strategy,
                  min_rating=retrieval_config.min_appropriateness_rating or 5,
                  direct_return=request.direct_return,
                  max_scenarios=retrieval_config.top_scenarios,
                  max_recommendations_per_scenario=retrieval_config.top_recommendations_per_scenario
              )

              # ========== 3. 计算处理时间 ==========
              processing_time_ms = int((time.time() - start_time) * 1000)

              # ========== 4. 返回结构化响应 ==========
              return IntelligentRecommendationResponse(
                  query=f"{request.clinical_context.chief_complaint} | {request.clinical_context.diagnosis or ''}",
                  best_recommendations=best_recommendations,
                  processing_time_ms=processing_time_ms,
                  similarity_threshold=retrieval_config.similarity_threshold,
                  strategy_used=strategy.value
              )

          except Exception as e:
               raise InternalServerException(
                   message=str(e)
               )










      async def _process_and_validate_model_config(self, origin_model_config: dict[str, Any]) -> dict[str, Any]:
          """
          处理并校验模型配置（支持chat/embedding/reranker三种子模型），返回校验后的配置

          校验逻辑：
          1. 整体结构校验（必须为字典）
          2. 三类子模型（chat_model/embedding_model/reranker_model）分别校验：
             - 类型合法性（type必须匹配）
             - 模型名称（name）有效性（使用ModelManager验证）
             - 参数（parameters）结构校验
          
          注意：不再依赖language_model_manager，使用ModelManager进行模型验证
          """
          # 1. 基础校验：输入必须为字典，否则返回默认配置
          if not isinstance(origin_model_config, dict):
              return DEFAULT_APP_CONFIG["model_config"]

          # 2. 提取基础配置，使用默认值兜底
          validated_config = {
              "chat_model": origin_model_config.get("chat_model", {}),
              "embedding_model": origin_model_config.get("embedding_model", {}),
              "reranker_model": origin_model_config.get("reranker_model", {})  # 提取reranker模型配置
          }

          # 3. 子模型校验通用逻辑（使用ModelManager验证）
          def _validate_sub_model(
                  sub_model_key: str,  # 子模型键名（如"chat_model"）
                  expected_type: str  # 预期类型（如"chat"）
          ) -> Dict[str, Any]:
              """校验单个子模型的配置（支持任意类型的子模型，保持通用性）"""
              user_sub_config = validated_config[sub_model_key]
              if not isinstance(user_sub_config, dict):
                  user_sub_config = {}

              # 从默认配置中获取该子模型的基准配置
              default_sub_config = DEFAULT_APP_CONFIG["model_config"][sub_model_key]

              # 校验type
              sub_type = user_sub_config.get("type", default_sub_config["type"])
              if not isinstance(sub_type, str) or sub_type != expected_type:
                  sub_type = default_sub_config["type"]

              # 校验model name（使用ModelManager）
              sub_name = user_sub_config.get("name", default_sub_config["name"])
              if not isinstance(sub_name, str) or not sub_name:
                  sub_name = default_sub_config["name"]
              else:
                  # 使用ModelManager验证模型是否存在且可用
                  is_valid, error_msg = self.model_service.model_manager.validate_model(sub_name)
                  if not is_valid:
                      # 模型不存在或不可用，使用默认值
                      sub_name = default_sub_config["name"]

              # 校验parameters（只校验是否为字典，不校验具体参数）
              user_params = user_sub_config.get("parameters", {})
              if not isinstance(user_params, dict):
                  user_params = default_sub_config.get("parameters", {})

              return {
                  "type": sub_type,
                  "name": sub_name,
                  "parameters": user_params  # 直接使用用户参数，由model_service验证
              }

          # 4. 执行子模型校验
          if validated_config["chat_model"]:
              validated_config["chat_model"] = _validate_sub_model("chat_model", "chat")
          if validated_config["embedding_model"]:
              validated_config["embedding_model"] = _validate_sub_model("embedding_model", "embedding")
          if validated_config["reranker_model"]:
              validated_config["reranker_model"] = _validate_sub_model("reranker_model", "reranker")
          # validated_config["chat_model"] = _validate_sub_model("chat_model", "chat")
          # validated_config["embedding_model"] = _validate_sub_model("embedding_model", "embedding")
          # validated_config["reranker_model"] = _validate_sub_model("reranker_model", "reranker")

          return validated_config

      async def _generate_llm_explanation(
          self,
          chat_model: Any,
          patient_info,
          clinical_context,
          scenarios_with_recommendations: List[Dict]
      ) -> Dict[str, Any]:
          """
          使用LLM生成推荐说明
          
          基于检索到的临床场景和推荐项目，生成人性化的推荐解释
          """
          # 构建提示词
          prompt = self._build_recommendation_prompt(
              patient_info,
              clinical_context,
              scenarios_with_recommendations
          )
          
          try:
              # 调用聊天模型
              response = await self._call_chat_model(chat_model, prompt)
              return {
                  'explanation': response,
                  'generated': True
              }
          except Exception as e:
              return {
                  'explanation': f"LLM生成失败: {str(e)}",
                  'generated': False
              }
      
      def _build_recommendation_prompt(
          self,
          patient_info,
          clinical_context,
          scenarios_with_recommendations: List[Dict]
      ) -> str:
          """
          构建LLM提示词
          """
          prompt_parts = [
              "# 临床推荐任务",
              "",
              "## 患者信息",
              f"- 年龄: {patient_info.age}岁" if patient_info.age else "",
              f"- 性别: {patient_info.gender}" if patient_info.gender else "",
              f"- 妊娠状态: {patient_info.pregnancy_status}" if patient_info.pregnancy_status else "",
              "",
              "## 临床上下文",
              f"- 主诉: {clinical_context.chief_complaint}",
              f"- 既往病史: {clinical_context.medical_history}" if clinical_context.medical_history else "",
              f"- 诊断: {clinical_context.diagnosis}" if clinical_context.diagnosis else "",
              "",
              "## 检索到的临床场景与推荐",
              ""
          ]
          
          # 添加场景和推荐
          for i, scenario in enumerate(scenarios_with_recommendations[:3], 1):  # 只显示前3个
              prompt_parts.append(f"### 场景 {i}: {scenario['scenario_description']}")
              prompt_parts.append(f"匹配分数: {scenario['matching_scores']['final_score']:.2f}")
              prompt_parts.append("")
              prompt_parts.append("推荐检查项目:")
              for rec in scenario['recommendations'][:5]:  # 每个场景显示前5个推荐
                  prompt_parts.append(
                      f"- {rec['procedure_name']} (适宜性: {rec['appropriateness_rating']}/9)"
                  )
              prompt_parts.append("")
          
          prompt_parts.extend([
              "",
              "## 任务要求",
              "请根据以上信息，生成一份简洁、专业的临床检查推荐说明，包括：",
              "1. 最适合的检查项目（前3项）",
              "2. 选择理由（结合患者情况和临床场景）",
              "3. 注意事项（如有）",
              "",
              "请用中文回答，语言简洁专业。"
          ])
          
          return "\n".join(filter(None, prompt_parts))
      
      async def _call_chat_model(self, chat_model: Any, prompt: str) -> str:
          """
          调用聊天模型
          """
          # 这里需要根据实际的聊天模型接口实现
          if hasattr(chat_model, 'chat'):
              result = await chat_model.chat(prompt)
              return result
          elif hasattr(chat_model, '__call__'):
              result = await chat_model(prompt)
              return result
          else:
              raise NotImplementedError("聊天模型接口未实现")


if __name__ == '__main__':
    import asyncio
    from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
    
    async def test():
        # 这里需要实际的数据库会话
        # rag_service = RagService(
        #     session=session,
        #     model_service=LanguageModelService(),
        #     language_model_manager=LanguageModelManager()
        # )
        # 
        # request = IntelligentRecommendationRequest(
        #     patient_info=PatientInfo(
        #         age=45,
        #         gender="female",
        #         pregnancy_status="not_applicable"
        #     ),
        #     clinical_context=ClinicalContext(
        #         chief_complaint="胸痛",
        #         diagnosis="疑似冠心病"
        #     )
        # )
        # 
        # response = await rag_service.generate_intelligent_recommendation(request)
        # print(response)
        pass
    
    asyncio.run(test())











