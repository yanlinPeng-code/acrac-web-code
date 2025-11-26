/**
 * 数据转换工具函数
 */

import type { EvaluationDetail } from "../types/evaluation"

/**
 * 格式化百分比
 */
export const formatPercentage = (value: number): string => {
  return `${(value * 100).toFixed(2)}%`
}

/**
 * 格式化推荐结果
 */
export const formatRecommendations = (recommendations: any): string => {
  if (Array.isArray(recommendations)) {
    if (recommendations.length === 0) return "-"

    if (Array.isArray(recommendations[0])) {
      // 多场景情况
      return recommendations.map((group: any) => group.join("，")).join(" | ")
    } else {
      // 单场景情况
      return recommendations.join("，")
    }
  }
  return String(recommendations)
}

/**
 * 格式化场景命中情况
 */
export const formatScenarioHits = (hits?: number[]): string => {
  if (!hits || !Array.isArray(hits)) return "-"
  return hits.join(" / ")
}

/**
 * 生成随机ID
 */
export const generateRandomId = (): string => {
  return String(Math.floor(Math.random() * 900000) + 100000)
}

/**
 * 判断是否应该显示参数（根据endpoint类型和是否上传文件）
 */
export const shouldShowParam = (
  paramName: string,
  endpoint: string,
  hasFile: boolean
): boolean => {
  // 核心参数总是显示
  const coreParams = [
    "topScenarios",
    "topRecommendationsPerScenario",
    "similarityThreshold",
    "minAppropriatenessRating",
  ]
  if (coreParams.includes(paramName)) {
    return true
  }

  // 没有上传文件时，显示standard_query等非文件模式参数
  if (!hasFile) {
     if (endpoint === "recommend" || endpoint === "recommend-simple") {
          const recommendParams = [
              "standardQuery",
              "patientInfo",
              "clinicalContext",
              "goldAnswer",
              "enableReranking",
              "needLLMRecommendations",
              "applyRuleFilter",
      ]
      return recommendParams.includes(paramName)
     }
     if (endpoint === "intelligent-recommendation") {
      const intelligentParams = [
          "standardQuery",
           "goldAnswer",
        "showReasoning",
        "includeRawData",
        "debugMode",
        "computeRagas",
        "groundTruth",
      ]
      return intelligentParams.includes(paramName)
    }
      if (endpoint === "recommend_item_with_reason") {
      const itemParams = [
          "standardQuery",
          "patientInfo",
          "clinicalContext",
          "goldAnswer",
        "sessionId",
        "patientId",
        "doctorId",
      ]
      return itemParams.includes(paramName)
    }




  }

  // 上传文件后，隐藏非文件模式参数，显示endpoint特定参数
  if (hasFile) {
    // 根据不同endpoint显示不同的特定参数
    if (endpoint === "recommend" || endpoint === "recommend-simple") {
      const recommendParams = [
        "enableReranking",
        "needLLMRecommendations",
        "applyRuleFilter",
      ]
      return recommendParams.includes(paramName)
    }

    if (endpoint === "intelligent-recommendation") {
      const intelligentParams = [
        "showReasoning",
        "includeRawData",
        "debugMode",
        "computeRagas",
        "groundTruth",
      ]
      return intelligentParams.includes(paramName)
    }

    if (endpoint === "recommend_item_with_reason") {
      const itemParams = [
        "sessionId",
        "patientId",
        "doctorId",
      ]
      return itemParams.includes(paramName)
    }
  }

  return false
}
