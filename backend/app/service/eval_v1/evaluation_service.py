from typing import Optional, List, Dict, Any, Tuple
import io
import json
import re
import pandas as pd
import httpx
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os

from app.schema.IntelligentRecommendation_schemas import (
    PatientInfo,
    ClinicalContext,
    RetrievalRequest,
)


def normalize_text(text: Optional[str]) -> str:
    """安全去空与去首尾空白，用于统一比较与显示。"""
    return (text or "").strip()


def extract_final_choices(best_recommendations: Any) -> List[List[str]]:
    """从推荐接口返回结构中提取每个场景的 final_choices 列表。"""
    if not isinstance(best_recommendations, list):
        return []
    results: List[List[str]] = []
    for scene in best_recommendations:
        if isinstance(scene, dict):
            choices = scene.get("final_choices")
            if isinstance(choices, list):
                results.append([c for c in choices if isinstance(c, str)])
            else:
                results.append([])
        else:
            results.append([])
    return results


def extract_recommendations_by_endpoint(endpoint: str, response_data: Dict[str, Any]) -> List[List[str]]:
    """根据不同接口从响应中提取推荐结果"""
    if endpoint in ["recommend", "recommend-simple"]:
        # 从best_recommendations提取final_choices
        return extract_final_choices(response_data.get("best_recommendations", []))

    elif endpoint == "intelligent-recommendation":
        # intelligent-recommendation接口的数据结构
        llm_recs = response_data.get("llm_recommendations", {})
        if llm_recs:
            recommendations = llm_recs.get("recommendations", [])
            # 提取procedure_name作为推荐项目
            return [[rec.get("procedure_name", "") for rec in recommendations if rec.get("procedure_name")]]
        return []

    elif endpoint == "recommend_item_with_reason":
        # recommend_item_with_reason是流式接口，返回的check_item_name
        # 这里假设已经处理完流式数据
        if "check_item_names" in response_data:
            return [response_data["check_item_names"]]
        return []

    return []


def is_gold_hit_in_choices(choices: List[str], gold_answer: str) -> int:
    """判断标准答案是否命中于某个场景的推荐集合（final_choices）。"""
    gold = normalize_text(gold_answer)
    if not gold:
        return 0
    normalized = [normalize_text(x) for x in choices]
    return 1 if gold in normalized else 0


# 为兼容性添加_hit别名
_hit = is_gold_hit_in_choices


