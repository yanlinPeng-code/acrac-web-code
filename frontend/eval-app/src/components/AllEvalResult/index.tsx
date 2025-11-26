/**
 * 所有接口并发评测结果展示组件
 */

import { Card, Table, Tabs, Row, Col, Statistic, Space, Typography, Alert } from "antd"
import {
  ClockCircleOutlined,
  CheckCircleOutlined,
  ApiOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons"
import type { ColumnsType } from "antd/es/table"
import type { AllEvaluationData, EvaluationDetail } from "../../types/evaluation"
import { formatPercentage, formatRecommendations, formatScenarioHits } from "../../utils/format"

const { Text } = Typography

interface AllEvalResultProps {
  result: AllEvaluationData
  clientLatency: number | null
}

export default function AllEvalResult({ result, clientLatency }: AllEvalResultProps) {
  // 明细表列定义
  const detailColumns: ColumnsType<EvaluationDetail> = [
    { title: "临床场景", dataIndex: "clinical_scenario", width: 300 },
    { title: "标准答案", dataIndex: "standard_answer", width: 150 },
    {
      title: "推荐",
      dataIndex: "recommendations",
      width: 250,
      render: (v: any) => formatRecommendations(v),
    },
    {
      title: "逐场景命中",
      dataIndex: "per_scenario_hits",
      width: 120,
      render: (v: number[]) => formatScenarioHits(v),
    },
    {
      title: "命中",
      dataIndex: "hit",
      width: 80,
      render: (v: boolean) => (v ? "✓" : "✗"),
    },
    { title: "耗时(ms)", dataIndex: "processing_time_ms", width: 100 },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="端到端耗时"
              value={clientLatency ?? 0}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="测试接口数"
              value={result.summary.total_endpoints_tested}
              prefix={<ApiOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="成功接口数"
              value={result.summary.successful_endpoints}
              valueStyle={{ color: "#3f8600" }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="失败接口数"
              value={result.summary.failed_endpoints}
              valueStyle={{ color: "#cf1322" }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card>
            <Statistic
              title="平均命中率"
              value={formatPercentage(result.summary.average_overall_accuracy)}
              valueStyle={{ color: "#1890ff" }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card>
            <Statistic
              title="平均处理时间"
              value={result.summary.average_processing_time_ms}
              suffix="ms"
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {result.csv_file_path && (
        <Alert
          message="评测结果已保存"
          description={
            <div>
              <Text>CSV文件路径: </Text>
              <Text code>{result.csv_file_path}</Text>
            </div>
          }
          type="success"
          showIcon
        />
      )}

      <Card title="各接口评测结果">
        <Tabs
          items={Object.entries(result.endpoint_results).map(([endpointName, endpointResult]) => ({
            key: endpointName,
            label: (
              <span>
                {endpointResult.status === "success" ? <CheckCircleOutlined style={{ color: "#52c41a" }} /> : <CloseCircleOutlined style={{ color: "#ff4d4f" }} />}
                {" "}{endpointName}
              </span>
            ),
            children:
              endpointResult.status === "success" && endpointResult.result ? (
                <Space direction="vertical" size="large" style={{ width: "100%" }}>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={8}>
                      <Card size="small">
                        <Statistic
                          title="命中率"
                          value={formatPercentage(endpointResult.result.overall_accuracy)}
                          valueStyle={{ color: "#3f8600" }}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} md={8}>
                      <Card size="small">
                        <Statistic
                          title="样本数"
                          value={endpointResult.result.total_samples}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} md={8}>
                      <Card size="small">
                        <Statistic
                          title="平均耗时"
                          value={endpointResult.result.average_processing_time_ms}
                          suffix="ms"
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={[16, 16]}>
                    <Col xs={24} md={12}>
                      <Card title="组合A (1场景/1推荐)" size="small">
                        <Space direction="vertical" style={{ width: "100%" }}>
                          <div>命中率: <Text strong style={{ color: "#1890ff" }}>{formatPercentage(endpointResult.result.combination_a.accuracy)}</Text></div>
                          <div>
                            命中: <Text strong>{endpointResult.result.combination_a.hit_samples}</Text> / {endpointResult.result.combination_a.total_samples}
                          </div>
                        </Space>
                      </Card>
                    </Col>
                    <Col xs={24} md={12}>
                      <Card title="组合B (3场景/3推荐)" size="small">
                        <Space direction="vertical" style={{ width: "100%" }}>
                          <div>命中率: <Text strong style={{ color: "#1890ff" }}>{formatPercentage(endpointResult.result.combination_b.accuracy)}</Text></div>
                          <div>
                            命中: <Text strong>{endpointResult.result.combination_b.hit_samples}</Text> / {endpointResult.result.combination_b.total_samples}
                          </div>
                        </Space>
                      </Card>
                    </Col>
                  </Row>

                  <Table
                    rowKey={(r, i) => `${endpointName}_${i}`}
                    columns={detailColumns}
                    dataSource={endpointResult.result.combination_b.details}
                    pagination={{ pageSize: 10 }}
                    scroll={{ x: 1200 }}
                  />
                </Space>
              ) : (
                <Alert
                  message="评测失败"
                  description={endpointResult.error || "未知错误"}
                  type="error"
                  showIcon
                />
              ),
          }))}
        />
      </Card>
    </Space>
  )
}
