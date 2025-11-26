from fastapi import APIRouter, Request, Body

from app.response.response_models import BaseResponse
from app.response.utils import success_200
from app.schema.IntelligentRecommendation_schemas import IntelligentRecommendationRequest, \
    IntelligentRecommendationResponse
from app.dependencies.dependency import RagRecommendDep
from starlette.responses import StreamingResponse


router=APIRouter(prefix="/api/v1", tags=["推荐模块"])

@router.post(
    path="/recommend",
    summary="推荐",
    description="推荐",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def rag_recommend(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep,
):
    """
    推荐
    """
    client_ip = getattr(http_request.state, 'client_ip', None)
    request_id = getattr(http_request.state, 'request_id', None)
    
    # 获取medical_dict
    medical_dict = getattr(http_request.app.state, 'medical_dict', None)
    
    response=await rag_recommendation_service.generate_intelligent_recommendation(
         recommendation_request,
         medical_dict
    )
    return success_200(response.model_dump(), message="推荐成功", request_id=request_id, host_id=client_ip)


@router.post(
    path="/recommend-simple",
    summary="简单推荐",
    description="简单推荐",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def rag_recommend(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep,
):
    """
    推荐
    """
    client_ip = getattr(http_request.state, 'client_ip', None)
    request_id = getattr(http_request.state, 'request_id', None)

    # 获取medical_dict
    medical_dict = getattr(http_request.app.state, 'medical_dict', None)

    response = await rag_recommendation_service.generate_simple_recommendation(
        recommendation_request,
        medical_dict
    )
    return success_200(response.model_dump(), message="推荐成功", request_id=request_id, host_id=client_ip)


@router.post(
    path="/recommend-stream",
    summary="流式直接推荐",
    description="LLM直接返回推荐项目及理由的纯文本，流式输出（每个场景先推荐项目，后推荐理由）",
)
async def rag_recommend_stream(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep,
):
    client_ip = getattr(http_request.state, 'client_ip', None)
    request_id = getattr(http_request.state, 'request_id', None)
    medical_dict = getattr(http_request.app.state, 'medical_dict', None)

    async def generator():
        async for chunk in rag_recommendation_service.stream_direct_recommendation(
            recommendation_request,
            medical_dict
        ):
            yield chunk

    return StreamingResponse(generator(), media_type="text/plain; charset=utf-8")