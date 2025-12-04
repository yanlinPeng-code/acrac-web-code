from fastapi import APIRouter, Request, Body
from app.response.response_models import BaseResponse
from app.response.utils import success_200
from app.schema.IntelligentRecommendation_schemas import IntelligentRecommendationRequest, \
    IntelligentRecommendationResponse

from app.dependencies.dependency import RagRecommendDep_V2

router=APIRouter(prefix="/api/v2", tags=["推荐模块_V2版本"])
@router.post(
    path="/recommend_detail",
    summary="推荐项目以结构化json返回，分为三级分类",
    description="推荐",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def rag_recommend(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep_V2,
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
    path="/recommend_simple",
    summary="简单推荐,推荐项目以结构化json返回，分为三级分类",
    description="简单推荐",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def rag_recommend(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep_V2,
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
    path="/recommend_final_choices",
    summary="项目推荐，该推荐仅仅返回最终的检查项目",
    description="",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def recommend_final_choice(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep_V2,
):
    """
    推荐
    """
    client_ip = getattr(http_request.state, 'client_ip', None)
    request_id = getattr(http_request.state, 'request_id', None)

    # 获取medical_dict
    medical_dict = getattr(http_request.app.state, 'medical_dict', None)

    response = await rag_recommendation_service.generate_fincal_recommendation(
        recommendation_request,
        medical_dict
    )
    return success_200(response.model_dump(), message="推荐成功", request_id=request_id, host_id=client_ip)




@router.post(
    path="/recommend_simple_final_choices",
    summary="简单项目推荐，该推荐仅仅返回最终的检查项目，与项目推荐略有性能提高",
    description="",
    response_model=BaseResponse[IntelligentRecommendationResponse],
)
async def recommend_simple_final_choice(
        http_request: Request,
        recommendation_request: IntelligentRecommendationRequest,
        rag_recommendation_service: RagRecommendDep_V2,
):
    """
    推荐
    """
    client_ip = getattr(http_request.state, 'client_ip', None)
    request_id = getattr(http_request.state, 'request_id', None)

    # 获取medical_dict
    medical_dict = getattr(http_request.app.state, 'medical_dict', None)

    response = await rag_recommendation_service.generate_simple_fincal_recommendation(
        recommendation_request,
        medical_dict
    )
    return success_200(response.model_dump(), message="推荐成功", request_id=request_id, host_id=client_ip)