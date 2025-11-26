## 目标

* 在 `backend/app/service/eval_v1/judge_service.py` 中，使用 LangChain 的 `ChatOpenAI` 与 `with_structured_output`。

* 结构化输出直接映射到现有的 Pydantic 模型 `JudgeResult`，返回 `JudgeResponse`。

## 依赖与配置

* 依赖已存在：`langchain`、`langchain-openai`、`pydantic`（均在 `requirements.txt`）。

* 使用 `settings.OPENAI_API_KEY`；模型默认 `gpt-4o-mini`，可通过环境变量 `OPENAI_MODEL` 覆盖。

## 代码改动点

* 新增导入：

  * `from langchain_openai import ChatOpenAI`

  * `from langchain_core.prompts import ChatPromptTemplate`

  * `from app.config.config import settings`

  * `from app.schema.judge_schemas import JudgeResult`

    <br />

* 重写 `judge_by_llm`：构建链 `prompt | llm.with_structured_output(JudgeResult)`；`ainvoke` 返回 `JudgeResult`，封装为 `JudgeResponse`。

* 修正 `judge_recommendations`：返回 `JudgeResponse`（当前未返回）。

* 保留 `judge_by_str` 原逻辑。

## 结构化输出模型

* 直接复用已存在的 `JudgeResult`（字段：`top_1`、`top_3`，字符串“0/1”）。

* 在提示词中明确约束值域，只允许 "0" 或 "1"，并说明含义：

  * `top_1`：推荐列表第 1 项是否命中标准列表（命中为 "1"）。

  * `top_3`：推荐列表前 3 项任一是否命中标准列表（命中为 "1"）。

## 提示词与链

* `ChatPromptTemplate.from_messages`：

  * system：说明评判规则、大小写与空白规范化、仅输出 JSON、字段值域。

  * user：注入 `{recommendations}` 与 `{standards}`。

* 运行链：

  * `structured_llm = self.llm.with_structured_output(JudgeResult)`

  * `chain = self.prompt | structured_llm`

  * `result: JudgeResult = await chain.ainvoke({"recommendations": recs, "standards": stds})`

## 关键实现要点

* 输入归一化：`recommendations` 可能为 `list[str] | list[dict]`，统一提取字符串（如 `id/name/title`）。

* 空输入处理：无推荐或无标准时，`top_1` 与/或 `top_3` 返回 "0"。

* 安全检查：若 `OPENAI_API_KEY` 为空，抛出带指引的异常。

## 示例代码（核心片段）

* 初始化：

```python
class JudgeService:
    def __init__(self):
        self.ai_service = AiService()
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY 未配置")
        self.llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "你是评判助手。根据提供的推荐列表与标准列表，计算 top_1 与 top_3。只返回 JSON；两个字段只能为 \"0\" 或 \"1\"。判定规则：忽略大小写与首尾空白，top_1 为推荐第1项是否命中标准列表，top_3 为推荐前3项任一是否命中标准列表。"),
            ("user", "推荐列表: {recommendations}\n标准列表: {standards}")
        ])
```

* LLM 评判：

```python
async def judge_by_llm(self, judge_request: JudgeRequest) -> JudgeResponse:
    recs = self._normalize_recs(judge_request.recommendations or [])
    stds = judge_request.standard_recommendations or []
    structured_llm = self.llm.with_structured_output(JudgeResult)
    result: JudgeResult = await (self.prompt | structured_llm).ainvoke({
        "recommendations": recs,
        "standards": stds,
    })
    return JudgeResponse(judge_result=result)
```

* 统一入口：

```python
async def judge_recommendations(self, judge_request: JudgeRequest) -> JudgeResponse:
    if judge_request.model_judge:
        return await self.judge_by_llm(judge_request)
    return self.judge_by_str(judge_request)
```

* 输入归一化：

```python
def _normalize_recs(self, recs):
    out = []
    for r in recs:
        if isinstance(r, str):
            out.append(r.strip())
        elif isinstance(r, dict):
            v = r.get("id") or r.get("name") or r.get("title") or next(iter(r.values()), "")
            out.append(str(v).strip())
        else:
            out.append(str(r).strip())
    return out
```

## 异常与日志

* 捕获 LLM 调用异常并记日志，返回明确错误信息。

* 不打印或持久化任何密钥。

## 验证方案

* 构造样例：

  * `recommendations=["CT胸部", "MRI心脏", "X光"]`

  * `standard_recommendations=["MRI心脏", "超声"]`

* 期待：`top_1="0"`，`top_3="1"`。

* 通过接口 `POST /api/v1/judge` 实测，确认返回 `BaseResponse[JudgeResponse]` 中的 `judge_result` 字段。

