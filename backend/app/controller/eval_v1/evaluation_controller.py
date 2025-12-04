from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import Optional, Dict, Any
from app.response.response_models import BaseResponse
from app.response.utils import success_200, bad_request_400
from app.dependencies.dependency import EvaluationDep

from app.schema.eval_schema import EvalRequest

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
    endpoint: str = Form("recommend-simple"),  # 默认值为recommend-simple
    standard_query: Optional[str] = Form(None),
    gold_answer: Optional[str] = Form(None),
    patient_info: Optional[str] = Form(None),
    clinical_context: Optional[str] = Form(None),
    enable_reranking: Optional[bool] = Form(None),
    need_llm_recommendations: Optional[bool] = Form(None),
    apply_rule_filter: Optional[bool] = Form(None),
    top_scenarios: Optional[int] = Form(3),
    top_recommendations_per_scenario: Optional[int] = Form(3),
    show_reasoning: Optional[bool] = Form(False),
    include_raw_data: Optional[bool] = Form(False),
    similarity_threshold: Optional[float] = Form(0.7),
    min_appropriateness_rating: Optional[int] = Form(5),
    debug_mode: Optional[bool] = Form(False),
    compute_ragas: Optional[bool] = Form(False),
    ground_truth: Optional[str] = Form(""),
    session_id: Optional[str] = Form(None),
    patient_id: Optional[str] = Form(None),
    doctor_id: Optional[str] = Form(None),
):
    """评估推荐接口

    - 文件模式：上传Excel后仅需指定 `endpoint`，其余策略参数可选；可附带单一组合 `(top_s, top_r)`。
    - 非文件模式：`standard_query` 与 `patient_info/clinical_context` 互斥，策略参数必填；可传 `gold_answer` 用于命中计算。

    支持的endpoints:
    - recommend
    - recommend-simple (默认)
    - intelligent-recommendation
    - recommend_item_with_reason
    """
    client_ip = getattr(http_request.state, "client_ip", None)
    request_id = getattr(http_request.state, "request_id", None)

    # 验证endpoint
    valid_endpoints = ["recommend", "recommend-simple", "intelligent-recommendation", "recommend_item_with_reason"]
    if endpoint not in valid_endpoints:
        return bad_request_400(f"非法endpoint，支持的值: {', '.join(valid_endpoints)}", request_id=request_id, host_id=client_ip)

    # 根据endpoint确定server_url
    server_url_map = {
        "recommend": "http://localhost:8000",
        "recommend-simple": "http://localhost:8000",
        "intelligent-recommendation": "http://203.83.233.236:5189",
        "recommend_item_with_reason": "http://203.83.233.236:5187",
    }
    server_url = server_url_map[endpoint]

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
            bool(enable_reranking) if enable_reranking is not None else False,
            bool(need_llm_recommendations) if need_llm_recommendations is not None else False,
            bool(apply_rule_filter) if apply_rule_filter is not None else False,
            float(similarity_threshold) if similarity_threshold is not None else 0.7,
            int(min_appropriateness_rating) if min_appropriateness_rating is not None else 5,
            bool(include_raw_data) if include_raw_data is not None else False,
            bool(debug_mode) if debug_mode is not None else False,
            bool(show_reasoning) if show_reasoning is not None else False,
            bool(compute_ragas) if compute_ragas is not None else False,
            str(ground_truth) if ground_truth else "",
        )
        return success_200(data, message="评估完成", request_id=request_id, host_id=client_ip)

    # 非文件模式
    if standard_query and (patient_info or clinical_context):
        return bad_request_400("standard_query与patient/clinical互斥", request_id=request_id, host_id=client_ip)

    # 必填参数校验
    if top_scenarios is None or top_recommendations_per_scenario is None or similarity_threshold is None or min_appropriateness_rating is None:
        return bad_request_400("缺少必填检索策略参数", request_id=request_id, host_id=client_ip)

    # 对于recommend和recommend-simple，需要额外的参数
    if endpoint in ["recommend", "recommend-simple"]:
        req_params = [enable_reranking, need_llm_recommendations, apply_rule_filter]
        if any(v is None for v in req_params):
            return bad_request_400("recommend/recommend-simple接口缺少必填参数", request_id=request_id, host_id=client_ip)

    data = await evaluation_service.evaluate_params(
        server_url,
        endpoint,
        standard_query,
        patient_info,
        clinical_context,
        gold_answer,
        bool(enable_reranking) if enable_reranking is not None else False,
        bool(need_llm_recommendations) if need_llm_recommendations is not None else False,
        bool(apply_rule_filter) if apply_rule_filter is not None else False,
        int(top_scenarios),
        int(top_recommendations_per_scenario),
        bool(show_reasoning) if show_reasoning is not None else False,
        bool(include_raw_data) if include_raw_data is not None else False,
        float(similarity_threshold),
        int(min_appropriateness_rating),
    )
    return success_200(data, message="评估完成", request_id=request_id, host_id=client_ip)


