from fastapi import APIRouter, Request
from app.schema.judge_schemas import JudgeRequest,JudgeResponse
from app.response.response_models import BaseResponse
from app.dependencies.dependency import JudgeDep
from app.response.utils import success_200
router=APIRouter(prefix="/api/v1",tags=["模型评判模块"])




@router.post("/judge",
    summary="根据LLM评判模型推荐结果",
    description="根据LLM评判模型推荐结果",
    response_model=BaseResponse[JudgeResponse],
)
async def judge_by_llm(
    request:Request,
    judge_request:JudgeRequest,
    judge_service:JudgeDep,
    )->BaseResponse[JudgeResponse]:
    """
    根据LLM评判模型推荐结果
    请求参数：
    - recommendations:推荐项目列表
    - standard_recommendations:标准推荐项目列表
    - model_judge:是否使用模型评判推荐结果
    响应参数：
    - judge_result:LLM评判结果

    """
    client_ip = getattr(request.state, "client_ip", None)
    request_id = getattr(request.state, "request_id", None)
    #调用评判服务
    judge_response=await judge_service.judge_recommendations(judge_request)


    return success_200(judge_response,message="评判推荐结果成功",request_id=request_id,host_id=client_ip)

    




