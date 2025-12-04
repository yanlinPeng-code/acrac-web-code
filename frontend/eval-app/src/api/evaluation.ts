/**
 * API请求函数
 * 封装所有评测相关的API调用
 */

import { getApiUrl, API_PATHS } from "./config"
import type {
  EvaluationParams,
  SingleEvalResponse,
  AllEvalResponse,
} from "../types/evaluation"

/**
 * 构造FormData
 */
const buildFormData = (params: EvaluationParams): FormData => {
  const form = new FormData()

  // 添加文件
  form.append("file", params.file)

  // 核心参数
  form.append("top_scenarios", String(params.top_scenarios))
  form.append("top_recommendations_per_scenario", String(params.top_recommendations_per_scenario))
  form.append("similarity_threshold", String(params.similarity_threshold))
  form.append("min_appropriateness_rating", String(params.min_appropriateness_rating))

  // 可选参数 - limit
  if (params.limit !== undefined && params.limit !== null) {
    form.append("limit", String(params.limit))
  }

  // 可选参数
  if (params.endpoint) {
    form.append("endpoint", params.endpoint)
  }
  if (params.standard_query){
      form.append("standard_query",params.standard_query)
  }

  if (params.enable_reranking !== undefined) {
    form.append("enable_reranking", String(params.enable_reranking))
  }

  if (params.need_llm_recommendations !== undefined) {
    form.append("need_llm_recommendations", String(params.need_llm_recommendations))
  }

  if (params.apply_rule_filter !== undefined) {
    form.append("apply_rule_filter", String(params.apply_rule_filter))
  }

  if (params.show_reasoning !== undefined) {
    form.append("show_reasoning", String(params.show_reasoning))
  }

  if (params.include_raw_data !== undefined) {
    form.append("include_raw_data", String(params.include_raw_data))
  }

  if (params.debug_mode !== undefined) {
    form.append("debug_mode", String(params.debug_mode))
  }

  if (params.compute_ragas !== undefined) {
    form.append("compute_ragas", String(params.compute_ragas))
  }

  if (params.ground_truth) {
    form.append("ground_truth", params.ground_truth)
  }

  if (params.session_id) {
    form.append("session_id", params.session_id)
  }

  if (params.patient_id) {
    form.append("patient_id", params.patient_id)
  }

  if (params.doctor_id) {
    form.append("doctor_id", params.doctor_id)
  }

  return form
}

/**
 * 评测单个接口
 */
export const evaluateSingleEndpoint = async (
  params: EvaluationParams
): Promise<SingleEvalResponse> => {
  const url = getApiUrl(API_PATHS.EVALUATE_SINGLE)
  const formData = buildFormData(params)

  const response = await fetch(url, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const json = await response.json()

  if (!json?.Data) {
    throw new Error(json?.Message || "响应数据格式错误")
  }

  return json
}

/**
 * 评测所有接口（异步提交）
 */
export const evaluateAllEndpoints = async (
  params: Omit<EvaluationParams, "endpoint">
): Promise<{ Code: number; Data: { task_id: string; status: string }; Message: string }> => {
  const url = getApiUrl(API_PATHS.EVALUATE_ALL)
  const formData = buildFormData(params as EvaluationParams)

  const response = await fetch(url, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const json = await response.json()

  if (!json?.Data) {
    throw new Error(json?.Message || "响应数据格式错误")
  }

  return json
}

/**
 * 预览Excel数据
 */
export const previewExcelData = async (file: File): Promise<{
  Code: number
  Data: {
    preview: any[]
    total_rows: number
    preview_limit: number
    filename: string
  }
  Message: string
}> => {
  const url = getApiUrl(API_PATHS.PREVIEW_EXCEL)
  const formData = new FormData()
  formData.append("file", file)

  const response = await fetch(url, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const json = await response.json()

  if (!json?.Data) {
    throw new Error(json?.Message || "响应数据格式错误")
  }

  return json
}

/**
 * 查询任务状态
 */
export const getTaskStatus = async (taskId: string): Promise<AllEvalResponse> => {
  const url = `${getApiUrl(API_PATHS.EVALUATE_ALL).replace('/all', '')}/task/${taskId}`

  const response = await fetch(url, {
    method: "GET",
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const json = await response.json()

  if (!json?.Data) {
    throw new Error(json?.Message || "响应数据格式错误")
  }

  return json
}
