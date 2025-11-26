/**
 * API配置文件
 * 统一管理所有API的URL配置
 */

// 基础URL配置
export const API_BASE_URL = "http://localhost:8000"

// API路径
export const API_PATHS = {
  // 单个接口评测
  EVALUATE_SINGLE: "/api/v1/evaluate-recommend",

  // 所有接口并发评测
  EVALUATE_ALL: "/api/v1/evaluate-recommend/all",
} as const

// 支持的endpoint列表
export const ENDPOINTS = {
  RECOMMEND: "recommend",
  RECOMMEND_SIMPLE: "recommend-simple",
  INTELLIGENT_RECOMMENDATION: "intelligent-recommendation",
  RECOMMEND_ITEM_WITH_REASON: "recommend_item_with_reason",
} as const

// Endpoint显示名称映射
export const ENDPOINT_LABELS = {
  [ENDPOINTS.RECOMMEND]: "Recommend",
  [ENDPOINTS.RECOMMEND_SIMPLE]: "Recommend Simple",
  [ENDPOINTS.INTELLIGENT_RECOMMENDATION]: "Intelligent Recommendation",
  [ENDPOINTS.RECOMMEND_ITEM_WITH_REASON]: "Recommend Item With Reason",
} as const

// 构造完整的API URL
export const getApiUrl = (path: string): string => {
  return `${API_BASE_URL}${path}`
}
