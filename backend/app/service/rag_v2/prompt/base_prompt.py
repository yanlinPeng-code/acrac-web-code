
from typing import List, Dict, Any
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.utils.logger.simple_logger import get_logger

from app.service.rag_v2.base import Base

logger=get_logger(__name__)

class BasePrompt(Base):

    def __init__(self):
        super().__init__()




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
        if clinical_context.department:
            if '急性' in clinical_context.chief_complaint or '急诊' in clinical_context.department:
                key_clinical_points.append("🔴 急性病程：需快速诊断")
        if clinical_context.chief_complaint:
            if '外伤' in clinical_context.chief_complaint:
                key_clinical_points.append("🟡 外伤相关：关注结构性损伤")
        if clinical_context.diagnosis:
            if '肿瘤' in clinical_context.diagnosis or '占位' in clinical_context.diagnosis:
                key_clinical_points.append("🔵 肿瘤评估：需要精确分期")

        if key_clinical_points:
            clinical_content += f"\n### 临床特征\n" + "\n".join(f"- {point}" for point in key_clinical_points)

        return clinical_content
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


    def build_task_instruction(self,  max_scenarios: int,
                                 max_recommendations_per_scenario: int,direct_return: bool,):
          """构建任务指令"""
          if not direct_return:
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


    def build_scenarios_with_recommend(self,all_scenarios:List[Dict[str, Any]],max_tokens:int=2500):
        # 所有场景和推荐项目（利用完整字段信息）
        scenarios_text = "## 可选临床场景及推荐项目\n\n"

        for scenario_idx, scenario_data in enumerate(all_scenarios, 1):
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
                # evidence_info = []
                # if recommendation.evidence_level:
                #     evidence_info.append(f"证据强度: {recommendation.evidence_level}")
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
                    contra = recommendation.contraindications[:80] + "..." if len(
                        recommendation.contraindications) > 80 else recommendation.contraindications
                    safety_info.append(f"禁忌症: {contra}")
                if safety_info:
                    scenarios_text += f"   - 安全考虑: {', '.join(safety_info)}\n"

                # 推荐理由
                if recommendation.reasoning_zh:
                    reasoning = recommendation.reasoning_zh[:50] + "..." if len(
                        recommendation.reasoning_zh) > 50 else recommendation.reasoning_zh
                    scenarios_text += f"   - 推荐理由: {reasoning}\n"
                #
                # # 特殊考虑
                if recommendation.special_considerations:
                    special = recommendation.special_considerations[:80] + "..." if len(
                        recommendation.special_considerations) > 80 else recommendation.special_considerations
                    scenarios_text += f"   - 特殊考虑: {special}\n"
                #
                # # 标准编码（如有）
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
            # if recommendation.appropriateness_category_zh:
            #     content += f"   - 适宜性类别: {recommendation.appropriateness_category_zh}\n"

            # # 证据和共识
            # evidence_info = []
            # if recommendation.evidence_level:
            #     evidence_info.append(f"证据强度: {recommendation.evidence_level}")
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
                contra = recommendation.contraindications[:10] + "..." if len(
                    recommendation.contraindications) > 10 else recommendation.contraindications
                safety_info.append(f"禁忌症: {contra}")
            if safety_info:
                content += f"   - 安全考虑: {', '.join(safety_info)}\n"

            # 推荐理由
            # if recommendation.reasoning_zh:
            #     reasoning = recommendation.reasoning_zh[:5] + "..." if len(
            #         recommendation.reasoning_zh) > 50 else recommendation.reasoning_zh
            #     content += f"   - 推荐理由: {reasoning}\n"

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
        你必须输出final_choices作为每个场景的最终选择项目，不能为空！

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
            "final_choices":["这里填入最终选择的最符合当前患者信息的检查项目推荐,不能为空！,如果没有最推荐的，highly_recommended"]
            "grading_reasoning": "对该场景推荐项目分级的临床理由（20字），重点说明分级依据"
        }}"""
        return task_instruction


    def build_comprehensive_prompt_with_grading(self,
                                                all_scenarios: List[Dict[str, Any]],
                                                patient_info: PatientInfo,
                                                clinical_context: ClinicalContext,
                                                max_scenarios: int,
                                                max_recommendations_per_scenario: int,
                                                direct_return: bool,
                                                ):
        pass
    pass
