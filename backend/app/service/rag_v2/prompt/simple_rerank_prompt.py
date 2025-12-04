from typing import List, Dict, Any

from app.config.config import settings
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v2.prompt.base_prompt import BasePrompt
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)

class SimpleRerankPrompt(BasePrompt):
      def __init__(self):
          super().__init__()



      def build_comprehensive_prompt_with_grading(
              self,
              all_scenarios: List[Dict[str, Any]],
              patient_info: PatientInfo,
              clinical_context: ClinicalContext,
              max_scenarios: int,
              max_recommendations_per_scenario: int,
              direct_return: bool,
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
              task_reserve_tokens = 700
              available_scenario_tokens = settings.OLLAMA_LLM_MAX_TOKENS - 800 - fixed_tokens - task_reserve_tokens
              logger.info(f"可用的提示词token数{available_scenario_tokens}")
              # 构建场景内容，限制在可用token数内
              scenarios_content = self.build_scenarios_with_recommend(
                  all_scenarios,
                  max_tokens=available_scenario_tokens
              )

              # 构建任务指令，使用实际显示的场景数量
              task_instruction = self.build_task_instruction(

                  max_scenarios=max_scenarios,
                  max_recommendations_per_scenario=max_recommendations_per_scenario,
                  direct_return=direct_return
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
              if total_tokens > settings.OLLAMA_LLM_MAX_TOKENS - 800:
                  logger.info(f"仍然超出{4096 - 600 - total_tokens}个token,进行截断")
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

      def build_scenarios_with_recommend(self,
                                         all_scenarios: List[Dict[str, Any]],
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

