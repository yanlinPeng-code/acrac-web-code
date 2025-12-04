"""
查询标准化服务
使用LLM将用户的自然语言输入转换为符合ACR标准的结构化文本
参考test_clinical_scenarios_embedding.py中的实现方式，使用SiliconFlow兼容接口
"""
import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from app.config.config import settings
from app.schema.IntelligentRecommendation_schemas import ClinicalContext, PatientInfo
from app.utils.logger.simple_logger import get_logger

logger = get_logger(__name__)


class AiService:
    """AI服务，提供查询标准化功能"""

    _client: Optional[httpx.AsyncClient] = None
    _client_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        """初始化AI服务配置"""
        self.llm_model_name = settings.OLLAMA_LLM_MODEL
        self.api_key = settings.SILICONFLOW_API_KEY
        self.base_url = settings.OLLAMA_BASE_URL

    @classmethod
    async def _get_client(cls) -> httpx.AsyncClient:
        """获取共享的HTTP客户端，避免重复建连"""
        if cls._client is None:
            async with cls._client_lock:
                if cls._client is None:
                    cls._client = httpx.AsyncClient(
                        base_url=settings.OLLAMA_BASE_URL,
                        headers={
                            "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        timeout=httpx.Timeout(300.0, connect=5.0),
                        transport=httpx.AsyncHTTPTransport(retries=2)
                    )
        return cls._client

    @classmethod
    async def close_client(cls) -> None:
        """关闭共享的HTTP客户端"""
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None

    async def standardize_query(
        self,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext
    ) -> str:
        """将患者信息和临床上下文标准化为ACR格式文本"""
        try:
            prompt = self._build_standardization_prompt(patient_info, clinical_context)
            standardized_text = await self._call_llm(prompt)
            logger.info("查询标准化成功，输出长度: %s", len(standardized_text))
            return standardized_text
        except Exception as exc:  # noqa: BLE001 - 需要降级兜底
            logger.error("LLM标准化失败，降级到简单模板: %s", exc)
            return self._simple_standardization(patient_info, clinical_context)

    def _build_standardization_prompt(
        self,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext
    ) -> str:
        """构建标准化提示词，指导LLM生成结构化描述"""
        user_input_parts: List[str] = []
        if patient_info.age:
            user_input_parts.append(f"年龄: {patient_info.age}岁")

        if patient_info.gender:
            user_input_parts.append(f"性别: {patient_info.gender}")
        if patient_info.gender == "女" and patient_info.pregnancy_status:
            user_input_parts.append(f"妊娠状态: {patient_info.pregnancy_status}")
        if patient_info.comorbidities:
            user_input_parts.append(f"合并症: {', '.join(patient_info.comorbidities)}")
        if patient_info.physical_examination:
            user_input_parts.append(f"检查报告: {', '.join(patient_info.physical_examination)}")
        if patient_info.pregnancy_status and patient_info.allergies:
            user_input_parts.append(f"过敏史: {', '.join(patient_info.allergies)}")

        if clinical_context.department:
            user_input_parts.append(f"科室: {clinical_context.department}")
        if clinical_context.chief_complaint:
            user_input_parts.append(f"主诉: {clinical_context.chief_complaint}")
        if clinical_context.present_illness:
            user_input_parts.append(f"现病史: {clinical_context.present_illness}")
        if clinical_context.symptom_severity:
            user_input_parts.append(f"症状严重程度: {clinical_context.symptom_severity}")
        if clinical_context.symptom_duration:
            user_input_parts.append(f"症状持续时间: {clinical_context.symptom_duration}")
        if clinical_context.medical_history:
            user_input_parts.append(f"既往病史: {clinical_context.medical_history}")
        if clinical_context.diagnosis:
            user_input_parts.append(f"医生主诊断: {clinical_context.diagnosis}")

        user_input = "\n".join(user_input_parts)
        return (
            "你是医学信息标准化专家。请将患者信息转换为简洁、专业的临床场景描述。\n\n"
            "【患者信息】\n"
            f"{user_input}\n\n"
            "【输出要求】\n"
            "1. 用简洁的医学术语描述临床场景。\n"
            "2. 突出关键信息：年龄段、性别、主要症状、特殊状态（如妊娠）、风险因素等。\n"
            "3. 格式示例：\"科室: 乳腺外科 ,临床场景: 32岁，妊娠期，左侧乳房可触及肿块伴轻微疼痛，无乳腺癌家族史，初始影像学检查。\"\n"
            "4. 只输出标准化描述，不要其他解释。\n"
            "5. 保持完整语义与标点。\n\n"
            "标准化描述：\n"
        )

    async def _post_chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用聊天补全接口并返回JSON结果"""
        client = await self._get_client()
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM并解析文本输出"""
        payload: Dict[str, Any] = {
            "model": self.llm_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        result = await self._post_chat_completion(payload)
        try:
            content = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("LLM响应结构异常: %s - 响应: %s", exc, result)
            raise
        return content

    async def _stream_llm(self, prompt: str):
        """以流式方式调用LLM，逐段产出文本。

        优先尝试服务端的流式接口（SSE/分块），若不可用则回退为一次性响应并切分行。
        """
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "model": self.llm_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "stream": True
        }
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_lines():
                    if not chunk:
                        continue
                    if chunk.startswith("data:"):
                        try:
                            data_str = chunk[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            obj = json.loads(data_str)
                            delta = (
                                obj.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                yield delta
                        except Exception:
                            continue
                    else:
                        # 非SSE格式，直接输出行内容
                        yield chunk
        except Exception:
            # 回退：一次性调用并逐行输出
            text = await self._call_llm(prompt)
            for line in text.splitlines():
                if line.strip():
                    yield line

    def _simple_standardization(
        self,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext
    ) -> str:
        """简单模板式标准化（降级方案）"""
        parts: List[str] = []

        if patient_info.age or patient_info.gender:
            age_str = f"{patient_info.age}岁" if patient_info.age else ""
            gender_str = patient_info.gender or ""
            if age_str and gender_str:
                parts.append(f"{age_str}的{gender_str}患者")
            elif age_str:
                parts.append(f"{age_str}患者")
            elif gender_str:
                parts.append(f"{gender_str}患者")

        if clinical_context.chief_complaint:
            parts.append(f"主诉{clinical_context.chief_complaint}")
        if clinical_context.present_illness:
            parts.append(clinical_context.present_illness[:100])
        if clinical_context.medical_history:
            parts.append(f"既往{clinical_context.medical_history[:100]}")
        if clinical_context.diagnosis:
            parts.append(f"临床诊断考虑{clinical_context.diagnosis}")
        if patient_info.pregnancy_status and patient_info.pregnancy_status != "not_applicable":
            parts.append(patient_info.pregnancy_status)
        if getattr(clinical_context, "urgency_level", None):
            parts.append(f"紧急程度{clinical_context.urgency_level}")

        return "，".join(parts) + "。"

    async def extract_medical_keywords_by_llm(
        self,
        text: str,
        top_k: int = 20
    ) -> List[str]:
        """使用LLM提取文本中的医学关键词"""
        # prompt = f"""你是医学文本分析专家。请从以下临床描述中提取关键的医学术语和症状词汇：\n\n【临床描述】\n{text}\n\n【提取要求】\n1. 提取所有重要的医学术语（疾病、症状、状态、部位等）。\n2. 保留完整的医学词组（如“非妊娠期”、“持续性头痛”、“急性发作”）。\n3. 特别注意否定状态词（如“非妊娠”、“非孕”等）。\n4. 按重要性排序，最多提取{top_k}个关键词。\n5. 只输出关键词列表，用逗号分隔，不要其他解释。\n\n关键词：\n"""
        # payload: Dict[str, Any] = {
        #     "model": self.llm_model_name,
        #     "messages": [{"role": "user", "content": prompt}],
        #     "temperature": 0.2,
        #     "max_tokens": 300
        # }
        # try:
        #     result = await self._post_chat_completion(payload)
        #     keywords_str = result["choices"][0]["message"]["content"].strip()
        # except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        #     logger.error("LLM关键词提取异常: %s", exc)
        #     return []
        #
        # keywords = [item.strip() for item in keywords_str.replace('\n', ',').split(',') if item.strip()]
        # logger.info("LLM提取了%s个关键词: %s", len(keywords), keywords[:10])
        return []
if __name__ == '__main__':
   async def mian():
    res=await AiService()._call_llm("你好")
    print(res)
   asyncio.run(mian())

