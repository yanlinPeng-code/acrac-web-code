from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import Optional, Dict, Any

from app.response.response_models import BaseResponse
from app.response.utils import success_200, bad_request_400
from app.dependencies.dependency import EvaluationDep


router = APIRouter(prefix="/api/v1", tags=["评估模块"])

@router.post(
    path="/evaluate-recommend",
    summary="评估推荐接口",
    description="基于Excel或直接输入评估推荐结果命中率与耗时",
    response_model=BaseResponse[Dict[str, Any]],
)
async def evaluate_recommend(
    http_request: Request,
    evaluation_service: EvaluationDep,
    file: Optional[UploadFile] = File(None),
    server_url: str = Form(...),
    endpoint: str = Form(...),
    standard_query: Optional[str] = Form(None),
    gold_answer: Optional[str] = Form(None),
    patient_info: Optional[str] = Form(None),
    clinical_context: Optional[str] = Form(None),
    enable_reranking: Optional[bool] = Form(None),
    need_llm_recommendations: Optional[bool] = Form(None),
    apply_rule_filter: Optional[bool] = Form(None),
    top_scenarios: Optional[int] = Form(None),
    top_recommendations_per_scenario: Optional[int] = Form(None),
    show_reasoning: Optional[bool] = Form(None),
    include_raw_data: Optional[bool] = Form(None),
    similarity_threshold: Optional[float] = Form(None),
    min_appropriateness_rating: Optional[int] = Form(None),
):
    """评估推荐接口

    - 文件模式：上传Excel后仅需指定 `server_url` 与 `endpoint`，其余策略参数可选；可附带单一组合 `(top_s, top_r)`。
    - 非文件模式：`standard_query` 与 `patient_info/clinical_context` 互斥，策略参数必填；可传 `gold_answer` 用于命中计算。
    """
    client_ip = getattr(http_request.state, "client_ip", None)
    request_id = getattr(http_request.state, "request_id", None)
    medical_dict = getattr(http_request.app.state, "medical_dict", None)

    if endpoint not in {"recommend", "recommend-simple"}:
        return bad_request_400("非法endpoint", request_id=request_id, host_id=client_ip)

    isFileMode = file is not None
    if isFileMode:
        content = await file.read()
        strategy_variants = None
        if top_scenarios is not None and top_recommendations_per_scenario is not None:
            try:
                strategy_variants = [(int(top_scenarios), int(top_recommendations_per_scenario))]
            except Exception:
                strategy_variants = None
        data = await evaluation_service.evaluate_excel(
            server_url,
            endpoint,
            content,
            strategy_variants,
            bool(enable_reranking) if enable_reranking is not None else True,
            bool(need_llm_recommendations) if need_llm_recommendations is not None else True,
            bool(apply_rule_filter) if apply_rule_filter is not None else True,
            float(similarity_threshold) if similarity_threshold is not None else 0.6,
            int(min_appropriateness_rating) if min_appropriateness_rating is not None else 5,
        )
        return success_200(data, message="评估完成", request_id=request_id, host_id=client_ip)
    if standard_query and (patient_info or clinical_context):
        return bad_request_400("standard_query与patient/clinical互斥", request_id=request_id, host_id=client_ip)
    req_params = [enable_reranking, need_llm_recommendations, apply_rule_filter, top_scenarios, top_recommendations_per_scenario, similarity_threshold, min_appropriateness_rating]
    if any(v is None for v in req_params):
        return bad_request_400("缺少必填检索策略参数", request_id=request_id, host_id=client_ip)
    data = await evaluation_service.evaluate_params(
        server_url,
        endpoint,
        standard_query,
        gold_answer,
        patient_info,
        clinical_context,
        bool(enable_reranking),
        bool(need_llm_recommendations),
        bool(apply_rule_filter),
        int(top_scenarios),
        int(top_recommendations_per_scenario),
        bool(show_reasoning) if show_reasoning is not None else False,
        bool(include_raw_data) if include_raw_data is not None else False,
        float(similarity_threshold),
        int(min_appropriateness_rating),
    )
    return success_200(data, message="评估完成", request_id=request_id, host_id=client_ip)