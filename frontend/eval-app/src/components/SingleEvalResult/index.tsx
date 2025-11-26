/**
 * 单个接口评测结果展示组件
 */

import { Card, Table, Tabs, Row, Col, Statistic, Space, Typography } from "antd"
import {
  ClockCircleOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons"
import type { ColumnsType } from "antd/es/table"
import type { SingleEvaluationData, EvaluationDetail, VariantResult } from "../../types/evaluation"
import { formatPercentage, formatRecommendations, formatScenarioHits } from "../../utils/format"

const { Text } = Typography

interface SingleEvalResultProps {
  result: SingleEvaluationData
  clientLatency: number | null
}

export default function SingleEvalResult({ result, clientLatency }: SingleEvalResultProps) {
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

  // 组合对比表列定义
  const variantColumns: ColumnsType<VariantResult> = [
    { title: "组合", dataIndex: "label" },
    { title: "命中率", dataIndex: "accuracy", render: (v: number) => formatPercentage(v) },
    { title: "样本数", dataIndex: "total_samples" },
    { title: "命中样本", dataIndex: "hit_samples" },
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
              title="服务端平均耗时"
              value={result.average_processing_time_ms}
              suffix="ms"
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总体命中率"
              value={formatPercentage(result.overall_accuracy)}
              valueStyle={{ color: "#3f8600" }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="样本数"
              value={result.total_samples}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="组合A (1场景/1推荐)" size="small">
            <Space direction="vertical" style={{ width: "100%" }}>
              <div>
                命中率: <Text strong style={{ fontSize: 16, color: "#1890ff" }}>{formatPercentage(result.combination_a.accuracy)}</Text>
              </div>
              <div>样本数: <Text strong>{result.combination_a.total_samples}</Text></div>
              <div>命中样本: <Text strong>{result.combination_a.hit_samples}</Text></div>
            </Space>
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card title="组合B (3场景/3推荐)" size="small">
            <Space direction="vertical" style={{ width: "100%" }}>
              <div>
                命中率: <Text strong style={{ fontSize: 16, color: "#1890ff" }}>{formatPercentage(result.combination_b.accuracy)}</Text>
              </div>
              <div>样本数: <Text strong>{result.combination_b.total_samples}</Text></div>
              <div>命中样本: <Text strong>{result.combination_b.hit_samples}</Text></div>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: "a",
              label: "组合A明细",
              children: (
                <Table
                  rowKey={(r, i) => `${r.clinical_scenario}_A_${i}`}
                  columns={detailColumns}
                  dataSource={result.combination_a.details}
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 1200 }}
                />
              ),
            },
            {
              key: "b",
              label: "组合B明细",
              children: (
                <Table
                  rowKey={(r, i) => `${r.clinical_scenario}_B_${i}`}
                  columns={detailColumns}
                  dataSource={result.combination_b.details}
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 1200 }}
                />
              ),
            },
            ...(result.variants
              ? [
                  {
                    key: "variants",
                    label: "所有组合对比",
                    children: (
                      <Table
                        rowKey={(r: VariantResult) => r.label}
                        columns={variantColumns}
                        dataSource={result.variants}
                        pagination={false}
                      />
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Card>
    </Space>
  )
}
