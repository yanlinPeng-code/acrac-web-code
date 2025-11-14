from fastapi import APIRouter, Request

from app.response.response_models import BaseResponse
from app.response.utils import success_200
from app.schema.IntelligentRecommendation_schemas import IntelligentRecommendationRequest, \
    IntelligentRecommendationResponse
from app.dependencies.dependency import RagRecommendDep


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