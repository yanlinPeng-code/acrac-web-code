from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate
from app.config.config import settings
from app.service.rag_v1.ai_service import AiService
from app.schema.judge_schemas import JudgeRequest
from app.schema.judge_schemas import JudgeResponse
from app.schema.judge_schemas import JudgeResult
from backend.app.prompt.judge_prompt import judge_prompt
class JudgeService:
 

    def _normalize_recs(self, recs):
        out = []
        for r in recs or []:
            if isinstance(r, str):
                out.append(r.strip())
            elif isinstance(r, dict):
                v = r.get("id") or r.get("name") or r.get("title") or next(iter(r.values()), "")
                out.append(str(v).strip())
            else:
                out.append(str(r).strip())
        return out


    async def judge_recommendations(self,judge_request:JudgeRequest)->JudgeResponse:
        """
        根据LLM评判模型推荐结果
        请求参数：
        - recommendations:推荐项目列表
        - standard_recommendations:标准推荐项目列表
        - model_judge:是否使用模型评判推荐结果
        响应参数：
        - judge_result:LLM评判结果
        """
        if judge_request.model_judge:
            return await self.judge_by_llm(judge_request)
        return self.judge_by_str(judge_request)

    async def judge_by_llm(self,judge_request:JudgeRequest)->JudgeResponse:
        """
        根据LLM评判模型推荐结果
        请求参数：
        - pred_items:推荐项目列表
        - gold_items:标准推荐项目列表
        - model_judge:是否使用模型评判推荐结果
        - oneonline_model:是否使用在线模型
        响应参数：
        - judge_result:LLM评判结果
        """
        recs = self._normalize_recs(judge_request.pred_items or [])
        stds = judge_request.gold_items or []
        
        prompt=ChatPromptTemplate.from_messages([
            (
                "system",
                judge_prompt,
            ),
            ("user", "推荐列表: {pred_items}\n标准列表: {gold_items}"),
        ])
        if judge_request.online_model:
            llm=ChatDeepSeek(
                model=settings.DEEPSEEK_MODEL_NAME,
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                temperature=1.0,
                streaming=False
            )
        else:
            llm=ChatOpenAI(
                model=settings.OLLAMA_LLM_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                api_key=settings.SILICONFLOW_API_KEY,
            )




        llm_with_output=llm.with_structured_output(JudgeResult)



        
        chain=prompt|llm_with_output

        resopnse=await chain.ainvoke({
            "pred_items": recs,
            "gold_items": stds,
        })
        return JudgeResponse(judge_result=resopnse).model_dump()







      
    def judge_by_str(self,judge_request:JudgeRequest)->JudgeResponse:
        """
        根据字符串形式匹配推荐项目和标准推荐项目
        请求参数：
        - pred_items:推荐项目列表
        - gold_items:标准推荐项目列表
        - model_judge:是否使用模型评判推荐结果
        响应参数：
        - judge_result:字符串匹配评判结果
        """
        #完全做字符串匹配
        recs = self._normalize_recs(judge_request.pred_items or [])
        stds = judge_request.gold_items or []
        #如果推荐项目为空，top_1=“0”；当推荐列表不足 3 项时按实际项数评判；当标准列表为空或仅包含空字符串时，top_1=“0”、top_3=“0”。
        if not recs or recs[0] == "":
            return JudgeResponse(judge_result=JudgeResult(top_1="0", top_3="0")).model_dump()
        if len(recs) < 3:
            return JudgeResponse(judge_result=JudgeResult(top_1="1" if recs[0] in stds else "0", top_3="1" if any(r in stds for r in recs) else "0")).model_dump()
        if not stds or stds[0] == "":
            return JudgeResponse(judge_result=JudgeResult(top_1="0", top_3="0")).model_dump()
        judge_result=JudgeResult(
            top_1="1" if recs[0] in stds else "0",
            top_3="1" if any(r in stds for r in recs[:3]) else "0",
        )
        return JudgeResponse(judge_result=judge_result).model_dump()
        

