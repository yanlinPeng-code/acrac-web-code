from fastapi import APIRouter, Request
from app.schema.judge_schemas import JudgeRequest,JudgeResponse
from app.response.response_models import BaseResponse
from app.dependencies.dependency import JudgeDep
from app.response.utils import success_200
router=APIRouter(prefix="/api/v1",tags=["模型评判模块"])




@router.post("/judge",
    summary="根据LLM评判模型推荐结果",
    response_model=BaseResponse[JudgeResponse],
)
async def judge_by_llm(
    request:Request,
    judge_request:JudgeRequest,
    judge_service:JudgeDep,
    )->BaseResponse[JudgeResponse]:
    """
       接收模型预测结果与金标准进行对比评估，以下是详细参数及示例。

       ---

       ### 📤 请求体参数 (Request Body Arguments)

       * **pred_items**: <span style="color:#b22222">模型预测项（红色强调）</span>
       * **gold_items**: <span style="color:#483d8b">金标准项（蓝色强调）</span>
       * **online_model**: <span style="color:#808000">是否使用在线模型</span>
       * **model_judge**: <span style="color:#808000">是否开启模型判官</span>

       ---

       ### 📝 JSON 示例 (Example Value)

       为了方便测试，示例 JSON 如下所示，请直接复制到 'Example Value' 或 'Raw' 输入框中：

       ```json
       {
         "pred_items": [
           "CT颅脑平扫",
           "CT脊骨平扫",
           "CT颅脑(增强)"
         ],
         "gold_items": [
           "CT颅脑平扫"
         ],
         "online_model": true,
         "model_judge": true
       }
       ```
       """
    client_ip = getattr(request.state, "client_ip", None)
    request_id = getattr(request.state, "request_id", None)
    #调用评判服务
    judge_response=await judge_service.judge_recommendations(judge_request)


    return success_200(judge_response,message="评判推荐结果成功",request_id=request_id,host_id=client_ip)

    