@router.post(
    path="/evaluate-recommend/preview",
    summary="预览Excel评测数据",
    description="上传Excel文件并返回前100行预览数据",
    response_model=BaseResponse[Dict[str, Any]],
)
async def preview_excel_data(
    http_request: Request,
    evaluation_service: EvaluationDep,
    file: UploadFile = File(...),
):
    """预览Excel评测数据

    上传Excel文件，返回前100行数据供用户确认
    不执行任何评测任务
    """
    client_ip = getattr(http_request.state, "client_ip", None)
    request_id = getattr(http_request.state, "request_id", None)

    # 验证文件类型
    if not file.filename.endswith(('.xlsx', '.xls')):
        return bad_request_400("仅支持Excel文件格式（.xlsx, .xls）", request_id=request_id, host_id=client_ip)

    content = await file.read()

    # 获取预览数据
    preview_data = await evaluation_service.get_excel_preview(content)

    if not preview_data:
        return bad_request_400("Excel文件为空或格式错误", request_id=request_id, host_id=client_ip)

    return success_200(
        {
            "preview": preview_data,
            "total_rows": len(preview_data),
            "preview_limit": min(100, len(preview_data)),
            "filename": file.filename
        },
        message="Excel预览加载成功",
        request_id=request_id,
        host_id=client_ip
    )


@router.post(
    path="/evaluate-recommend/all",
    summary="评估所有推荐接口",
    description="异步并发调用4个推荐接口进行评估并返回任务ID",
    response_model=BaseResponse[Dict[str, Any]],
)
async def evaluate_all_recommend(
    http_request: Request,
    evaluation_service: EvaluationDep,
    file: UploadFile = File(...),
    limit: Optional[int] = Form(None),
    top_scenarios: int = Form(3),
    top_recommendations_per_scenario: int = Form(3),
    similarity_threshold: float = Form(0.7),
    min_appropriateness_rating: int = Form(5),
):
    """异步并发评估所有4个推荐接口

    必须上传Excel文件，包含临床场景和标准答案
    limit: 评测数据条数，默认为全部
    返回任务ID（不包含预览数据，预览请使用 /preview 接口）
    """
    client_ip = getattr(http_request.state, "client_ip", None)
    request_id = getattr(http_request.state, "request_id", None)

    # 验证文件类型
    if not file.filename.endswith(('.xlsx', '.xls')):
        return bad_request_400("仅支持Excel文件格式（.xlsx, .xls）", request_id=request_id, host_id=client_ip)

    content = await file.read()

    # 提交评测任务（不再并发预览）
    import asyncio
    task_id = await asyncio.to_thread(
        evaluation_service.submit_evaluation_task,
        file_bytes=content,
        limit=limit,
        top_scenarios=top_scenarios,
        top_recommendations_per_scenario=top_recommendations_per_scenario,
        similarity_threshold=similarity_threshold,
        min_appropriateness_rating=min_appropriateness_rating,
    )

    return success_200(
        {"task_id": task_id, "status": "pending"},
        message="评测任务已提交，请使用task_id查询结果",
        request_id=request_id,
        host_id=client_ip
    )


@router.get(
    path="/evaluate-recommend/task/{task_id}",
    summary="查询评测任务状态",
    description="根据任务ID查询评测任务的状态和结果",
    response_model=BaseResponse[Dict[str, Any]],
)
async def get_evaluation_task_status(
    http_request: Request,
    evaluation_service: EvaluationDep,
    task_id: str,
):
    """查询评测任务状态

    返回任务状态：PENDING（等待中）、STARTED（执行中）、SUCCESS（成功）、FAILURE（失败）
    """
    client_ip = getattr(http_request.state, "client_ip", None)
    request_id = getattr(http_request.state, "request_id", None)

    response = evaluation_service.get_task_status(task_id)

    return success_200(response, message="查询成功", request_id=request_id, host_id=client_ip)