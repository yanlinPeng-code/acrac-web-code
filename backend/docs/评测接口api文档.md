# 推荐系统评估接口文档

## 概述

本文档描述了推荐系统评估模块的接口规范，用于测试推荐系统的命中率和性能。

## 评估接口

### POST 评估推荐系统

POST /api/v1/evaluate-recommend

评估推荐系统的命中率和性能

> Body 请求参数 (multipart/form-data)

```form
file: [文件] (可选)
endpoint: "recommend" | "recommend-simple"
standard_query: string (可选)
patient_info: JSON字符串 (可选)
clinical_context: JSON字符串 (可选)
enable_reranking: boolean (可选)
need_llm_recommendations: boolean (可选)
apply_rule_filter: boolean (可选)
top_scenarios: number (可选)
top_recommendations_per_scenario: number (可选)
show_reasoning: boolean (可选)
include_raw_data: boolean (可选)
similarity_threshold: number (可选)
min_appropriateness_rating: number (可选)
```

#### 请求参数说明

| 参数名                                 | 类型      | 必填 | 说明                                   |
| :---------------------------------- | :------ | :- | :----------------------------------- |
| file                                | File    | 否  | Excel文件，包含临床场景和标准答案                  |
| endpoint                            | string  | 是  | 评估的接口类型：recommend 或 recommend-simple |
| standard\_query                     | string  | 否  | 标准问题查询                               |
| patient\_info                       | string  | 否  | 患者信息JSON字符串                          |
| clinical\_context                   | string  | 否  | 临床上下文JSON字符串                         |
| enable\_reranking                   | boolean | 否  | 是否启用重排序                              |
| need\_llm\_recommendations          | boolean | 否  | 是否需要LLM推荐                            |
| apply\_rule\_filter                 | boolean | 否  | 是否应用规则过滤                             |
| top\_scenarios                      | number  | 否  | 返回的场景数量                              |
| top\_recommendations\_per\_scenario | number  | 否  | 每个场景的推荐数量                            |
| show\_reasoning                     | boolean | 否  | 是否显示推理过程                             |
| include\_raw\_data                  | boolean | 否  | 是否包含原始数据                             |
| similarity\_threshold               | number  | 否  | 相似度阈值                                |
| min\_appropriateness\_rating        | number  | 否  | 最小适当性评分                              |

#### 输入规则

1. **文件模式**：上传Excel文件后，不能填写`patient_info`、`clinical_context`和`standard_query`
2. **标准问题模式**：填写`standard_query`时，隐藏`patient_info`和`clinical_context`
3. **普通模式**：未上传文件时，可以填写`patient_info`和`clinical_context`或`standard_query`，但两者不能同时填写
4. **必填参数**：在三种模式下，以下参数必填：
   * `enable_reranking`
   * `need_llm_recommendations`
   * `apply_rule_filter`
   * `top_scenarios`
   * `top_recommendations_per_scenario`
   * `similarity_threshold`
   * `min_appropriateness_rating`

> 返回示例

```json
{
  "request_id": "req_123456",
  "code": "200",
  "message": "评估完成",
  "success": true,
  "data": {
    "overall_accuracy": 0.85,
    "combination_a": {
      "accuracy": 0.8,
      "total_samples": 100,
      "hit_samples": 80,
      "details": [
        {
          "clinical_scenario": "头痛伴发热",
          "standard_answer": "头颅CT",
          "recommendations": ["头颅CT", "血常规"],
          "hit": true,
          "processing_time_ms": 120
        }
      ]
    },
    "combination_b": {
      "accuracy": 0.9,
      "total_samples": 100,
      "hit_samples": 90,
      "details": [
        {
          "clinical_scenario": "胸痛",
          "standard_answer": "心电图",
          "recommendations": ["心电图", "胸部X光", "心肌酶谱"],
          "hit": true,
          "processing_time_ms": 150
        }
      ]
    },
    "average_processing_time_ms": 135,
    "total_samples": 100
  }
}
```

### 返回结果

| 状态码 | 说明      | 数据模型               |
| :-- | :------ | :----------------- |
| 200 | 评估成功    | EvaluationResponse |
| 400 | 请求参数错误  | ErrorResponse      |
| 422 | 参数验证失败  | ValidationError    |
| 500 | 服务器内部错误 | ErrorResponse      |

## 评估标准

### 组合A评估

* `top_scenarios = 1`, `top_recommendations_per_scenario = 1`
* 命中条件：唯一推荐等于标准答案
* 命中率 = 命中样本数 / 总样本数

### 组合B评估

* `top_scenarios = 3`, `top_recommendations_per_scenario = 3`
* 命中条件：标准答案出现在任一场景的推荐中
* 命中率 = 命中样本数 / 总样本数

## 数据模型

### EvaluationResponse

```json
{
  "overall_accuracy": 0.85,
  "combination_a": {
    "accuracy": 0.8,
    "total_samples": 100,
    "hit_samples": 80,
    "details": [
      {
        "clinical_scenario": "string",
        "standard_answer": "string",
        "recommendations": ["string"],
        "hit": true,
        "processing_time_ms": 120
      }
    ]
  },
  "combination_b": {
    "accuracy": 0.9,
    "total_samples": 100,
    "hit_samples": 90,
    "details": [
      {
        "clinical_scenario": "string",
        "standard_answer": "string",
        "recommendations": ["string"],
        "hit": true,
        "processing_time_ms": 150
      }
    ]
  },
  "average_processing_time_ms": 135,
  "total_samples": 100
}
```

### EvaluationDetail

```json
{
  "clinical_scenario": "string",
  "standard_answer": "string",
  "recommendations": ["string"],
  "hit": true,
  "processing_time_ms": 120
}
```

### CombinationResult

```json
{
  "accuracy": 0.8,
  "total_samples": 100,
  "hit_samples": 80,
  "details": [EvaluationDetail]
}
```

### ErrorResponse

```json
{
  "request_id": "string",
  "code": "string",
  "message": "string",
  "success": false
}
```

## 前端实现要求

### 界面组件

* 文件上传区域（Antd Upload）
* 接口选择（Radio.Group：recommend / recommend-simple）
* 参数输入区域（动态显示/隐藏）
* 评估按钮
* 结果展示区域

### 显示/隐藏逻辑

1. **上传文件后**：隐藏所有参数输入区域
2. **填写standard\_query**：隐藏patient\_info和clinical\_context
3. **填写patient\_info/clinical\_context**：隐藏standard\_query
4. **非文件模式**：显示必填参数输入区域

### 结果展示

* 总体命中率统计卡片
* 组合A/B详细结果表格
* 处理时间统计
* 样本明细展示

## 技术栈

* 前端：React + TypeScript + TailwindCSS + Ant Design
* 后端：Python + FastAPI
* 文件处理：pandas + openpyxl

