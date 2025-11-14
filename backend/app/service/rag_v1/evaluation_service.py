from typing import Optional, List, Dict, Any, Tuple
import io
import json
import pandas as pd
import httpx

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


def is_gold_hit_in_choices(choices: List[str], gold_answer: str) -> int:
    """判断标准答案是否命中于某个场景的推荐集合（final_choices）。"""
    gold = normalize_text(gold_answer)
    if not gold:
        return 0
    normalized = [normalize_text(x) for x in choices]
    return 1 if gold in normalized else 0


class EvaluationService:
    """评测服务：通过 HTTP 直连被测后端 URL，执行推荐接口并统计命中率。"""

    def __init__(self):
        pass

    async def post_recommendation_request(self, server_url: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用被测后端的推荐接口并返回 Data 节点内容。"""
        url = server_url.rstrip("/") + ("/api/v1/recommend" if endpoint == "recommend" else "/api/v1/recommend-simple")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()
        return body.get("Data", {})

    def build_request_payload(
        self,
        scenario_text: str,
        need_optimize_query: bool,
        retrieval: RetrievalRequest,
        standard_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构造被测后端推荐接口的请求载荷。"""
        patient_dump = PatientInfo().model_dump()
        clinical_dump = ClinicalContext(
            department="影像科",
            chief_complaint=scenario_text,
            medical_history=None,
            present_illness=None,
            diagnosis=None,
            symptom_duration=None,
            symptom_severity=None,
        ).model_dump()
        return {
            "patient_info": patient_dump,
            "clinical_context": clinical_dump,
            "need_optimize_query": need_optimize_query,
            "search_strategy": None,
            "retrieval_strategy": retrieval.model_dump(),
            "standard_query": standard_query or "",
        }

    def _rows_from_excel(self, file_bytes: bytes) -> List[Dict[str, str]]:
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
                retr = RetrievalRequest(
                    enable_reranking=enable_reranking,
                    need_llm_recommendations=need_llm_recommendations,
                    apply_rule_filter=apply_rule_filter,
                    top_scenarios=s_num,
                    top_recommendations_per_scenario=r_num,
                    show_reasoning=False,
                    include_raw_data=False,
                    similarity_threshold=similarity_threshold,
                    min_appropriateness_rating=min_appropriateness_rating,
                )
                payload = self.build_request_payload(text, True, retr)
                data = await self.post_recommendation_request(server_url, endpoint, payload)
                fc_groups = extract_final_choices(data.get("best_recommendations"))
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
                        "processing_time_ms": data.get("processing_time_ms") or 0,
                    })
                else:
                    hit = 1 if any(per_hits) else 0
                    details.append({
                        "clinical_scenario": text,
                        "standard_answer": gold,
                        "recommendations": fc_groups,
                        "per_scenario_hits": per_hits,
                        "hit": bool(hit),
                        "processing_time_ms": data.get("processing_time_ms") or 0,
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
            show_reasoning=bool(show_reasoning) if show_reasoning is not None else False,
            include_raw_data=bool(include_raw_data) if include_raw_data is not None else False,
            similarity_threshold=similarity_threshold,
            min_appropriateness_rating=min_appropriateness_rating,
        )
        payload = self.build_request_payload(text, True, retr, standard_query if standard_query else None)
        data = await self.post_recommendation_request(server_url, endpoint, payload)
        groups = extract_final_choices(data.get("best_recommendations"))
        ms = data.get("processing_time_ms") or 0
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