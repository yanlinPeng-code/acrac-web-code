from typing import Dict, Any, List

from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v2.rerank.adaptive_reranker import AdaptiveReranker
from app.utils.helper.helper import safe_parse_llm_response
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)
class FinalChoiceAdaptiveReranker(AdaptiveReranker):
      def __init__(self):
          super().__init__()

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
      def build_task_instruction(self,
                                 max_scenarios,
                                 max_recommendations_per_scenario,
                                 direct_return,
                                 ):
          if not direct_return:
              return f"""
                     ## 角色定位
                     你是一个具有20年经验的医学影像专家,能够根据用户的信息和临床上下文为用户选择最匹配的医学影像检查项目
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

                     ###  第三级：最终的项目推荐
                     - 结合所有的最佳场景以及最佳的项目推荐中选择{max_recommendations_per_scenario}个最符合用户身体状况和临床上下文的检查项目



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
                         "final_choices":[这里是检查项目名称，注意一定要为{max_recommendations_per_scenario}个]
                         "overall_reasoning": "总体选择策略，重点说明安全性考量和诊断路径"
                     }}
                      **重要：
                           -请只输出纯JSON格式，不要包含任何其他文字、说明或Markdown标记！确保JSON格式完全正确。**
                     """

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

      async def _get_recommendations_single_call(self,
                                           confirmed_scenarios: List[Dict[str, Any]],
                                           patient_info: PatientInfo,
                                           clinical_context: ClinicalContext,
                                           max_recommendations_per_scenario: int,
                                           expected_scenario_count: int,
                                           single_prompt: str,
                                           direct_return: bool = False
                                           ):

          try:

              response = await self.ai_service._call_llm(single_prompt)

              if not direct_return:

                  # 使用增强的JSON解析
                  result = safe_parse_llm_response(response=response, expected_scenario_count=len(confirmed_scenarios))

                  if result is None:
                      logger.error("JSON解析失败，使用降级方案")
                      return self._fallback_for_confirmed_scenarios(confirmed_scenarios)

                  # 处理选中的场景数据
                  final_choices=result.get("final_choices",[])
                  overall_reasoning=result.get("overall_reasoning","")
                  final_results=[]
                  if final_choices:
                      final_results.append({"final_choices":final_choices,"overall_reasoning":overall_reasoning})
                  else:
                      final_results.append({"final_choices":[],"overall_reasoning":""})

                  return final_results
              else:
                  return response
          except Exception as e:
              logger.error(f"❌ 单次调用失败: {str(e)}")
              if not direct_return:
                  return self._fallback_for_confirmed_scenarios(confirmed_scenarios)
              return "执行出错"

