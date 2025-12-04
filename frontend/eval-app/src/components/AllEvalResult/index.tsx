/**
 * 所有接口并发评测结果展示组件
 */

import { Card, Table, Row, Col, Statistic, Space, Typography, Alert, Tabs } from "antd"
import {
  ClockCircleOutlined,
  CheckCircleOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  CloseCircleOutlined,
  BarChartOutlined,
} from "@ant-design/icons"
import type { ColumnsType } from "antd/es/table"
import type { AllEvaluationData, EndpointSummary } from "../../types/evaluation"
import { formatPercentage } from "../../utils/format"
import VChartComparison from "../VChartComparison"

const { Text } = Typography

interface AllEvalResultProps {
  result: AllEvaluationData
  clientLatency: number | null
}

export default function AllEvalResult({ result, clientLatency }: AllEvalResultProps) {
  // 如果有新的endpoint_summary数据，则显示它（Sheet 5数据）
  if (result.endpoint_summary && result.endpoint_summary.length > 0) {
    const summaryColumns: ColumnsType<EndpointSummary> = [
      {
        title: "接口名称",
        dataIndex: "api_name",
        key: "api_name",
        width: 250,
      },
      {
        title: "Top1命中数",
        dataIndex: "top1_hit_count",
        key: "top1_hit_count",
        width: 120,
      },
      {
        title: "Top3命中数",
        dataIndex: "top3_hit_count",
        key: "top3_hit_count",
        width: 120,
      },
      {
        title: "Top1准确率",
        dataIndex: "top1_accuracy",
        key: "top1_accuracy",
        width: 120,
        render: (value: number) => formatPercentage(value),
      },
      {
        title: "Top3准确率",
        dataIndex: "top3_accuracy",
        key: "top3_accuracy",
        width: 120,
        render: (value: number) => formatPercentage(value),
      },
      {
        title: "平均响应时间(ms)",
        dataIndex: "avg_response_time_ms",
        key: "avg_response_time_ms",
        width: 150,
      },
      {
        title: "总耗时(ms)",
        dataIndex: "total_time_ms",
        key: "total_time_ms",
        width: 120,
      },
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
                value={result.endpoint_summary.length}
                prefix={<ApiOutlined />}
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="平均Top1准确率"
                value={formatPercentage(
                  result.endpoint_summary.reduce((sum, item) => sum + item.top1_accuracy, 0) /
                  result.endpoint_summary.length
                )}
                valueStyle={{ color: "#3f8600" }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="平均响应时间"
                value={Math.round(
                  result.endpoint_summary.reduce((sum, item) => sum + item.avg_response_time_ms, 0) /
                  result.endpoint_summary.length
                )}
                suffix="ms"
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
        </Row>

        <Card title="接口评测结果对比">
          <Tabs
            defaultActiveKey="table"
            items={[
              {
                key: 'table',
                label: (
                  <span>
                    <ApiOutlined />
                    数据表格
                  </span>
                ),
                children: (
                  <Table
                    dataSource={result.endpoint_summary}
                    columns={summaryColumns}
                    pagination={false}
                    rowKey="api_name"
                    scroll={{ x: 'max-content' }}
                  />
                )
              },
              {
                key: 'vchart',
                label: (
                  <span>
                    <BarChartOutlined />
                    可视化图表
                  </span>
                ),
                children: <VChartComparison data={result.endpoint_summary} />
              }
            ]}
          />
        </Card>
      </Space>
    )
  }

  // 兼容旧的endpoint_results数据格式
  if (!result.endpoint_results || !result.summary) {
    return (
      <Alert
        message="暂无评测结果"
        description="评测结果数据格式不正确"
        type="warning"
        showIcon
      />
    )
  }

  // 原有的详细展示逻辑（保留以兼容旧版本）
  const detailColumns: ColumnsType<any> = [
    { title: "临床场景", dataIndex: "clinical_scenario", width: 300 },
    { title: "标准答案", dataIndex: "standard_answer", width: 150 },
    {
      title: "推荐",
      dataIndex: "recommendations",
      width: 250,
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
