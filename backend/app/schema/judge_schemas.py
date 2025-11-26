

from typing import Optional
from pydantic import BaseModel, Field


class JudgeRequest(BaseModel):
      #推荐项目列表
    pred_items:Optional[list[str]|list[dict]]|None=Field(
        default=None,
        description="推荐项目列表，每个项目可以是字符串或字典（包含项目ID和其他信息）",
    )
    #标准推荐项目
    gold_items:Optional[list[str]]|None=Field(
        default=None,
        description="标准推荐项目列表，每个项目是字符串",
    )
    online_model:Optional[bool]=Field(
        default=True,
        description="是否使用在线模型评判推荐结果",
    )
    model_judge:Optional[bool]=Field(
        default=True,
        description="是否使用模型评判推荐结果",
    )
  







class JudgeResult(BaseModel):
    top1_hit:Optional[str]=Field(
        default=None,
        description="Top-1的评判结果，只能是0或1，0表示推荐项目不在标准推荐项目中，1表示推荐项目在标准推荐项目中",

    )
    top3_hit:Optional[str]=Field(
        default=None,
        description="Top-3的评判结果，只能是0或1，0表示推荐项目不在标准推荐项目中，1表示推荐项目在标准推荐项目中",
    )
    hit_count:Optional[str]=Field(
        default=None,
        description="命中的项目数量",
    )
    hit_items:Optional[list[str]]=Field(
        default=None,
        description="命中的项目列表",
    )
    
    reason:Optional[str]=Field(
        default=None,
        description="评判结果的解释",
    )



class JudgeResponse(BaseModel):
    judge_result:Optional[JudgeResult|list[JudgeResult]]=Field(
        default=None,
        description="LLM评判结果",
    )











