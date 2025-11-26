/**
 * 数据类型定义
 */

// 评测模式
export type EvalMode = "single" | "all"

// 支持的endpoint类型
export type EndpointType = "recommend" | "recommend-simple" | "intelligent-recommendation" | "recommend_item_with_reason"

// 评测详情
export interface EvaluationDetail {
  clinical_scenario: string
  standard_answer: string
  recommendations: any
  per_scenario_hits?: number[]
  hit: boolean
  processing_time_ms: number
}

// 组合结果
export interface CombinationResult {
  accuracy: number
  total_samples: number
  hit_samples: number
  details: EvaluationDetail[]
}

// 变体结果
export interface VariantResult {
  label: string
  accuracy: number
  total_samples: number
  hit_samples: number
  details: EvaluationDetail[]
}

// 单个接口评测响应数据
export interface SingleEvaluationData {
  overall_accuracy: number
  combination_a: CombinationResult
  combination_b: CombinationResult
  variants?: VariantResult[]
  average_processing_time_ms: number
  total_samples: number
}

// 单个接口评测响应
export interface SingleEvalResponse {
  RequestId: string
  Data: SingleEvaluationData
}

// 所有接口评测汇总
export interface AllEvaluationSummary {
  total_endpoints_tested: number
  successful_endpoints: number
  failed_endpoints: number
  average_overall_accuracy: number
  average_processing_time_ms: number
  total_samples: number
}

// 接口评测结果
export interface EndpointEvalResult {
  status: string
  result?: SingleEvaluationData
  error?: string
}

// 所有接口评测响应数据
export interface AllEvaluationData {
  summary: AllEvaluationSummary
  endpoint_results: {
    [key: string]: EndpointEvalResult
  }
  csv_file_path?: string
}

// 所有接口评测响应
export interface AllEvalResponse {
  RequestId: string
  Data: AllEvaluationData
}

// 评测请求参数
export interface EvaluationParams {
  file: File
  endpoint?: EndpointType
  standard_query?:string
  top_scenarios: number
  top_recommendations_per_scenario: number
  similarity_threshold: number
  min_appropriateness_rating: number
  // recommend/recommend-simple 特有参数
  enable_reranking?: boolean
  need_llm_recommendations?: boolean
  apply_rule_filter?: boolean
  // intelligent-recommendation 特有参数
  show_reasoning?: boolean
  include_raw_data?: boolean
  debug_mode?: boolean
  compute_ragas?: boolean
  ground_truth?: string
  // recommend_item_with_reason 特有参数
  session_id?: string
  patient_id?: string
  doctor_id?: string
}
