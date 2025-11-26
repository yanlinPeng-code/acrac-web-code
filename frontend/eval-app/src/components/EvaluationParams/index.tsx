/**
 * 评测参数配置组件
 */

import { Card, Switch, InputNumber, Input, Row, Col, Typography } from "antd"
import { SettingOutlined } from "@ant-design/icons"
import type { EndpointType } from "../../types/evaluation"
import { shouldShowParam } from "../../utils/format"

const { Text } = Typography
const { TextArea } = Input

interface EvaluationParamsProps {
  endpoint: EndpointType
  hasFile: boolean
  // 非文件模式参数
  standardQuery: string
  setStandardQuery: (value: string) => void
  patientInfo: string
  setPatientInfo: (value: string) => void
  clinicalContext: string
  setClinicalContext: (value: string) => void
  goldAnswer: string
  setGoldAnswer: (value: string) => void
  // 核心参数
  topScenarios: number
  setTopScenarios: (value: number) => void
  topRecommendationsPerScenario: number
  setTopRecommendationsPerScenario: (value: number) => void
  similarityThreshold: number
  setSimilarityThreshold: (value: number) => void
  minAppropriatenessRating: number
  setMinAppropriatenessRating: (value: number) => void
  // recommend/recommend-simple 参数
  enableReranking: boolean
  setEnableReranking: (value: boolean) => void
  needLLMRecommendations: boolean
  setNeedLLMRecommendations: (value: boolean) => void
  applyRuleFilter: boolean
  setApplyRuleFilter: (value: boolean) => void
  // intelligent-recommendation 参数
  showReasoning: boolean
  setShowReasoning: (value: boolean) => void
  includeRawData: boolean
  setIncludeRawData: (value: boolean) => void
  debugMode: boolean
  setDebugMode: (value: boolean) => void
  computeRagas: boolean
  setComputeRagas: (value: boolean) => void
  groundTruth: string
  setGroundTruth: (value: string) => void
  // recommend_item_with_reason 参数
  sessionId: string
  patientId: string
  doctorId: string
}

export default function EvaluationParams(props: EvaluationParamsProps) {
  const { endpoint, hasFile } = props

  const ParamItem = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div style={{ display: "flex", alignItems: "start", gap: 8, width: "100%" }}>
      <Text style={{ minWidth: 160, paddingTop: 4 }}>{label}:</Text>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  )

  return (
    <Card
      title={
        <span>
          <SettingOutlined /> 评测参数
        </span>
      }
    >
      <Row gutter={[16, 16]}>
        {/* 非文件模式参数 */}
        {shouldShowParam("standardQuery", endpoint, hasFile) && (
          <Col xs={24}>
            <ParamItem label="标准问题 (standard_query)">
              <TextArea
                value={props.standardQuery}
                onChange={(e) => props.setStandardQuery(e.target.value)}
                placeholder="输入标准化问题，用于测试推荐系统"
                rows={3}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("patientInfo", endpoint, hasFile) && (
          <Col xs={24}>
            <ParamItem label="患者信息 (patient_info)">
              <TextArea
                value={props.patientInfo}
                onChange={(e) => props.setPatientInfo(e.target.value)}
                placeholder='输入患者信息JSON，例如: {"age": 45, "gender": "女"}'
                rows={3}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("clinicalContext", endpoint, hasFile) && (
          <Col xs={24}>
            <ParamItem label="临床上下文 (clinical_context)">
              <TextArea
                value={props.clinicalContext}
                onChange={(e) => props.setClinicalContext(e.target.value)}
                placeholder='输入临床上下文JSON，例如: {"department": "内科", "chief_complaint": "头痛"}'
                rows={3}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("goldAnswer", endpoint, hasFile) && (
          <Col xs={24}>
            <ParamItem label="标准答案 (gold_answer)">
              <Input
                value={props.goldAnswer}
                onChange={(e) => props.setGoldAnswer(e.target.value)}
                placeholder="输入标准答案，用于评测命中率"
              />
            </ParamItem>
          </Col>
        )}

        {/* 核心参数 */}
        {shouldShowParam("topScenarios", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="场景数 (top_scenarios)">
              <InputNumber
                min={1}
                max={50}
                step={1}
                value={props.topScenarios}
                onChange={(v) => props.setTopScenarios(v || 3)}
                style={{ width: "100%" }}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("topRecommendationsPerScenario", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="每场景推荐数">
              <InputNumber
                min={1}
                max={20}
                step={1}
                value={props.topRecommendationsPerScenario}
                onChange={(v) => props.setTopRecommendationsPerScenario(v || 3)}
                style={{ width: "100%" }}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("similarityThreshold", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="相似度阈值">
              <InputNumber
                min={0.1}
                max={0.9}
                step={0.05}
                value={props.similarityThreshold}
                onChange={(v) => props.setSimilarityThreshold(v || 0.7)}
                style={{ width: "100%" }}
              />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("minAppropriatenessRating", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="最低适宜性评分">
              <InputNumber
                min={1}
                max={9}
                step={1}
                value={props.minAppropriatenessRating}
                onChange={(v) => props.setMinAppropriatenessRating(v || 5)}
                style={{ width: "100%" }}
              />
            </ParamItem>
          </Col>
        )}

        {/* recommend/recommend-simple 特有参数 */}
        {shouldShowParam("enableReranking", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="启用LLM重排序">
              <Switch checked={props.enableReranking} onChange={props.setEnableReranking} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("needLLMRecommendations", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="启用LLM推荐">
              <Switch checked={props.needLLMRecommendations} onChange={props.setNeedLLMRecommendations} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("applyRuleFilter", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="启用规则过滤">
              <Switch checked={props.applyRuleFilter} onChange={props.setApplyRuleFilter} />
            </ParamItem>
          </Col>
        )}

        {/* intelligent-recommendation 特有参数 */}
        {shouldShowParam("showReasoning", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="显示推理过程">
              <Switch checked={props.showReasoning} onChange={props.setShowReasoning} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("includeRawData", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="包含原始数据">
              <Switch checked={props.includeRawData} onChange={props.setIncludeRawData} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("debugMode", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="调试模式">
              <Switch checked={props.debugMode} onChange={props.setDebugMode} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("computeRagas", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="计算RAGAS">
              <Switch checked={props.computeRagas} onChange={props.setComputeRagas} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("groundTruth", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="Ground Truth">
              <Input
                value={props.groundTruth}
                onChange={(e) => props.setGroundTruth(e.target.value)}
                placeholder="可选"
                style={{ width: "100%" }}
              />
            </ParamItem>
          </Col>
        )}

        {/* recommend_item_with_reason 特有参数 */}
        {shouldShowParam("sessionId", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="Session ID">
              <Input value={props.sessionId} disabled style={{ width: "100%" }} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("patientId", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="Patient ID">
              <Input value={props.patientId} disabled style={{ width: "100%" }} />
            </ParamItem>
          </Col>
        )}

        {shouldShowParam("doctorId", endpoint, hasFile) && (
          <Col xs={24} sm={12} md={8}>
            <ParamItem label="Doctor ID">
              <Input value={props.doctorId} disabled style={{ width: "100%" }} />
            </ParamItem>
          </Col>
        )}
      </Row>
    </Card>
  )
}
