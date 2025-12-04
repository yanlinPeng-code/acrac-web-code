import hashlib
import json
import asyncio
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate
from backend.app.config.redis_config import redis_manager
from app.config.config import settings
from app.schema.judge_schemas import JudgeRequest
from app.schema.judge_schemas import JudgeResponse
from app.schema.judge_schemas import JudgeResult
from app.prompt.judge_prompt import judge_prompt
from app.utils.logger.simple_logger import get_logger

logger = get_logger(__name__)


class JudgeService:

    def __init__(self):
        # 不在初始化时访问 redis_client，改为延迟访问
        pass

    @property
    def redis_client(self):
        """延迟获取 Redis 客户端，如果未初始化则返回 None"""
        try:
            return redis_manager.async_client
        except RuntimeError:
            # Redis 未初始化（如在 Celery worker 中），返回 None
            logger.debug("Redis 未初始化，缓存功能不可用")
            return None

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

    async def judge_recommendations(self, judge_request: JudgeRequest) -> dict:
        """
        根据LLM评判模型推荐结果
        """
        if judge_request.model_judge:
            return await self.judge_by_llm(judge_request)
        return self.judge_by_str(judge_request)

    async def judge_by_llm(self, judge_request: JudgeRequest) -> dict:
        """
        根据LLM评判模型推荐结果，带Redis缓存
        """
        # 生成缓存键
        cache_data = json.dumps({
            "pred_items": judge_request.pred_items,
            "gold_items": judge_request.gold_items,
            "online_model": judge_request.online_model
        }, sort_keys=True, ensure_ascii=False)
        cache_key = f"judge:llm_result:{hashlib.md5(cache_data.encode()).hexdigest()}"

        # 尝试从缓存获取
        if self.redis_client:
            try:
                cached_result = await self.redis_client.get(cache_key)
                if cached_result:
                    logger.info(f"✅ 从缓存获取LLM评判结果: {cache_key[:20]}...")
                    cached_data = json.loads(cached_result)
                    return JudgeResponse(judge_result=JudgeResult(**cached_data)).model_dump()
            except Exception as e:
                logger.warning(f"⚠️ Redis缓存读取失败: {e}")

        # 缓存未命中，调用LLM
        recs = self._normalize_recs(judge_request.pred_items or [])
        stds = judge_request.gold_items or []

        prompt = ChatPromptTemplate.from_messages([
            ("system", judge_prompt),
            ("user", "推荐列表: {pred_items}\n标准列表: {gold_items}"),
        ])

        if judge_request.online_model:
            llm = ChatDeepSeek(
                model=settings.DEEPSEEK_MODEL_NAME,
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                temperature=1.0,
                streaming=False
            )
        else:
            llm = ChatOpenAI(
                model=settings.OLLAMA_LLM_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                api_key=settings.SILICONFLOW_API_KEY,
                temperature=0.1,
            )

        llm_with_output = llm.with_structured_output(JudgeResult)
        chain = prompt | llm_with_output

        try:
            response = await asyncio.wait_for(
                chain.ainvoke({
                    "pred_items": recs,
                    "gold_items": stds,
                }),
                timeout=300  # 5分钟超时
            )

            # 存入缓存
            if self.redis_client:
                try:
                    await self.redis_client.setex(
                        cache_key,
                        3600,  # 1小时过期
                        json.dumps(response.model_dump(), ensure_ascii=False)
                    )
                    logger.info(f"✅ LLM评判结果已缓存: {cache_key[:20]}...")
                except Exception as e:
                    logger.warning(f"⚠️ Redis缓存写入失败: {e}")

            return JudgeResponse(judge_result=response).model_dump()

        except asyncio.TimeoutError:
            logger.error("❌ LLM评判超时")
            return self.judge_by_str(judge_request)
        except Exception as e:
            logger.error(f"❌ LLM评判失败: {e}")
            return self.judge_by_str(judge_request)

    def judge_by_str(self, judge_request: JudgeRequest) -> dict:
        """
        根据字符串形式匹配推荐项目和标准推荐项目
        """
        recs = self._normalize_recs(judge_request.pred_items or [])
        stds = judge_request.gold_items or []

        if not recs or recs[0] == "":
            return JudgeResponse(judge_result=JudgeResult(top_1="0", top_3="0")).model_dump()

        if len(recs) < 3:
            return JudgeResponse(judge_result=JudgeResult(
                top_1="1" if recs[0] in stds else "0",
                top_3="1" if any(r in stds for r in recs) else "0"
            )).model_dump()

        if not stds or stds[0] == "":
            return JudgeResponse(judge_result=JudgeResult(top_1="0", top_3="0")).model_dump()

        judge_result = JudgeResult(
            top_1="1" if recs[0] in stds else "0",
            top_3="1" if any(r in stds for r in recs[:3]) else "0",
        )
        return JudgeResponse(judge_result=judge_result).model_dump()
