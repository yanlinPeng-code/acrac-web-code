
import asyncio
import io
import json
import random
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import aiohttp
import numpy as np
import pandas as pd

from backend.app.entity.eval_entity import EVAL_CONFIG
from backend.app.schema.IntelligentRecommendation_schemas import SearchStrategy
from backend.app.schema.eval_schema import EvalParams
from backend.app.schema.judge_schemas import JudgeRequest
from backend.app.service.eval_v1.judge_service import JudgeService


class EvaluationService:
    """评测服务：通过 HTTP 直连被测后端 URL，执行推荐接口并统计命中率。"""

    def __init__(self, max_concurrent_per_endpoint: int = 5):
        self.eval_config = EVAL_CONFIG
        self.judge_service = JudgeService()
        self.max_concurrent_per_endpoint = max_concurrent_per_endpoint  # 每个接口的并发数

    def _calculate_endpoint_statistics(self, result_df_data: List[Dict[str, Any]], endpoint_name: str = "") -> Dict[str, Any]:
        """计算接口统计数据的公共方法（去除冗余）"""
        if not result_df_data:
            return {
                'api_name': endpoint_name,
                'top1_hit_count': 0,
                'top3_hit_count': 0,
                'top1_accuracy': 0.0,
                'top3_accuracy': 0.0,
                'avg_response_time_ms': 0.0,
                'total_time_ms': 0.0,
                'total_samples': 0,
                'total_rows': 0,
                'invalid_samples': 0
            }

        df_temp = pd.DataFrame(result_df_data)

        # 只统计有效样本（is_valid_sample 为 True）
        if 'is_valid_sample' in df_temp.columns:
            valid_df = df_temp[df_temp['is_valid_sample'] == True]
        else:
            valid_df = df_temp

        total_samples = len(valid_df)  # 有效样本数
        total_rows = len(df_temp)  # 总行数
        invalid_samples = total_rows - total_samples

        top1_hits = int(valid_df['top1_hit'].sum()) if 'top1_hit' in valid_df.columns and len(valid_df) > 0 else 0
        top3_hits = int(valid_df['top3_hit'].sum()) if 'top3_hit' in valid_df.columns and len(valid_df) > 0 else 0
        avg_time = float(valid_df['processing_time_ms'].mean()) if 'processing_time_ms' in valid_df.columns and len(valid_df) > 0 else 0.0
        total_endpoint_time = float(valid_df['processing_time_ms'].sum()) if 'processing_time_ms' in valid_df.columns else 0.0

        return {
            'api_name': endpoint_name,
            'top1_hit_count': top1_hits,
            'top3_hit_count': top3_hits,
            'top1_accuracy': round(top1_hits / total_samples, 4) if total_samples > 0 else 0.0,
            'top3_accuracy': round(top3_hits / total_samples, 4) if total_samples > 0 else 0.0,
            'avg_response_time_ms': round(avg_time, 2),
            'total_time_ms': round(total_endpoint_time, 2),
            'total_samples': total_samples,
            'total_rows': total_rows,
            'invalid_samples': invalid_samples
        }

    def _rows_from_excel(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """从Excel字节数据中读取行"""
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
            rows = []

            for _, row in df.iterrows():
                # 处理过敏史
                allergies = []
                if 'allergies' in df.columns and pd.notna(row.get('allergies')):
                    allergies_str = str(row['allergies'])
                    allergies = [item.strip() for item in allergies_str.split(',') if item.strip()]

                # 处理合并症
                comorbidities = []
                if 'comorbidities' in df.columns and pd.notna(row.get('comorbidities')):
                    comorbidities_str = str(row['comorbidities'])
                    comorbidities = [item.strip() for item in comorbidities_str.split(',') if item.strip()]

                rows.append({
                    "scenario": row.get('scenarios', '') if pd.notna(row.get('scenarios')) else '',
                    "gold": row.get('gold_answer', '') if pd.notna(row.get('gold_answer')) else '',
                    "patient_info": {
                        "age": row.get('age') if pd.notna(row.get('age')) else '',
                        "gender": row.get('gender') if pd.notna(row.get('gender')) else '',
                        "pregnancy_status": row.get('pregnancy_status') if pd.notna(
                            row.get('pregnancy_status')) else '',
                        "allergies": allergies,
                        "comorbidities": comorbidities,
                        "physical_examination": row.get('physical_examination') if pd.notna(
                            row.get('physical_examination')) else ''
                    },
                    "clinical_context": {
                        "department": row.get('department', '') if pd.notna(row.get('department')) else '',
                        "chief_complaint": row.get('chief_complaint', '') if pd.notna(
                            row.get('chief_complaint')) else '',
                        "medical_history": row.get('medical_history') if pd.notna(row.get('medical_history')) else '',
                        "present_illness": row.get('present_illness') if pd.notna(row.get('present_illness')) else '',
                        "diagnosis": row.get('diagnosis') if pd.notna(row.get('diagnosis')) else '',
                        "symptom_duration": row.get('symptom_duration') if pd.notna(
                            row.get('symptom_duration')) else '',
                        "symptom_severity": row.get('symptom_severity') if pd.notna(
                            row.get('symptom_severity')) else ''
                    }
                })

            return rows
        except Exception as e:
            print(f"读取Excel失败: {e}")
            return []

    def _process_gold_field(self, gold: Any) -> List[str]:
        """处理gold字段，去除*号并包装为列表"""
        if gold is None:
            return []

        # 如果是字符串
        if isinstance(gold, str):
            # 替换各种分隔符为统一分隔符
            gold = gold.replace('；', ';').replace('，', ',').replace('、', ',')

            # 去除*号
            gold = gold.replace('*', '').strip()

            # 按分隔符分割
            items = []
            if ';' in gold:
                items = [item.strip() for item in gold.split(';') if item.strip()]
            elif ',' in gold:
                items = [item.strip() for item in gold.split(',') if item.strip()]
            else:
                items = [gold] if gold else []

            return items

        # 如果是数字
        elif isinstance(gold, (int, float)):
            return [str(gold)]

        # 如果是列表
        elif isinstance(gold, list):
            # 处理列表中的每个元素
            result = []
            for item in gold:
                if isinstance(item, str):
                    result.append(item.replace('*', '').strip())
                else:
                    result.append(str(item))
            return [item for item in result if item]

        # 其他类型转换为字符串
        else:
            return [str(gold).replace('*', '').strip()]

    def build_request_payload(self, endpoint: str, text: str, retr: EvalParams,
                              patient_info: Dict = None, clinical_context: Dict = None,
                              standard_query: str = "") -> Dict[str, Any]:
        """根据endpoint构建请求payload"""
        if endpoint in ["recommend_final_choices", "recommend_simple_final_choices"]:
            search_strategy = SearchStrategy()

            return {
                "patient_info": patient_info or {},
                "clinical_context": clinical_context or {},
                "search_strategy": search_strategy.dict(exclude_none=True),
                "retrieval_strategy": {
                    "enable_reranking": retr.enable_reranking,
                    "need_llm_recommendations": retr.need_llm_recommendations,
                    "apply_rule_filter": retr.apply_rule_filter,
                    "top_scenarios": retr.top_scenarios,
                    "top_recommendations_per_scenario": retr.top_recommendations_per_scenario,
                    "similarity_threshold": retr.similarity_threshold,
                    "min_appropriateness_rating": retr.min_appropriateness_rating,
                },
                "direct_return": False,
                "standard_query": ""
            }

        elif endpoint == "intelligent-recommendation":
            return {
                "clinical_query": text,
                "include_raw_data": retr.include_raw_data,
                "debug_mode": retr.debug_mode,
                "top_scenarios": retr.top_scenarios,
                "top_recommendations_per_scenario": retr.top_recommendations_per_scenario,
                "show_reasoning": retr.show_reasoning,
                "similarity_threshold": 0.4,
                "compute_ragas": retr.compute_ragas,
                "ground_truth": retr.ground_truth,
            }

        elif endpoint == "recommend_item":
            # 构建abstract_history - 主要使用现病史
            abstract_history = (clinical_context.get("present_illness") or
                                clinical_context.get("medical_history") or "")

            return {
                "session_id": f"{random.randint(1, 888)}",
                "patient_id": f"{random.randint(1, 888)}",
                "doctor_id": f"{random.randint(1, 888)}",
                "department": clinical_context.get("department", "内科"),
                "source": "test",
                "patient_sex": patient_info.get("gender") if patient_info.get("gender") else "",
                "patient_age": str(patient_info.get("age")) if patient_info.get("age") else "未知",
                "clinic_info": clinical_context.get("chief_complaint") if clinical_context.get(
                    "chief_complaint") else "",
                "diagnose_name": str(clinical_context.get("diagnosis")) if clinical_context.get("diagnosis") else "",
                "abstract_history": abstract_history,
                "recommend_count": 3
            }

        return {}

    async def post_recommendation_request(self, server_url: str, endpoint: str,
                                          payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送推荐请求"""
        url = f"{server_url}/{endpoint}"
        try:
            timeout = aiohttp.ClientTimeout(total=600)  # 5分钟超时
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        return {"error": f"HTTP {response.status}: {error_text}"}
        except Exception as e:
            return {"error": str(e)}

    async def _process_single_row(self,
                                  server_url: str,
                                  endpoint: str,
                                  endpoint_name: str,
                                  row: Dict[str, Any],
                                  s_num: int,
                                  r_num: int,
                                  enable_reranking: bool,
                                  need_llm_recommendations: bool,
                                  apply_rule_filter: bool,
                                  similarity_threshold: float,
                                  min_appropriateness_rating: int,
                                  show_reasoning: bool,
                                  include_raw_data: bool,
                                  debug_mode: bool,
                                  compute_ragas: bool,
                                  ground_truth: str,
                                  idx: int) -> Dict[str, Any]:
        """处理单行数据的异步函数"""
        text = row["scenario"]
        gold = row["gold"]
        patient_info = row["patient_info"]
        clinical_context = row["clinical_context"]

        # 处理gold字段：去除*号并包装为列表
        gold_processed = self._process_gold_field(gold)

        # 创建RetrievalRequest
        retr_dict = {
            "enable_reranking": enable_reranking,
            "need_llm_recommendations": need_llm_recommendations,
            "apply_rule_filter": apply_rule_filter,
            "top_scenarios": s_num,
            "top_recommendations_per_scenario": r_num,
            "similarity_threshold": similarity_threshold,
            "min_appropriateness_rating": min_appropriateness_rating,
            "show_reasoning": show_reasoning,
            "include_raw_data": include_raw_data,
            "debug_mode": debug_mode,
            "compute_ragas": compute_ragas,
            "ground_truth": ground_truth,
        }
        retr = EvalParams(**retr_dict)

        # 构建请求payload
        payload = self.build_request_payload(
            endpoint_name, text, retr, patient_info, clinical_context, text
        )

        # 发送请求
        start_time = time.time()
        data = await self.post_recommendation_request(server_url, endpoint, payload)
        end_time = time.time()
        processing_time_ms = int((end_time - start_time) * 1000)

        # 提取推荐结果
        fc_groups = extract_recommendations_by_endpoint(endpoint_name, data)

        # 获取预测项目列表
        pred_items = []
        if fc_groups and len(fc_groups) > 0:
            first_group = fc_groups[0]
            if isinstance(first_group, dict) and "final_choices" in first_group:
                pred_items = first_group.get("final_choices", [])
                if isinstance(pred_items, str):
                    pred_items = [pred_items.strip()] if pred_items.strip() else []
            else:
                # 处理其他格式
                pred_items = [str(item) for item in first_group] if isinstance(first_group, list) else []

        # 检查 pred_items 是否为空，判断是否为有效样本
        is_valid_sample = bool(pred_items and len(pred_items) > 0 and pred_items[0] != "")

        # 调用judge_service进行评判
        judge_result = None
        top1_hit_value = 0
        top3_hit_value = 0
        hit_count_value = 0
        hit_items_list = []
        reason = ""

        # 如果 pred_items 为空，跳过模型判定过程，直接标记为无效样本
        if not is_valid_sample:
            reason = "pred_items为空，跳过模型判定"
        else:
            try:
                # 拼装judge_service的请求参数
                judge_request = JudgeRequest(
                    pred_items=pred_items,
                    gold_items=gold_processed,
                    online_model=True,
                    model_judge=True
                )

                # 调用judge_service - 返回的是字典
                response_dict = await self.judge_service.judge_recommendations(
                    judge_request=judge_request
                )

                # 处理评判结果 - 直接使用字典
                judge_result = response_dict.get("judge_result", {})

                # 处理单个JudgeResult或多个JudgeResult的情况
                if isinstance(judge_result, list) and len(judge_result) > 0:
                    judge_result = judge_result[0]  # 取第一个结果

                # 获取命中信息 - 直接从字典中获取
                if judge_result:
                    # 从字典中获取值，注意字段名和类型
                    top1_hit_str = judge_result.get("top1_hit", "0")
                    top3_hit_str = judge_result.get("top3_hit", "0")
                    hit_count_str = judge_result.get("hit_count", "0")

                    # 转换类型
                    top1_hit_value = int(top1_hit_str) if top1_hit_str in ['0', '1'] else 0
                    top3_hit_value = int(top3_hit_str) if top3_hit_str in ['0', '1'] else 0
                    hit_count_value = int(hit_count_str) if hit_count_str and hit_count_str.isdigit() else 0

                    # 获取命中项列表
                    hit_items_list = judge_result.get("hit_items", [])
                    if isinstance(hit_items_list, str):
                        # 如果hit_items是字符串，尝试解析
                        try:
                            hit_items_list = json.loads(hit_items_list)
                        except:
                            hit_items_list = [hit_items_list]

                    # 获取原因
                    reason = judge_result.get("reason", "")

            except Exception as e:
                print(f"调用judge_service失败: {e}")
                # 如果judge_service调用失败，使用简单的命中逻辑
                if pred_items and gold_processed:
                    # 简单的Top1命中判断
                    if pred_items and pred_items[0] in gold_processed:
                        top1_hit_value = 1

                    # 简单的Top3命中判断
                    top3_items = pred_items[:3] if len(pred_items) > 3 else pred_items
                    if any(item in gold_processed for item in top3_items):
                        top3_hit_value = 1

                    # 计算命中数量
                    hit_items_list = [item for item in pred_items if item in gold_processed]
                    hit_count_value = len(hit_items_list)
                    reason = f"简单匹配: Top1命中={top1_hit_value}, Top3命中={top3_hit_value}, 命中{hit_count_value}项"

        # 计算得分
        top1_score = top1_hit_value * 1.0  # top1命中得1分
        top3_score = top3_hit_value * 1.0  # top3命中得1分

        # 综合得分计算：加权平均，可以根据需求调整权重
        # 这里使用70% top1 + 30% top3的权重
        combined_score = 0.7 * top1_score + 0.3 * top3_score

        # 返回该行的结果
        return {
            'row_index': idx + 1,
            'scenario': text,
            'patient_info': json.dumps(patient_info, ensure_ascii=False) if patient_info else "",
            'clinical_context': json.dumps(clinical_context, ensure_ascii=False) if clinical_context else "",
            'gold_original': gold,
            'gold_processed': json.dumps(gold_processed, ensure_ascii=False),
            'pred_items': json.dumps(pred_items, ensure_ascii=False),
            'processing_time_ms': processing_time_ms,
            'is_valid_sample': is_valid_sample,
            'top1_hit': top1_hit_value,
            'top3_hit': top3_hit_value,
            'hit_count': hit_count_value,
            'hit_items': json.dumps(hit_items_list, ensure_ascii=False),
            'top1_score': round(top1_score, 2),
            'top3_score': round(top3_score, 2),
            'combined_score': round(combined_score, 2),
            'judge_reason': reason
        }

    async def evaluate_excel_concurrent(
            self,
            server_url: str,
            endpoint: str,
            endpoint_name: str,
            file_bytes: bytes,
            limit: Optional[int] = None,
            strategy_variants: Optional[List[Tuple[int, int]]] = None,
            enable_reranking: bool = True,
            need_llm_recommendations: bool = True,
            apply_rule_filter: bool = True,
            similarity_threshold: float = 0.4,
            min_appropriateness_rating: int = 4,
            include_raw_data: bool = False,
            debug_mode: bool = False,
            show_reasoning: bool = False,
            compute_ragas: bool = False,
            ground_truth: str = "",
    ) -> Dict[str, Any]:
        """基于Excel的批量评测（并发处理每一行）"""
        # 读取原始Excel文件
        try:
            original_df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            print(f"读取原始Excel失败: {e}")
            return {
                "overall_accuracy": 0.0,
                "overall_top1_accuracy": 0.0,
                "overall_top3_accuracy": 0.0,
                "overall_combined_accuracy": 0.0,
                "average_processing_time_ms": 0,
                "total_samples": 0,
                "variants": [],
                "combination_a": {
                    "accuracy": 0.0,
                    "top1_accuracy": 0.0,
                    "top3_accuracy": 0.0,
                    "combined_accuracy": 0.0,
                    "total_samples": 0,
                    "hit_samples": 0,
                    "details": []
                },
                "combination_b": {
                    "accuracy": 0.0,
                    "top1_accuracy": 0.0,
                    "top3_accuracy": 0.0,
                    "combined_accuracy": 0.0,
                    "total_samples": 0,
                    "hit_samples": 0,
                    "details": []
                },
                "result_excel": b"",
                "result_dataframe": []
            }

        rows = self._rows_from_excel(file_bytes)
        if not rows:
            return {
                "overall_accuracy": 0.0,
                "overall_top1_accuracy": 0.0,
                "overall_top3_accuracy": 0.0,
                "overall_combined_accuracy": 0.0,
                "average_processing_time_ms": 0,
                "total_samples": 0,
                "variants": [],
                "combination_a": {
                    "accuracy": 0.0,
                    "top1_accuracy": 0.0,
                    "top3_accuracy": 0.0,
                    "combined_accuracy": 0.0,
                    "total_samples": 0,
                    "hit_samples": 0,
                    "details": []
                },
                "combination_b": {
                    "accuracy": 0.0,
                    "top1_accuracy": 0.0,
                    "top3_accuracy": 0.0,
                    "combined_accuracy": 0.0,
                    "total_samples": 0,
                    "hit_samples": 0,
                    "details": []
                },
                "result_excel": b"",
                "result_dataframe": []
            }

        if strategy_variants is None:
            strategy_variants = [ (3, 3)]

        # 对于不同接口，调整strategy_variants
        if endpoint == "recommend_simple_final_choices":
            strategy_variants = [(s, r) for (s, r) in strategy_variants if s < 5]

        variants_results = []
        all_processing_times = []
        result_data = []

        for (s_num, r_num) in strategy_variants:
            key = f"top_s{s_num}_top_r{r_num}"

            # 并发处理每一行数据
            rows_to_process = rows[:limit] if limit else rows
            tasks = []
            for idx, row in enumerate(rows_to_process):
                task = self._process_single_row(
                    server_url=server_url,
                    endpoint=endpoint,
                    endpoint_name=endpoint_name,
                    row=row,
                    s_num=s_num,
                    r_num=r_num,
                    enable_reranking=enable_reranking,
                    need_llm_recommendations=need_llm_recommendations,
                    apply_rule_filter=apply_rule_filter,
                    similarity_threshold=similarity_threshold,
                    min_appropriateness_rating=min_appropriateness_rating,
                    show_reasoning=show_reasoning,
                    include_raw_data=include_raw_data,
                    debug_mode=debug_mode,
                    compute_ragas=compute_ragas,
                    ground_truth=ground_truth,
                    idx=idx
                )
                tasks.append(task)

            # 使用信号量控制并发数
            semaphore = asyncio.Semaphore(self.max_concurrent_per_endpoint)

            async def bounded_task(task):
                async with semaphore:
                    return await task

            bounded_tasks = [bounded_task(task) for task in tasks]

            # 并发执行所有任务
            variant_results = await asyncio.gather(*bounded_tasks, return_exceptions=True)

            # 处理结果
            variant_details = []
            variant_processing_times = []

            top1_hits = 0
            top3_hits = 0
            total_hit_count = 0
            total_samples = 0  # 只计算有效样本（final_choices 不为空）
            total_rows = len(rows_to_process)  # 总行数

            for idx, result in enumerate(variant_results):
                if isinstance(result, Exception):
                    print(f"处理第{idx + 1}行数据时发生错误: {result}")
                    # 添加错误记录
                    detail = {
                        'row_index': idx + 1,
                        'scenario': rows[idx]["scenario"],
                        'error': str(result),
                        'top1_hit': 0,
                        'top3_hit': 0,
                        'hit_count': 0,
                        'processing_time_ms': 0,
                        'variant': key,
                        'is_valid_sample': False  # 标记为无效样本
                    }
                    variant_details.append(detail)
                    result_data.append(detail)
                    continue

                detail = {**result, 'variant': key}

                # 检查 pred_items 是否为空
                pred_items_str = detail.get('pred_items', '[]')
                try:
                    pred_items = json.loads(pred_items_str) if isinstance(pred_items_str, str) else pred_items_str
                    is_valid = bool(pred_items and len(pred_items) > 0 and pred_items[0] != "")
                except:
                    is_valid = False

                detail['is_valid_sample'] = is_valid
                variant_details.append(detail)
                result_data.append(detail)

                # 只有有效样本才计入统计
                if is_valid:
                    total_samples += 1
                    top1_hits += detail['top1_hit']
                    top3_hits += detail['top3_hit']
                    total_hit_count += detail['hit_count']
                    variant_processing_times.append(detail['processing_time_ms'])
                    all_processing_times.append(detail['processing_time_ms'])

            # 计算该variant的准确率（基于有效样本数）
            top1_accuracy = top1_hits / total_samples if total_samples > 0 else 0
            top3_accuracy = top3_hits / total_samples if total_samples > 0 else 0
            avg_hit_count = total_hit_count / total_samples if total_samples > 0 else 0
            avg_processing_time = np.mean(variant_processing_times) if variant_processing_times else 0

            # 计算综合准确率
            combined_accuracy = 0.7 * top1_accuracy + 0.3 * top3_accuracy

            variant_result = {
                'variant_name': key,
                'top1_accuracy': round(top1_accuracy, 4),
                'top3_accuracy': round(top3_accuracy, 4),
                'combined_accuracy': round(combined_accuracy, 4),
                'average_hit_count': round(avg_hit_count, 2),
                'average_processing_time_ms': round(avg_processing_time, 2),
                'total_samples': total_samples,  # 有效样本数
                'total_rows': total_rows,  # 总行数
                'invalid_samples': total_rows - total_samples,  # 无效样本数
                'top1_hits': top1_hits,
                'top3_hits': top3_hits,
                'total_hit_count': total_hit_count,
                'details': variant_details
            }

            variants_results.append(variant_result)

        # 计算整体统计信息
        if all_processing_times:
            avg_processing_time_overall = np.mean(all_processing_times)
        else:
            avg_processing_time_overall = 0

        # 计算总体准确率（取所有variant的平均值）
        if variants_results:
            overall_top1_accuracy = np.mean([v['top1_accuracy'] for v in variants_results])
            overall_top3_accuracy = np.mean([v['top3_accuracy'] for v in variants_results])
            overall_combined_accuracy = np.mean([v['combined_accuracy'] for v in variants_results])
            overall_accuracy = overall_top1_accuracy  # 保持向后兼容
        else:
            overall_top1_accuracy = 0
            overall_top3_accuracy = 0
            overall_combined_accuracy = 0
            overall_accuracy = 0

        # 设置combination_a和combination_b（取前两个variant）
        combination_a = {}
        combination_b = {}

        if len(variants_results) >= 1:
            v = variants_results[0]
            combination_a = {
                "accuracy": v['top1_accuracy'],
                "top1_accuracy": v['top1_accuracy'],
                "top3_accuracy": v['top3_accuracy'],
                "combined_accuracy": v['combined_accuracy'],
                "total_samples": v['total_samples'],
                "hit_samples": v['top1_hits'],
                "top3_hit_samples": v['top3_hits'],
                "average_processing_time_ms": v['average_processing_time_ms'],
                "details": v['details'][:10]  # 只取前10个详细结果
            }

        if len(variants_results) >= 2:
            v = variants_results[1]
            combination_b = {
                "accuracy": v['top1_accuracy'],
                "top1_accuracy": v['top1_accuracy'],
                "top3_accuracy": v['top3_accuracy'],
                "combined_accuracy": v['combined_accuracy'],
                "total_samples": v['total_samples'],
                "hit_samples": v['top1_hits'],
                "top3_hit_samples": v['top3_hits'],
                "average_processing_time_ms": v['average_processing_time_ms'],
                "details": v['details'][:10]  # 只取前10个详细结果
            }

        # 创建结果DataFrame
        result_df = pd.DataFrame(result_data)

        # 保存结果到Excel（包含原始内容）
        output_excel_bytes = self._create_result_excel(
            original_df=original_df,
            result_df=result_df,
            rows=rows,
            variants_results=variants_results,
            overall_top1_accuracy=overall_top1_accuracy,
            overall_top3_accuracy=overall_top3_accuracy,
            overall_combined_accuracy=overall_combined_accuracy,
            avg_processing_time_overall=avg_processing_time_overall
        )

        return {
            "overall_accuracy": overall_accuracy,
            "overall_top1_accuracy": overall_top1_accuracy,
            "overall_top3_accuracy": overall_top3_accuracy,
            "overall_combined_accuracy": overall_combined_accuracy,
            "average_processing_time_ms": avg_processing_time_overall,
            "total_samples": len(rows),
            "variants": variants_results,
            "combination_a": combination_a,
            "combination_b": combination_b,
            "result_excel": output_excel_bytes,
            "result_dataframe": result_df.to_dict('records')
        }

    async def evaluate_all_endpoints_concurrent(
            self,
            file_bytes: bytes,
            limit: Optional[int] = None,
            top_scenarios: int = 3,
            top_recommendations_per_scenario: int = 3,
            similarity_threshold: float = 0.4,
            min_appropriateness_rating: int = 4,
            progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """并发评估所有4个接口并返回汇总结果（纯异步架构，单event loop）"""

        # 报告初始进度
        if progress_callback:
            progress_callback(0, len(self.eval_config), "开始评测...")

        # 创建所有评测任务（纯异步，无需线程池）
        async def evaluate_single_with_progress(config: Dict[str, Any], index: int) -> tuple:
            """评测单个接口并报告进度"""
            endpoint_name = config["name"]
            try:
                result = await self.evaluate_excel_concurrent(
                    server_url=config["server_url"],
                    endpoint=config["endpoint"],
                    endpoint_name=endpoint_name,
                    file_bytes=file_bytes,
                    limit=limit,
                    strategy_variants=[(top_scenarios, top_recommendations_per_scenario)],
                    enable_reranking=True,
                    need_llm_recommendations=True,
                    apply_rule_filter=True,
                    similarity_threshold=similarity_threshold,
                    min_appropriateness_rating=min_appropriateness_rating,
                    show_reasoning=False,
                    include_raw_data=False,
                    debug_mode=False,
                    compute_ragas=False,
                    ground_truth="",
                )
                if progress_callback:
                    progress_callback(index + 1, len(self.eval_config), f"已完成 {endpoint_name}")
                return (endpoint_name, result, None)
            except Exception as e:
                if progress_callback:
                    progress_callback(index + 1, len(self.eval_config), f"{endpoint_name} 失败: {str(e)}")
                return (endpoint_name, None, e)

        # 使用 asyncio.gather 并发执行所有接口评测（第一层并发）
        # 每个接口内部使用 Semaphore 控制单行并发（第二层并发）
        tasks = [
            evaluate_single_with_progress(config, idx)
            for idx, config in enumerate(self.eval_config)
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=False)

        # 整理结果
        all_results = {}
        successful_results = []

        for endpoint_name, result, error in results_list:
            if error:
                all_results[endpoint_name] = {
                    "error": str(error),
                    "status": "failed"
                }
            elif result and "error" in result:
                all_results[endpoint_name] = {
                    "error": result["error"],
                    "status": "failed"
                }
            else:
                all_results[endpoint_name] = {
                    "status": "success",
                    "result": result
                }
                successful_results.append(result)

        # 计算总体统计
        if successful_results:
            # 从第一个成功的结果中获取 total_samples，避免重复解析Excel
            total_samples = successful_results[0].get('total_samples', 0)

            # 计算平均准确率
            avg_overall_accuracy = sum(r["overall_accuracy"] for r in successful_results) / len(successful_results)
            avg_top1_accuracy = sum(r["overall_top1_accuracy"] for r in successful_results) / len(successful_results)
            avg_top3_accuracy = sum(r["overall_top3_accuracy"] for r in successful_results) / len(successful_results)
            avg_combined_accuracy = sum(r["overall_combined_accuracy"] for r in successful_results) / len(
                successful_results)

            # 计算平均处理时间
            avg_processing_time = sum(r["average_processing_time_ms"] for r in successful_results) / len(
                successful_results)
        else:
            total_samples = 0
            avg_overall_accuracy = 0.0
            avg_top1_accuracy = 0.0
            avg_top3_accuracy = 0.0
            avg_combined_accuracy = 0.0
            avg_processing_time = 0

        summary = {
            "total_endpoints_tested": len(self.eval_config),
            "successful_endpoints": len(successful_results),
            "failed_endpoints": len(self.eval_config) - len(successful_results),
            "average_overall_accuracy": avg_overall_accuracy,
            "average_top1_accuracy": avg_top1_accuracy,
            "average_top3_accuracy": avg_top3_accuracy,
            "average_combined_accuracy": avg_combined_accuracy,
            "average_processing_time_ms": int(avg_processing_time),
            "total_samples": total_samples,
            "concurrent_per_endpoint": self.max_concurrent_per_endpoint,
        }

        # 保存评测结果到Excel
        final_result_excel = self._create_final_summary_excel(all_results, summary, file_bytes)

        # 生成接口汇总数据（用于前端显示）- 使用公共方法去除冗余
        endpoint_summary = []
        for endpoint_name, result in all_results.items():
            if result.get('status') == 'success':
                endpoint_result = result.get('result', {})
                result_df_data = endpoint_result.get('result_dataframe', [])
                if result_df_data:
                    stats = self._calculate_endpoint_statistics(result_df_data, endpoint_name)
                    endpoint_summary.append(stats)

        return {
            "summary": summary,
            "endpoint_summary": endpoint_summary,
            "result_excel": final_result_excel,
        }

    def _create_result_excel(self, original_df: pd.DataFrame, result_df: pd.DataFrame,
                             rows: List[Dict], variants_results: List[Dict],
                             overall_top1_accuracy: float, overall_top3_accuracy: float,
                             overall_combined_accuracy: float, avg_processing_time_overall: float) -> bytes:
        """创建包含评测结果的Excel文件"""
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 1. 原始数据Sheet
            original_df.to_excel(writer, sheet_name='原始数据', index=False)

            # 2. 详细结果Sheet
            result_df.to_excel(writer, sheet_name='详细结果', index=False)

            # 3. 汇总统计Sheet
            summary_data = {
                '指标': [
                    '评测时间', '总样本数', '测试变体数',
                    '总体Top1准确率', '总体Top3准确率', '总体综合准确率',
                    '平均处理时间(毫秒)', '最大处理时间(毫秒)', '最小处理时间(毫秒)'
                ],
                '值': [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    len(rows),
                    len(variants_results),
                    f"{overall_top1_accuracy:.2%}",
                    f"{overall_top3_accuracy:.2%}",
                    f"{overall_combined_accuracy:.2%}",
                    f"{avg_processing_time_overall:.2f}",
                    f"{max(result_df['processing_time_ms']) if 'processing_time_ms' in result_df.columns and len(result_df) > 0 else 0}",
                    f"{min(result_df['processing_time_ms']) if 'processing_time_ms' in result_df.columns and len(result_df) > 0 else 0}"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='汇总统计', index=False)

            # 4. 变体对比Sheet
            variant_data = []
            for v in variants_results:
                variant_data.append({
                    '变体名称': v['variant_name'],
                    'Top1准确率': f"{v['top1_accuracy']:.2%}",
                    'Top3准确率': f"{v['top3_accuracy']:.2%}",
                    '综合准确率': f"{v['combined_accuracy']:.2%}",
                    '平均命中数': v['average_hit_count'],
                    '平均处理时间(毫秒)': v['average_processing_time_ms'],
                    '总样本数': v['total_samples'],
                    'Top1命中数': v['top1_hits'],
                    'Top3命中数': v['top3_hits']
                })
            variant_df = pd.DataFrame(variant_data)
            variant_df.to_excel(writer, sheet_name='变体对比', index=False)

            # 5. Top1命中分析Sheet
            if 'top1_hit' in result_df.columns:
                top1_stats = {
                    '指标': ['Top1总命中数', 'Top1总未命中数', 'Top1命中率', 'Top1平均得分'],
                    '值': [
                        int(result_df['top1_hit'].sum()),
                        int(len(result_df) - result_df['top1_hit'].sum()),
                        f"{result_df['top1_hit'].mean():.2%}",
                        f"{result_df['top1_score'].mean():.2f}" if 'top1_score' in result_df.columns else "N/A"
                    ]
                }
                top1_df = pd.DataFrame(top1_stats)
                top1_df.to_excel(writer, sheet_name='Top1分析', index=False)

            # 6. Top3命中分析Sheet
            if 'top3_hit' in result_df.columns:
                top3_stats = {
                    '指标': ['Top3总命中数', 'Top3总未命中数', 'Top3命中率', 'Top3平均得分'],
                    '值': [
                        int(result_df['top3_hit'].sum()),
                        int(len(result_df) - result_df['top3_hit'].sum()),
                        f"{result_df['top3_hit'].mean():.2%}",
                        f"{result_df['top3_score'].mean():.2f}" if 'top3_score' in result_df.columns else "N/A"
                    ]
                }
                top3_df = pd.DataFrame(top3_stats)
                top3_df.to_excel(writer, sheet_name='Top3分析', index=False)

        output.seek(0)
        return output.getvalue()

    def _create_final_summary_excel(self, all_results: Dict[str, Any], summary: Dict[str, Any],
                                    file_bytes: bytes) -> bytes:
        """创建最终汇总的Excel文件（5个sheet）"""
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 读取原始数据
            try:
                original_df = pd.read_excel(io.BytesIO(file_bytes))
            except:
                original_df = pd.DataFrame()

            # Sheet 1-4: 每个接口的详细结果
            sheet_index = 1
            for endpoint_name, result in all_results.items():
                if result.get('status') == 'success':
                    endpoint_result = result.get('result', {})
                    result_data = endpoint_result.get('result_dataframe', [])

                    if result_data:
                        # 构建每行数据，包含原始数据字段和扩充字段
                        rows = []
                        for item in result_data:
                            row = {}
                            # 从原始Excel获取所有字段
                            if 'scenario' in item:
                                row['scenarios'] = item['scenario']
                            if 'gold_original' in item:
                                row['gold_answer'] = item['gold_original']
                            if 'patient_info' in item:
                                try:
                                    patient_info = json.loads(item['patient_info']) if isinstance(item['patient_info'], str) else item['patient_info']
                                    row['age'] = patient_info.get('age', '')
                                    row['gender'] = patient_info.get('gender', '')
                                    row['pregnancy_status'] = patient_info.get('pregnancy_status', '')
                                    row['allergies'] = ','.join(patient_info.get('allergies', [])) if isinstance(patient_info.get('allergies'), list) else patient_info.get('allergies', '')
                                    row['comorbidities'] = ','.join(patient_info.get('comorbidities', [])) if isinstance(patient_info.get('comorbidities'), list) else patient_info.get('comorbidities', '')
                                    row['physical_examination'] = patient_info.get('physical_examination', '')
                                except:
                                    pass
                            if 'clinical_context' in item:
                                try:
                                    clinical_context = json.loads(item['clinical_context']) if isinstance(item['clinical_context'], str) else item['clinical_context']
                                    row['department'] = clinical_context.get('department', '')
                                    row['chief_complaint'] = clinical_context.get('chief_complaint', '')
                                    row['medical_history'] = clinical_context.get('medical_history', '')
                                    row['present_illness'] = clinical_context.get('present_illness', '')
                                    row['diagnosis'] = clinical_context.get('diagnosis', '')
                                    row['symptom_duration'] = clinical_context.get('symptom_duration', '')
                                    row['symptom_severity'] = clinical_context.get('symptom_severity', '')
                                except:
                                    pass

                            # 扩充字段
                            row['api_name'] = endpoint_name
                            row['final_choices'] = item.get('pred_items', '')
                            row['is_valid_sample'] = item.get('is_valid_sample', True)  # 添加有效性标记
                            row['top1_hit'] = item.get('top1_hit', 0)
                            row['top3_hit'] = item.get('top3_hit', 0)
                            row['top1_accuracy'] = item.get('top1_hit', 0)
                            row['top3_accuracy'] = item.get('top3_hit', 0)
                            row['response_time_ms'] = item.get('processing_time_ms', 0)

                            rows.append(row)

                        result_df = pd.DataFrame(rows)

                        # 计算汇总行统计数据 - 使用公共方法去除冗余
                        stats = self._calculate_endpoint_statistics(rows, endpoint_name)

                        # 添加汇总行
                        summary_row = {col: '' for col in result_df.columns}
                        summary_row.update({
                            'scenarios': f'top1_hits={stats["top1_hit_count"]}',
                            'gold_answer': f'top3_hits={stats["top3_hit_count"]}',
                            'api_name': f'top1_accuracy={stats["top1_accuracy"]}',
                            'final_choices': f'top3_accuracy={stats["top3_accuracy"]}',
                            'is_valid_sample': f'valid={stats["total_samples"]}, invalid={stats["invalid_samples"]}',
                            'top1_hit': '',
                            'top3_hit': '',
                            'top1_accuracy': '',
                            'top3_accuracy': '',
                            'response_time_ms': f'avg_time={stats["avg_response_time_ms"]}ms'
                        })
                        result_df = pd.concat([result_df, pd.DataFrame([summary_row])], ignore_index=True)

                        result_df.to_excel(writer, sheet_name=f'Sheet{sheet_index}_{endpoint_name[:20]}', index=False)
                        sheet_index += 1

            # Sheet 5: 接口汇总（只有4行，每个接口一行）- 使用公共方法去除冗余
            endpoint_summary = []
            for endpoint_name, result in all_results.items():
                if result.get('status') == 'success':
                    endpoint_result = result.get('result', {})
                    result_df_data = endpoint_result.get('result_dataframe', [])
                    if result_df_data:
                        stats = self._calculate_endpoint_statistics(result_df_data, endpoint_name)
                        endpoint_summary.append(stats)

            summary_df = pd.DataFrame(endpoint_summary)
            summary_df.to_excel(writer, sheet_name='Sheet5_Summary', index=False)

        output.seek(0)
        return output.getvalue()

    async def get_excel_preview(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """获取Excel预览数据（异步）"""
        try:
            # 使用 asyncio.to_thread 在线程池中执行同步IO操作
            import asyncio
            df = await asyncio.to_thread(pd.read_excel, io.BytesIO(file_bytes))
            return df.head(100).to_dict('records')
        except Exception as e:
            print(f"读取Excel预览失败: {e}")
            return []

    def submit_evaluation_task(
        self,
        file_bytes: bytes,
        limit: Optional[int] = None,
        top_scenarios: int = 3,
        top_recommendations_per_scenario: int = 3,
        similarity_threshold: float = 0.7,
        min_appropriateness_rating: int = 5,
    ) -> str:
        """提交评测任务到Celery"""
        from app.celery.tasks.evaluation_tasks import evaluate_all_endpoints_task
        import os

        os.makedirs("output_eval", exist_ok=True)

        task = evaluate_all_endpoints_task.delay(
            file_bytes=file_bytes,
            limit=limit,
            top_scenarios=top_scenarios,
            top_recommendations_per_scenario=top_recommendations_per_scenario,
            similarity_threshold=similarity_threshold,
            min_appropriateness_rating=min_appropriateness_rating,
        )
        return task.id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        from celery.result import AsyncResult

        task_result = AsyncResult(task_id)

        if task_result.state == 'PENDING':
            return {"task_id": task_id, "status": "pending", "message": "任务等待执行中"}
        elif task_result.state == 'STARTED':
            return {"task_id": task_id, "status": "started", "message": "任务执行中"}
        elif task_result.state == 'PROGRESS':
            # 返回进度信息
            progress_info = task_result.info or {}
            return {
                "task_id": task_id,
                "status": "progress",
                "message": progress_info.get("message", "任务进行中"),
                "progress": {
                    "completed": progress_info.get("completed", 0),
                    "total": progress_info.get("total", 0),
                    "percentage": progress_info.get("percentage", 0)
                }
            }
        elif task_result.state == 'SUCCESS':
            return {"task_id": task_id, "status": "success", "result": task_result.result, "message": "任务执行成功"}
        elif task_result.state == 'FAILURE':
            return {"task_id": task_id, "status": "failure", "error": str(task_result.info), "message": "任务执行失败"}
        else:
            return {"task_id": task_id, "status": task_result.state.lower(), "message": f"任务状态: {task_result.state}"}

def normalize_text(text: str) -> str:
    """标准化文本，去除空格和特殊字符"""
    if not text:
        return ""
    return ''.join(text.split()).lower()

def _hit(group: List[str], gold: str) -> int:
    """检查推荐组中是否包含正确答案"""
    gold_norm = normalize_text(gold)
    for rec in group:
        if normalize_text(rec) == gold_norm:
            return 1
    return 0

def extract_recommendations_by_endpoint(endpoint: str, data: Dict[str, Any]) -> List[dict]:
    """根据不同接口提取推荐结果"""
    if endpoint in ["recommend_final_choices", "recommend_simple_final_choices"]:
        # 提取fc_groups中的推荐项
        fc_groups = data.get("Data", {}).get("best_recommendations", [])
        recommendations = []
        for group in fc_groups:
            if isinstance(group, dict) and "final_choices" in group:
                if isinstance(group['final_choices'], list):
                    final_choices = list(group['final_choices'])
                else:
                    final_choices = []
                overall_reason = group.get('overall_reasoning', '')
                recommendations.append({"final_choices": final_choices, "overall_reason": overall_reason})
            else:
                # 如果是字符串列表
                recommendations.append({"overall_reason": '', "final_choices": []})
        return recommendations

    elif endpoint == "intelligent-recommendation":
        llm_recommendations = data.get("llm_recommendations", {})
        recommendations_list = llm_recommendations.get("recommendations", [])
        scenario = data.get("query", "")
        final_choices = []

        for recommend in recommendations_list:
            if isinstance(recommend, dict):
                procedure_name = recommend.get("procedure_name", "")
                if procedure_name:
                    final_choices.append(procedure_name)

        recommendations = [{"scenario_description": scenario, "final_choices": final_choices}]
        return recommendations

    elif endpoint == "recommend_item":
        # 根据您的测试，这个接口返回的应该是recommend_item
        recommendations = data.get("data", [])
        choices = []
        if recommendations:
           for recommend in recommendations:
               if isinstance(recommend, dict):
                   choices.append(recommend.get('check_item_name', ""))
        return [{"final_choices": choices}]

    return []