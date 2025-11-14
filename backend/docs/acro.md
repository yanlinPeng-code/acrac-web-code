

# acro

推荐系统

Base URLs:

# Authentication

# 推荐模块

<a id="opIdrag_recommend_api_v1_recommend_post"></a>

## POST 推荐

POST /api/v1/recommend

推荐

> Body 请求参数

```json
{
  "patient_info": {
    "age": 150,
    "gender": "string",
    "pregnancy_status": "string",
    "allergies": [
      "string"
    ],
    "comorbidities": [
      "string"
    ],
    "physical_examination": "string"
  },
  "clinical_context": {
    "department": "string",
    "chief_complaint": "string",
    "medical_history": "string",
    "present_illness": "string",
    "diagnosis": "string",
    "symptom_duration": "string",
    "symptom_severity": "string"
  },
  "search_strategy": {
    "vector_weight": 0.4,
    "keyword_weight": 0.3,
    "rule_weight": 0.3,
    "enable_reranking": true,
    "apply_contraindication_filter": true
  },
  "is_need_structure_filter": false,
  "top_scenarios": 10,
  "top_recommendations_per_scenario": 5,
  "show_reasoning": true,
  "include_raw_data": false,
  "debug_mode": false,
  "similarity_threshold": 0.6,
  "min_appropriateness_rating": 1,
  "compute_ragas": false,
  "ground_truth": "string"
}
```

### 请求参数

|名称|位置|类型|必选|中文名|说明|
|---|---|---|---|---|---|
|body|body|[IntelligentRecommendationRequest](#schemaintelligentrecommendationrequest)| 是 | IntelligentRecommendationRequest|none|

> 返回示例

> 200 Response

```json
{
  "RequestId": "string",
  "Code": "string",
  "Message": "string",
  "HostId": "string",
  "Data": {
    "query": "string",
    "best_recommendations": [
      null
    ],
    "contexts": [
      "string"
    ],
    "processing_time_ms": 0,
    "model_used": "string",
    "reranker_model_used": "string",
    "similarity_threshold": 0,
    "max_similarity": 0,
    "is_low_similarity_mode": true,
    "llm_raw_response": "string",
    "debug_info": {},
    "trace": {}
  },
  "Success": true
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Successful Response|[BaseResponse_IntelligentRecommendationResponse_](#schemabaseresponse_intelligentrecommendationresponse_)|
|422|[Unprocessable Entity](https://tools.ietf.org/html/rfc2518#section-10.3)|Validation Error|[HTTPValidationError](#schemahttpvalidationerror)|

# 数据模型

<h2 id="tocS_BaseResponse_IntelligentRecommendationResponse_">BaseResponse_IntelligentRecommendationResponse_</h2>

```json
{
  "RequestId": "string",
  "Code": "string",
  "Message": "string",
  "HostId": "string",
  "Data": {
    "query": "string",
    "best_recommendations": [
      null
    ],
    "contexts": [
      "string"
    ],
    "processing_time_ms": 0,
    "model_used": "string",
    "reranker_model_used": "string",
    "similarity_threshold": 0,
    "max_similarity": 0,
    "is_low_similarity_mode": true,
    "llm_raw_response": "string",
    "debug_info": {},
    "trace": {}
  },
  "Success": true
}

```

<h2 id="tocS_ClinicalContext">ClinicalContext</h2>



```json
{
  "department": "string",
  "chief_complaint": "string",
  "medical_history": "string",
  "present_illness": "string",
  "diagnosis": "string",
  "symptom_duration": "string",
  "symptom_severity": "string"
}

```

<h2 id="tocS_IntelligentRecommendationRequest">IntelligentRecommendationRequest</h2>



```json
{
  "patient_info": {
    "age": 150,
    "gender": "string",
    "pregnancy_status": "string",
    "allergies": [
      "string"
    ],
    "comorbidities": [
      "string"
    ],
    "physical_examination": "string"
  },
  "clinical_context": {
    "department": "string",
    "chief_complaint": "string",
    "medical_history": "string",
    "present_illness": "string",
    "diagnosis": "string",
    "symptom_duration": "string",
    "symptom_severity": "string"
  },
  "search_strategy": {
    "vector_weight": 0.4,
    "keyword_weight": 0.3,
    "rule_weight": 0.3,
    "enable_reranking": true,
    "apply_contraindication_filter": true
  },
  "is_need_structure_filter": false,
  "top_scenarios": 10,
  "top_recommendations_per_scenario": 5,
  "show_reasoning": true,
  "include_raw_data": false,
  "debug_mode": false,
  "similarity_threshold": 0.6,
  "min_appropriateness_rating": 1,
  "compute_ragas": false,
  "ground_truth": "string"
}

```

<h2 id="tocS_IntelligentRecommendationResponse">IntelligentRecommendationResponse</h2>

```json
{
  "query": "string",
  "best_recommendations": [
    null
  ],
  "contexts": [
    "string"
  ],
  "processing_time_ms": 0,
  "model_used": "string",
  "reranker_model_used": "string",
  "similarity_threshold": 0,
  "max_similarity": 0,
  "is_low_similarity_mode": true,
  "llm_raw_response": "string",
  "debug_info": {},
  "trace": {}
}

```

<h2 id="tocS_PatientInfo">PatientInfo</h2>

```json
{
  "age": 150,
  "gender": "string",
  "pregnancy_status": "string",
  "allergies": [
    "string"
  ],
  "comorbidities": [
    "string"
  ],
  "physical_examination": "string"
}

```

<h2 id="tocS_SearchStrategy">SearchStrategy</h2>

```json
{
  "vector_weight": 0.4,
  "keyword_weight": 0.3,
  "rule_weight": 0.3,
  "enable_reranking": true,
  "apply_contraindication_filter": true
}

```





