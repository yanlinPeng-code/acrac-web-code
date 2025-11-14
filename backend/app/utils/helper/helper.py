#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/7/19 17:41
@Author  : thezehui@gmail.com
@File    : helper.py
"""
import importlib
import json
import random
import string
from datetime import datetime
from enum import Enum
from hashlib import sha3_256
from uuid import UUID

from langchain_core.documents import Document
from pydantic import BaseModel
from typing_extensions import Any

import json
import re
from typing import Dict, List, Any, Optional

from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)





def safe_parse_llm_response( response: str, expected_scenario_count: int=3) -> Optional[Dict[str, Any]]:
    """安全解析LLM返回的JSON数据，增强防御机制"""
    # 预处理：移除所有可能的Markdown代码块标记
    cleaned_response = re.sub(r'```json\s*', '', response)
    cleaned_response = re.sub(r'```\s*', '', cleaned_response)
    cleaned_response = cleaned_response.strip()
    # 方法1: 尝试直接解析清理后的响应
    try:
        result = json.loads(cleaned_response)
        if _validate_result_structure(result, expected_scenario_count):
            return result
    except json.JSONDecodeError as e:
        logger.warning(f"直接解析失败: {e}")

    # 方法2: 使用正则表达式提取JSON部分
    json_patterns = [
        r'```json\s*(.*?)\s*```',  # 匹配 ```json ... ```
        r'```\s*(.*?)\s*```',  # 匹配 ``` ... ```
        r'\{.*\}',  # 匹配 {...}
        r'\{[\s\S]*\}',  # 匹配最外层的花括号内容
    ]

    for pattern in json_patterns:
        try:
            json_match = re.search(pattern, cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                if _validate_result_structure(result, expected_scenario_count):
                    return result
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"模式匹配解析失败: {e}")
            continue

        # 方法3: 尝试修复常见的JSON格式错误
    try:
        fixed_response = _fix_common_json_errors(cleaned_response)
        result = json.loads(fixed_response)
        if _validate_result_structure(result, expected_scenario_count):
            return result
    except json.JSONDecodeError as e:
        logger.error(f"修复后解析失败: {e}")

    logger.error("所有JSON解析方法均失败")
    return None


def _fix_common_json_errors(text: str) -> str:
    """修复常见的JSON格式错误"""

    # 修复尾随逗号
    fixed = re.sub(r',\s*([}\]])', r'\1', text)

    # 修复单引号（替换为双引号）
    fixed = re.sub(r"'([^']*)'", r'"\1"', fixed)

    # 修复未转义的控制字符
    fixed = fixed.replace('\n', '\\n').replace('\t', '\\t')

    # 修复注释（移除）
    fixed = re.sub(r'//.*', '', fixed)
    fixed = re.sub(r'/\*.*?\*/', '', fixed, flags=re.DOTALL)

    # 修复可能缺失的引号
    fixed = re.sub(r'(\w+):', r'"\1":', fixed)

    return fixed


def _validate_result_structure(result: Dict[str, Any], expected_scenario_count: int) -> bool:
    """验证结果结构是否符合预期"""

    if not isinstance(result, dict):
        logger.error("结果不是字典类型")
        return False

    if 'selected_scenarios' not in result:
        logger.error("缺少selected_scenarios字段")
        return False

    selected_scenarios = result['selected_scenarios']
    if not isinstance(selected_scenarios, list):
        logger.error("selected_scenarios不是列表类型")
        return False

    # 验证每个场景的数据结构
    for i, scenario_data in enumerate(selected_scenarios):
        if not isinstance(scenario_data, dict):
            logger.error(f"场景{i}数据不是字典类型")
            return False

        required_fields = ['scenario_index', 'scenario_id', 'recommendation_grades',"comprehensive_score","final_choices"]
        for field in required_fields:
            if field not in scenario_data:
                logger.error(f"场景{i}缺少必要字段: {field}")
                return False

        # 验证recommendation_grades结构
        grades = scenario_data['recommendation_grades']
        if not isinstance(grades, dict):
            logger.error(f"场景{i}的recommendation_grades不是字典类型")
            return False
        choices=scenario_data["final_choices"]
        if  not isinstance(choices,list):
            logger.error(f"场景{i}的final_choices不是列表类型")
            return False
        required_grade_keys = ['highly_recommended', 'recommended', 'less_recommended']
        for key in required_grade_keys:
            if key not in grades:
                logger.error(f"场景{i}的recommendation_grades缺少{key}")
                return False
            if not isinstance(grades[key], list):
                logger.error(f"场景{i}的{key}不是列表类型")
                return False

    logger.info(f"✅ JSON结构验证通过，找到{len(selected_scenarios)}个场景")
    return True



def dynamic_import(module_name: str, symbol_name: str) -> Any:
    """动态导入特定模块下的特定功能"""
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def add_attribute(attr_name: str, attr_value: Any):
    """装饰器函数，为特定的函数添加相应的属性，第一个参数为属性名字，第二个参数为属性值"""

    def decorator(func):
        setattr(func, attr_name, attr_value)
        return func

    return decorator


def generate_text_hash(text: str) -> str:
    """根据传递的文本计算对应的哈希值"""
    # 1.将需要计算哈希值的内容加上None这个字符串，避免传递了空字符串导致计算出错
    text = str(text) + "None"

    # 2.使用sha3_256将数据转换成哈希值后返回
    return sha3_256(text.encode()).hexdigest()


def datetime_to_timestamp(dt: datetime) -> int:
    """将传入的datetime时间转换成时间戳，如果数据不存在则返回0"""
    if dt is None:
        return 0
    return int(dt.timestamp())


def convert_model_to_dict(obj: Any, *args, **kwargs):
    """辅助函数，将Pydantic V1版本中的UUID/Enum等数据转换成可序列化存储的数据。"""
    # 1.如果是Pydantic的BaseModel类型，递归处理其字段
    if isinstance(obj, BaseModel):
        obj_dict = obj.model_dump(*args, **kwargs)
        for key, value in obj_dict.items():
            obj_dict[key] = convert_model_to_dict(value, *args, **kwargs)
        return obj_dict

    elif isinstance(obj, list):
        return [convert_model_to_dict(item, *args, **kwargs) for item in obj]

    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {key: convert_model_to_dict(value, *args, **kwargs) for key, value in obj.items()}
    return obj


def get_value_type(value: Any) -> Any:
    """根据传递的值获取变量的类型，并将str和bool转换成string和boolean"""
    # 1.计算变量的类型并转换成字符串
    value_type = type(value).__name__

    # 2.判断是否为str或者是bool
    if value_type == "str":
        return "string"
    elif value_type == "bool":
        return "boolean"

    return value_type


def generate_random_string(length: int = 16) -> str:
    """根据传递的字符，生成随机的字符串"""
    chars = string.ascii_letters + string.digits

    random_str = "".join(random.choices(chars, k=length))
    return random_str


def combine_documents(documents: list[Document]) -> str:
    """将对应的文档列表使用换行符进行合并"""
    return "\n\n".join([document.page_content for document in documents])


def remove_fields(origin_dict: dict, target_dict: list[str]) -> any:
    """
    去除字典中的字段
    :param origin_dict:
    :param target_dict:
    :return:
    """
    for field in target_dict:
        origin_dict.pop(field, None)


def safe_process_recommendation_grades(

        grading_data: Dict[str, List[int]],
        original_recommendations: List[Dict[str, Any]],
        scenario_index: int
) -> Dict[str, List[Dict[str, Any]]]:
    """安全处理推荐分级数据"""

    graded_recommendations = {
        "highly_recommended": [],
        "recommended": [],
        "less_recommended": []
    }

    recommendation_levels = [
        ('highly_recommended', '极其推荐'),
        ('recommended', '推荐'),
        ('less_recommended', '不太推荐')
    ]

    for level_key, level_zh in recommendation_levels:
        # 确保分级数据存在且是列表
        level_indices = grading_data.get(level_key, [])
        if not isinstance(level_indices, list):
            logger.warning(f"场景{scenario_index}的{level_zh}数据不是列表类型")
            continue

        for rec_idx in level_indices:
            # 验证索引范围
            if not (1 <= rec_idx <= len(original_recommendations)):
                logger.warning(f"场景{scenario_index}的无效{level_zh}索引: {rec_idx}")
                continue

            try:
                rec_data = original_recommendations[rec_idx - 1].copy()
                rec_data['recommendation_level'] = level_key
                rec_data['recommendation_level_zh'] = level_zh

                # 添加详细信息
                procedure = rec_data['procedure']
                recommendation = rec_data['recommendation']

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

            except Exception as e:
                logger.error(f"处理场景{scenario_index}的推荐项目{rec_idx}时出错: {str(e)}")
                continue

    return graded_recommendations


def assemble_database_results(

        scenarios_with_recommendations: List[Dict[str, Any]],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        max_scenarios: int,
        max_recommendations_per_scenario: int
) -> List[Dict[str, Any]]:
    """
    将数据库查询结果组装成与LLM返回相同的格式

    Args:
        scenarios_with_recommendations: get_scenarios_with_recommends 返回的数据
        patient_info: 患者信息
        clinical_context: 临床上下文
        max_scenarios: 最大场景数
        max_recommendations_per_scenario: 每个场景最大推荐数

    Returns:
        与LLM返回格式相同的结果
    """
    try:
        final_results = []

        for index, scenario_data in enumerate(scenarios_with_recommendations[:max_scenarios], 1):
            # 组装单个场景数据
            assembled_scenario = _assemble_single_scenario_from_db(
                scenario_data, index, patient_info, clinical_context, max_recommendations_per_scenario
            )

            if assembled_scenario:
                final_results.append(assembled_scenario)

        # 按综合评分排序
        final_results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

        logger.info(f"✅ 数据库结果组装完成: {len(final_results)}个场景")
        return final_results

    except Exception as e:
        logger.error(f"❌ 数据库结果组装失败: {str(e)}")
        return []

def _assemble_single_scenario_from_db(
        
        scenario_data: Dict[str, Any],
        scenario_index: int,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        max_recommendations: int
) -> Optional[Dict[str, Any]]:
    """从数据库数据组装单个场景"""

    try:
        scenario = scenario_data['scenario']
        raw_recommendations = scenario_data.get('recommendations', [])

        # 限制每个场景的推荐数量
        limited_recommendations = raw_recommendations[:max_recommendations]

        if not limited_recommendations:
            logger.warning(f"场景 {scenario.semantic_id} 没有推荐项目")
            return None

        # 对推荐项目进行分级
        graded_recommendations = _grade_recommendations(limited_recommendations)

        # 计算综合评分
        comprehensive_score = _calculate_comprehensive_score(
            scenario_data, limited_recommendations, patient_info
        )

        # 生成推理文本
        scenario_reasoning = _generate_scenario_reasoning(scenario_data, patient_info)
        grading_reasoning = _generate_grading_reasoning(graded_recommendations)

        final_choices = []
        for level in ["highly_recommended", "recommended", "less_recommended"]:
            for rec in graded_recommendations.get(level, []):
                if len(final_choices) >= max_recommendations:
                    break
                name = (
                    (rec.get("procedure_details", {}).get("name_zh") or "")
                    or (rec.get("procedure_details", {}).get("name_en") or "")
                )
                if not name:
                    name = str(rec.get("procedure_details", {}).get("semantic_id", ""))
                if name:
                    final_choices.append(name)

        # 组装最终结果
        return {
            'comprehensive_score': comprehensive_score,
            'scenario_reasoning': scenario_reasoning,
            'grading_reasoning': grading_reasoning,
            'overall_reasoning': '基于数据库查询和ACR评分的自动分级推荐',
            'graded_recommendations': graded_recommendations,
            'recommendation_summary': {
                'highly_recommended_count': len(graded_recommendations['highly_recommended']),
                'recommended_count': len(graded_recommendations['recommended']),
                'less_recommended_count': len(graded_recommendations['less_recommended']),
                'total_recommendations': len(limited_recommendations)
            },
            'final_choices': final_choices,
            'scenario_metadata': {
                'scenario_id': scenario.semantic_id,
                'description': scenario.description_zh,
                'panel': getattr(scenario.panel, 'name_zh', '未知') if hasattr(scenario, 'panel') else '未知',
                'patient_population': scenario.patient_population or '未知',
                'clinical_context': scenario.clinical_context or '无',
                'original_index': scenario_index
            }
        }

    except Exception as e:
        logger.error(f"组装场景 {scenario_data.get('scenario_id', 'unknown')} 失败: {str(e)}")
        return None


def _grade_recommendations(recommendations: List[Dict]) -> Dict[str, List[Dict]]:
    """根据ACR评分对推荐项目进行分级"""

    graded = {
        "highly_recommended": [],
        "recommended": [],
        "less_recommended": []
    }

    for rec_data in recommendations:
        # 组装推荐项目数据
        assembled_rec = _assemble_recommendation_from_db(rec_data)

        if not assembled_rec:
            continue

        # 根据ACR评分分级
        rating = rec_data['recommendation'].appropriateness_rating or 0
        if rating >= 7:
            level_key = "highly_recommended"
            level_zh = "极其推荐"
        elif rating >= 4:
            level_key = "recommended"
            level_zh = "推荐"
        else:
            level_key = "less_recommended"
            level_zh = "不太推荐"

        # 设置推荐等级
        assembled_rec['recommendation_level'] = level_key
        assembled_rec['recommendation_level_zh'] = level_zh

        graded[level_key].append(assembled_rec)

    return graded


def _assemble_recommendation_from_db( rec_data: Dict) -> Optional[Dict[str, Any]]:
    """从数据库数据组装单个推荐项目"""

    try:
        recommendation = rec_data['recommendation']
        procedure = rec_data['procedure']

        return {
            'recommendation_level': '',  # 将在分级时设置
            'recommendation_level_zh': '',  # 将在分级时设置
            'procedure_details': {
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
                'description_zh': procedure.description_zh or ''
            },
            'recommendation_details': {
                'appropriateness_rating': recommendation.appropriateness_rating,
                'appropriateness_category_zh': recommendation.appropriateness_category_zh or '',
                'evidence_level': recommendation.evidence_level or '',
                'consensus_level': recommendation.consensus_level or '',
                'adult_radiation_dose': recommendation.adult_radiation_dose or '',
                'pediatric_radiation_dose': recommendation.pediatric_radiation_dose or '',
                'pregnancy_safety': recommendation.pregnancy_safety or '',
                'contraindications': recommendation.contraindications or '',
                'reasoning_zh': recommendation.reasoning_zh or '',
                'special_considerations': recommendation.special_considerations or ''
            }
        }
    except Exception as e:
        logger.error(f"组装推荐项目失败: {str(e)}")
        return None


def _calculate_comprehensive_score(
        
        scenario_data: Dict[str, Any],
        recommendations: List[Dict],
        patient_info: PatientInfo
) -> float:
    """计算场景综合评分"""

    if not recommendations:
        return 0.0

    # 基础评分：场景匹配分数（占40%）
    matching_scores = scenario_data.get('matching_scores', {})
    base_score = matching_scores.get('final_score', 0) * 0.4

    # ACR评分部分：平均ACR评分（占40%）
    avg_acr_rating = sum(
        (rec['recommendation'].appropriateness_rating or 0) for rec in recommendations
    ) / len(recommendations)
    acr_score = (avg_acr_rating / 9) * 40

    # 患者匹配度加分（占20%）
    patient_match_bonus = _calculate_patient_match_bonus(recommendations, patient_info) * 0.2

    return min(100.0, base_score + acr_score + patient_match_bonus)


def _calculate_patient_match_bonus(
        
        recommendations: List[Dict],
        patient_info: PatientInfo
) -> float:
    """计算患者匹配度加分"""

    bonus = 0.0

    for rec_data in recommendations:
        recommendation = rec_data['recommendation']
        procedure = rec_data['procedure']

        # 检查妊娠安全性匹配
        if (patient_info.pregnancy_status and
                patient_info.pregnancy_status in ["妊娠期", "哺乳期"] and
                recommendation.pregnancy_safety == "安全"):
            bonus += 5.0

        # 检查辐射安全性（儿童、老年人）
        if patient_info.age:
            if patient_info.age < 18:  # 儿童
                if procedure.radiation_level in ["低", "无"]:
                    bonus += 3.0
            elif patient_info.age > 65:  # 老年人
                if procedure.radiation_level != "高":
                    bonus += 2.0

        # 检查禁忌症匹配
        if (patient_info.allergies and
                recommendation.contraindications and
                any(allergy in recommendation.contraindications for allergy in patient_info.allergies)):
            bonus -= 5.0  # 有禁忌症扣分

    # 平均到每个推荐项目
    return bonus / max(len(recommendations), 1)


def _generate_scenario_reasoning(scenario_data: Dict[str, Any], patient_info: PatientInfo) -> str:
    """生成场景推理文本"""

    scenario = scenario_data['scenario']
    matching_scores = scenario_data.get('matching_scores', {})
    reasoning_parts = []

    # 场景匹配分数
    final_score = matching_scores.get('final_score', 0)
    if final_score > 0.8:
        reasoning_parts.append("场景匹配度很高")
    elif final_score > 0.6:
        reasoning_parts.append("场景匹配度中等")
    else:
        reasoning_parts.append("场景匹配度一般")

    # 患者人群匹配
    if (scenario.patient_population and
            _check_patient_population_match(scenario.patient_population, patient_info)):
        reasoning_parts.append(f"符合{scenario.patient_population}人群特征")

    # 临床上下文匹配
    if scenario.clinical_context:
        reasoning_parts.append(f"临床上下文: {scenario.clinical_context[:50]}...")

    return "；".join(reasoning_parts) if reasoning_parts else "基于相似度匹配的临床场景"


def _generate_grading_reasoning( graded_recommendations: Dict[str, List[Dict]]) -> str:
    """生成分级推理文本"""

    highly_count = len(graded_recommendations['highly_recommended'])
    recommended_count = len(graded_recommendations['recommended'])
    less_count = len(graded_recommendations['less_recommended'])

    reasoning_parts = []

    if highly_count > 0:
        reasoning_parts.append(f"{highly_count}个极其推荐项目(ACR 7-9分)")
    if recommended_count > 0:
        reasoning_parts.append(f"{recommended_count}个推荐项目(ACR 4-6分)")
    if less_count > 0:
        reasoning_parts.append(f"{less_count}个不太推荐项目(ACR 1-3分)")

    return "推荐项目分级基于ACR适宜性评分：" + "，".join(reasoning_parts)


def _check_patient_population_match(population: str, patient_info: PatientInfo) -> bool:
    """检查患者人群匹配"""
    if not population or not patient_info:
        return False

    population_lower = population.lower()

    # 年龄匹配
    if patient_info.age:
        if "儿童" in population_lower and patient_info.age < 18:
            return True
        if ("老年" in population_lower or "老人" in population_lower) and patient_info.age > 65:
            return True
        if "成人" in population_lower and 18 <= patient_info.age <= 65:
            return True

    # 性别匹配
    if patient_info.gender and patient_info.gender in population_lower:
        return True

    # 妊娠状态匹配
    if patient_info.pregnancy_status:
        if "妊娠" in population_lower and "妊娠" in patient_info.pregnancy_status:
            return True
        if "哺乳" in population_lower and "哺乳" in patient_info.pregnancy_status:
            return True

    return False