class EvaluationService:
    """评测服务：通过 HTTP 直连被测后端 URL，执行推荐接口并统计命中率。"""

    def __init__(self):
        pass

    async def post_recommendation_request(self, server_url: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用被测后端的推荐接口并返回 Data 节点内容。"""
        # 构建完整URL
        if endpoint == "recommend":
            url = server_url.rstrip("/") + "/api/v1/acrac-code/recommend"
        elif endpoint == "recommend-simple":
            url = server_url.rstrip("/") + "/api/v1/acrac-code/simple-recommend"
        elif endpoint == "intelligent-recommendation":
            url = server_url.rstrip("/") + "/api/v1/acrac/rag-llm/intelligent-recommendation"
        elif endpoint == "recommend_item_with_reason":
            url = server_url.rstrip("/") + "/rimagai/checkitem/recommend_item_with_reason"
        else:
            raise ValueError(f"Unsupported endpoint: {endpoint}")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        # 根据不同接口返回不同的数据结构
        if endpoint in ["recommend", "recommend-simple"]:
            return body.get("Data", {})
        elif endpoint == "intelligent-recommendation":
            return body  # 直接返回整个响应体
        elif endpoint == "recommend_item_with_reason":
            # 流式接口需要特殊处理
            return body
        return body.get("Data", {})

    def build_request_payload(
        self,
        endpoint: str,
        scenario_text: str,
        retrieval: RetrievalRequest,
        standard_query: Optional[str] = None,
        patient_info: Optional[str] = None,
        clinical_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构造被测后端推荐接口的请求载荷。"""
        if endpoint in ["recommend", "recommend-simple"]:
            # recommend和recommend-simple接口
            if patient_info and clinical_context:
                # 使用提供的patient_info和clinical_context
                try:
                    patient_dict = json.loads(patient_info)
                    clinical_dict = json.loads(clinical_context)
                except:
                    patient_dict = PatientInfo().model_dump()
                    clinical_dict = ClinicalContext(
                        department="影像科",
                        chief_complaint=scenario_text,
                    ).model_dump()
            else:
                patient_dict = PatientInfo().model_dump()
                clinical_dict = ClinicalContext(
                    department="影像科",
                    chief_complaint=scenario_text,
                ).model_dump()

            return {
                "patient_info": patient_dict,
                "clinical_context": clinical_dict,
                "search_strategy": None,
                "retrieval_strategy": retrieval.model_dump(),
                "direct_return": True,
                "standard_query": standard_query or "",
            }

        elif endpoint == "intelligent-recommendation":
            # intelligent-recommendation接口
            return {
                "clinical_query": standard_query or scenario_text,
                "include_raw_data": retrieval.include_raw_data if hasattr(retrieval, 'include_raw_data') else False,
                "debug_mode": retrieval.debug_mode if hasattr(retrieval, 'debug_mode') else False,
                "top_scenarios": retrieval.top_scenarios,
                "top_recommendations_per_scenario": retrieval.top_recommendations_per_scenario,
                "show_reasoning": retrieval.show_reasoning if hasattr(retrieval, 'show_reasoning') else True,
                "similarity_threshold": retrieval.similarity_threshold,
                "compute_ragas": retrieval.compute_ragas if hasattr(retrieval, 'compute_ragas') else False,
                "ground_truth": retrieval.ground_truth if hasattr(retrieval, 'ground_truth') else "",
            }

        elif endpoint == "recommend_item_with_reason":
            # recommend_item_with_reason接口 - 需要从scenario_text中提取信息
            # 使用正则匹配提取年龄、性别等信息
            age_match = re.search(r'(\d+)岁', scenario_text)
            gender_match = re.search(r'(男性?|女性?)', scenario_text)

            age = age_match.group(1) if age_match else "35"
            gender = "男" if gender_match and "男" in gender_match.group(1) else "女"

            # 提取除了年龄和性别之外的其他文本内容作为clinic_info
            clinic_info = scenario_text
            if scenario_text:
                # 尝试去除年龄和性别信息，保留其他症状描述
                temp_text = scenario_text
                # 去除年龄信息，如"45岁"、"35岁男性"等
                temp_text = re.sub(r'\d+岁', '', temp_text)
                # 去除性别信息
                temp_text = re.sub(r'(男性?|女性?)', '', temp_text)
                # 去除多余的标点符号和空格
                temp_text = re.sub(r'^[，。、\s]+', '', temp_text)
                temp_text = re.sub(r'[，。、\s]+$', '', temp_text)
                temp_text = temp_text.strip()

                # 如果提取出的文本太短（少于5个字符），说明提取不完整，使用原始文本
                if len(temp_text) >= 5:
                    clinic_info = temp_text
                else:
                    clinic_info = scenario_text

            # 从clinical_context中提取department和diagnosis
            department = "神经科"  # 默认值
            diagnosis = "无"  # 默认值
            history = "无"  # 默认值

            if clinical_context:
                try:
                    clinical_dict = json.loads(clinical_context)
                    department = clinical_dict.get("department", "神经科")
                    diagnosis = clinical_dict.get("diagnosis", "无")
                    medical_history = clinical_dict.get("medical_history", "")
                    present_illness = clinical_dict.get("present_illness", "")
                    history = f"{medical_history} {present_illness}".strip() if medical_history or present_illness else "无"
                except:
                    pass

            import random
            return {
                "session_id": str(random.randint(100000, 999999)),
                "patient_id": str(random.randint(100000, 999999)),
                "doctor_id": str(random.randint(100000, 999999)),
                "department": department,
                "source": "127.0.0.1",
                "patient_sex": gender,
                "patient_age": f"{age}岁",
                "clinic_info": clinic_info,
                "diagnose_name": diagnosis,
                "abstract_history": history,
                "recommend_count": retrieval.top_recommendations_per_scenario,
            }

        return {}

    def \
            _rows_from_excel(self, file_bytes: bytes) -> List[Dict[str, str]]:
        """从 Excel 中提取评测样本：临床场景文本与标准答案。"""
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        cols = {str(c).strip(): c for c in df.columns}
        scenario_col = None
        answer_col = None
        for k in cols.keys():
            if "临床场景" in k:
                scenario_col = cols[k]
            if "首选检查项目" in k and "标准化" in k:
                answer_col = cols[k]
        if scenario_col is None or answer_col is None:
            return []
        samples: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            scenario_text = normalize_text(row.get(scenario_col))
            gold_answer = normalize_text(row.get(answer_col))
            if scenario_text:
                samples.append({"scenario": scenario_text, "gold": gold_answer})
        return samples

    async def evaluate_excel(
        self,
        server_url: str,
        endpoint: str,
        file_bytes: bytes,
        strategy_variants: Optional[List[Tuple[int,int]]] = None,
        enable_reranking: bool = True,
        need_llm_recommendations: bool = True,
        apply_rule_filter: bool = True,
        similarity_threshold: float = 0.6,
        min_appropriateness_rating: int = 5,
        include_raw_data: bool = False,
        debug_mode: bool = False,
        show_reasoning: bool = False,
        compute_ragas: bool = False,
        ground_truth: str = "",
    ) -> Dict[str, Any]:
        """基于 Excel 的批量评测：对多组合(top@k)进行横向统计并输出 A/B 与 variants。"""
        rows = self._rows_from_excel(file_bytes)
        if strategy_variants is None:
            strategy_variants = [(1,1),(1,3),(3,1),(3,3)]
        if endpoint == "recommend-simple":
            strategy_variants = [(s,r) for (s,r) in strategy_variants if s < 5]

        variants_results = []
        details_map: Dict[str, List[Dict[str, Any]]] = {}
        acc_map: Dict[str, float] = {}
        ms_all: List[int] = []

        for (s_num, r_num) in strategy_variants:
            key = f"top_s{s_num}_top_r{r_num}"
            details: List[Dict[str, Any]] = []
            for r in rows:
                text = r["scenario"]
                gold = r["gold"]

                # 创建RetrievalRequest，添加intelligent-recommendation需要的字段
                retr_dict = {
                    "enable_reranking": enable_reranking,
                    "need_llm_recommendations": need_llm_recommendations,
                    "apply_rule_filter": apply_rule_filter,
                    "top_scenarios": s_num,
                    "top_recommendations_per_scenario": r_num,
                    "similarity_threshold": similarity_threshold,
                    "min_appropriateness_rating": min_appropriateness_rating,
                }
                retr = RetrievalRequest(**retr_dict)

                # 动态添加额外字段
                retr.show_reasoning = show_reasoning
                retr.include_raw_data = include_raw_data
                retr.debug_mode = debug_mode
                retr.compute_ragas = compute_ragas
                retr.ground_truth = ground_truth

                payload = self.build_request_payload(endpoint, text, retr, standard_query=text)
                data = await self.post_recommendation_request(server_url, endpoint, payload)

                # 根据不同接口提取推荐结果
                fc_groups = extract_recommendations_by_endpoint(endpoint, data)

                # 获取处理时间
                ms = 0
                if endpoint in ["recommend", "recommend-simple"]:
                    ms = data.get("processing_time_ms", 0)
                elif endpoint == "intelligent-recommendation":
                    ms = data.get("processing_time_ms", 0)

                per_hits = [ _hit(group, gold) for group in fc_groups[:s_num] ]
                if s_num == 1 and r_num == 1:
                    final = fc_groups[0] if fc_groups else []
                    hit = 1 if final and normalize_text(gold) == normalize_text(final[0]) else 0
                    details.append({
                        "clinical_scenario": text,
                        "standard_answer": gold,
                        "recommendations": final,
                        "per_scenario_hits": per_hits,
                        "hit": bool(hit),
                        "processing_time_ms": ms,
                    })
                else:
                    hit = 1 if any(per_hits) else 0
                    details.append({
                        "clinical_scenario": text,
                        "standard_answer": gold,
                        "recommendations": fc_groups,
                        "per_scenario_hits": per_hits,
                        "hit": bool(hit),
                        "processing_time_ms": ms,
                    })
            total = len(details)
            hit_cnt = sum(1 for d in details if d.get("hit"))
            acc = (hit_cnt / total) if total else 0.0
            details_map[key] = details
            acc_map[key] = acc
            ms_all.extend([d.get("processing_time_ms",0) for d in details])
            variants_results.append({
                "label": key,
                "accuracy": acc,
                "total_samples": total,
                "hit_samples": hit_cnt,
                "details": details,
            })

        avg_ms = int(sum(ms_all)/len(ms_all)) if ms_all else 0
        acc_a = acc_map.get("top_s1_top_r1", 0.0)
        acc_b = acc_map.get("top_s3_top_r3", 0.0)
        details_a = details_map.get("top_s1_top_r1", [])
        details_b = details_map.get("top_s3_top_r3", [])

        return {
            "overall_accuracy": acc_b if acc_b else max(acc_map.values() or [0.0]),
            "combination_a": {
                "accuracy": acc_a,
                "total_samples": len(details_a),
                "hit_samples": sum(1 for d in details_a if d.get("hit")),
                "details": details_a,
            },
            "combination_b": {
                "accuracy": acc_b,
                "total_samples": len(details_b),
                "hit_samples": sum(1 for d in details_b if d.get("hit")),
                "details": details_b,
            },
            "variants": variants_results,
            "average_processing_time_ms": avg_ms,
            "total_samples": sum(v["total_samples"] for v in variants_results) // (len(variants_results) or 1),
        }

    async def evaluate_params(
        self,
        server_url: str,
        endpoint: str,
        standard_query: Optional[str],
        patient_info: Optional[str],
        clinical_context: Optional[str],
        gold_answer: Optional[str],
        enable_reranking: bool,
        need_llm_recommendations: bool,
        apply_rule_filter: bool,
        top_scenarios: int,
        top_recommendations_per_scenario: int,
        show_reasoning: Optional[bool],
        include_raw_data: Optional[bool],
        similarity_threshold: float,
        min_appropriateness_rating: int,
    ) -> Dict[str, Any]:
        """非文件模式评测：按传入策略进行一次评测，并与 A/B 组合映射对齐。"""
        if standard_query and (patient_info or clinical_context):
            raise ValueError("standard_query conflicts with patient/clinical")
        if standard_query:
            text = standard_query
        else:
            if not clinical_context:
                raise ValueError("clinical_context required")
            cc = json.loads(clinical_context)
            text = str(cc.get("chief_complaint") or "")

        retr = RetrievalRequest(
            enable_reranking=enable_reranking,
            need_llm_recommendations=need_llm_recommendations,
            apply_rule_filter=apply_rule_filter,
            top_scenarios=top_scenarios,
            top_recommendations_per_scenario=top_recommendations_per_scenario,
            similarity_threshold=similarity_threshold,
            min_appropriateness_rating=min_appropriateness_rating,
        )

        # 动态添加额外字段
        retr.show_reasoning = bool(show_reasoning) if show_reasoning is not None else False
        retr.include_raw_data = bool(include_raw_data) if include_raw_data is not None else False

        payload = self.build_request_payload(
            endpoint, text, retr,
            standard_query=standard_query if standard_query else None,
            patient_info=patient_info,
            clinical_context=clinical_context
        )
        data = await self.post_recommendation_request(server_url, endpoint, payload)

        # 根据不同接口提取推荐结果
        groups = extract_recommendations_by_endpoint(endpoint, data)

        # 获取处理时间
        ms = 0
        if endpoint in ["recommend", "recommend-simple"]:
            ms = data.get("processing_time_ms", 0)
        elif endpoint == "intelligent-recommendation":
            ms = data.get("processing_time_ms", 0)

        gold = normalize_text(gold_answer) if gold_answer else ""
        per_hits = [ is_gold_hit_in_choices(group, gold) for group in groups[:top_scenarios] ] if gold else [1 if groups else 0]
        overall_hit = 1 if any(per_hits) else 0
        details = [{
            "clinical_scenario": text,
            "standard_answer": gold,
            "recommendations": groups if top_scenarios > 1 else (groups[0] if groups else []),
            "per_scenario_hits": per_hits,
            "hit": bool(overall_hit),
            "processing_time_ms": ms,
        }]
        acc = float(overall_hit)
        return {
            "overall_accuracy": acc,
            "combination_a": {
                "accuracy": acc if top_scenarios == 1 and top_recommendations_per_scenario == 1 else 0.0,
                "total_samples": 1,
                "hit_samples": 1 if acc else 0,
                "details": details,
            },
            "combination_b": {
                "accuracy": acc if top_scenarios == 3 and top_recommendations_per_scenario == 3 else 0.0,
                "total_samples": 1,
                "hit_samples": 1 if acc else 0,
                "details": details,
            },
            "variants": [
                {
                    "label": f"top_s{top_scenarios}_top_r{top_recommendations_per_scenario}",
                    "accuracy": acc,
                    "total_samples": 1,
                    "hit_samples": 1 if acc else 0,
                    "details": details,
                }
            ],
            "average_processing_time_ms": ms,
            "total_samples": 1,
        }

    async def evaluate_all_endpoints(
        self,
        file_bytes: bytes,
        top_scenarios: int = 3,
        top_recommendations_per_scenario: int = 3,
        similarity_threshold: float = 0.7,
        min_appropriateness_rating: int = 5,
    ) -> Dict[str, Any]:
        """并发评估所有4个接口并返回汇总结果，使用线程池模拟真实用户场景"""

        # 定义4个接口配置
        endpoints_config = [
            {
                "name": "recommend",
                "server_url": "http://203.83.233.236:5188",
                "endpoint": "recommend",
            },
            {
                "name": "recommend-simple",
                "server_url": "http://203.83.233.236:5188",
                "endpoint": "recommend-simple",
            },
            {
                "name": "intelligent-recommendation",
                "server_url": "http://203.83.233.236:5189",
                "endpoint": "intelligent-recommendation",
            },
            {
                "name": "recommend_item_with_reason",
                "server_url": "http://203.83.233.236:5187",
                "endpoint": "recommend_item_with_reason",
            },
        ]

        # 使用线程池并发调用所有接口，模拟真实用户场景
        with ThreadPoolExecutor(max_workers=4) as executor:
            loop = asyncio.get_event_loop()
            tasks = []
            for config in endpoints_config:
                # 将每个评估任务提交到线程池
                task = loop.run_in_executor(
                    executor,
                    self._evaluate_single_sync,
                    config["server_url"],
                    config["endpoint"],
                    file_bytes,
                    top_scenarios,
                    top_recommendations_per_scenario,
                    similarity_threshold,
                    min_appropriateness_rating,
                )
                tasks.append((config["name"], task))

            # 等待所有任务完成
            results_list = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

        # 整理结果
        all_results = {}
        for i, (endpoint_name, _) in enumerate(tasks):
            if isinstance(results_list[i], Exception):
                all_results[endpoint_name] = {
                    "error": str(results_list[i]),
                    "status": "failed"
                }
            else:
                all_results[endpoint_name] = {
                    "status": "success",
                    "result": results_list[i]
                }

        # 计算总体统计
        successful_results = [r for r in results_list if not isinstance(r, Exception)]
        if successful_results:
            total_samples = len(self._rows_from_excel(file_bytes))
            avg_overall_accuracy = sum(r["overall_accuracy"] for r in successful_results) / len(successful_results)
            avg_processing_time = sum(r["average_processing_time_ms"] for r in successful_results) / len(successful_results)
        else:
            total_samples = 0
            avg_overall_accuracy = 0.0
            avg_processing_time = 0

        summary = {
            "total_endpoints_tested": len(endpoints_config),
            "successful_endpoints": len(successful_results),
            "failed_endpoints": len(endpoints_config) - len(successful_results),
            "average_overall_accuracy": avg_overall_accuracy,
            "average_processing_time_ms": int(avg_processing_time),
            "total_samples": total_samples,
        }

        # 保存评测结果到CSV文件
        csv_file_path = self._save_evaluation_to_csv(all_results, summary, file_bytes)

        return {
            "summary": summary,
            "endpoint_results": all_results,
            "csv_file_path": csv_file_path,
        }

    def _evaluate_single_sync(
        self,
        server_url: str,
        endpoint: str,
        file_bytes: bytes,
        top_scenarios: int,
        top_recommendations_per_scenario: int,
        similarity_threshold: float,
        min_appropriateness_rating: int,
    ) -> Dict[str, Any]:
        """同步方式执行单个接口评估，用于线程池"""
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                self.evaluate_excel(
                    server_url=server_url,
                    endpoint=endpoint,
                    file_bytes=file_bytes,
                    strategy_variants=[(top_scenarios, top_recommendations_per_scenario)],
                    enable_reranking=False,
                    need_llm_recommendations=False,
                    apply_rule_filter=False,
                    similarity_threshold=similarity_threshold,
                    min_appropriateness_rating=min_appropriateness_rating,
                    show_reasoning=False,
                    include_raw_data=False,
                    debug_mode=False,
                    compute_ragas=False,
                    ground_truth="",
                )
            )
            return result
        finally:
            loop.close()

    def _save_evaluation_to_csv(
        self,
        all_results: Dict[str, Any],
        summary: Dict[str, Any],
        file_bytes: bytes,
    ) -> str:
        """将评测结果保存到CSV文件"""
        # 创建结果目录
        results_dir = "evaluation_results"
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)

        # 生成文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"evaluation_all_{timestamp}.csv"
        csv_filepath = os.path.join(results_dir, csv_filename)

        # 提取原始测试样本
        rows = self._rows_from_excel(file_bytes)

        # 准备CSV数据
        csv_data = []

        # 添加汇总信息行
        csv_data.append({
            "接口名称": "【汇总统计】",
            "状态": f"成功: {summary['successful_endpoints']}/{summary['total_endpoints_tested']}",
            "平均命中率": f"{summary['average_overall_accuracy']:.2%}",
            "平均处理时间(ms)": summary['average_processing_time_ms'],
            "样本数": summary['total_samples'],
            "临床场景": "",
            "标准答案": "",
            "推荐结果": "",
            "是否命中": "",
        })
        csv_data.append({})  # 空行

        # 为每个接口添加详细结果
        for endpoint_name, endpoint_result in all_results.items():
            if endpoint_result["status"] == "success":
                result = endpoint_result["result"]

                # 添加接口统计行
                csv_data.append({
                    "接口名称": f"【{endpoint_name}】",
                    "状态": "成功",
                    "平均命中率": f"{result['overall_accuracy']:.2%}",
                    "平均处理时间(ms)": result['average_processing_time_ms'],
                    "样本数": result['total_samples'],
                    "临床场景": "",
                    "标准答案": "",
                    "推荐结果": "",
                    "是否命中": "",
                })

                # 获取组合B的详细结果（3场景3推荐）
                combination_key = f"top_s{result.get('variants', [{}])[0].get('label', '').split('_')[1] if result.get('variants') else '3'}"
                details = result.get('combination_b', {}).get('details', [])

                # 添加每个样本的详细结果
                for i, detail in enumerate(details):
                    recommendations = detail.get('recommendations', [])
                    # 格式化推荐结果
                    if isinstance(recommendations, list):
                        if recommendations and isinstance(recommendations[0], list):
                            # 多场景情况
                            rec_str = " | ".join([", ".join(group) for group in recommendations])
                        else:
                            # 单场景情况
                            rec_str = ", ".join(recommendations)
                    else:
                        rec_str = str(recommendations)

                    csv_data.append({
                        "接口名称": endpoint_name,
                        "状态": "",
                        "平均命中率": "",
                        "平均处理时间(ms)": detail.get('processing_time_ms', ''),
                        "样本数": "",
                        "临床场景": detail.get('clinical_scenario', ''),
                        "标准答案": detail.get('standard_answer', ''),
                        "推荐结果": rec_str,
                        "是否命中": "✓" if detail.get('hit') else "✗",
                    })

                csv_data.append({})  # 接口之间添加空行

            else:
                # 失败的接口
                csv_data.append({
                    "接口名称": f"【{endpoint_name}】",
                    "状态": f"失败: {endpoint_result.get('error', '未知错误')}",
                    "平均命中率": "",
                    "平均处理时间(ms)": "",
                    "样本数": "",
                    "临床场景": "",
                    "标准答案": "",
                    "推荐结果": "",
                    "是否命中": "",
                })
                csv_data.append({})

        # 将数据转换为DataFrame并保存
        df = pd.DataFrame(csv_data)
        df.to_csv(csv_filepath, index=False, encoding='utf-8-sig')

        return csv_filepath