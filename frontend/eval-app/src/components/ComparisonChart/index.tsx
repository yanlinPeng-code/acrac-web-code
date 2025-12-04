/**
 * 接口对比可视化组件
 */

import { Card, Row, Col, Statistic, Progress, Table, Typography, Tag, Space } from "antd"
import {
  TrophyOutlined,
  RocketOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons"

const { Title, Text } = Typography

interface EndpointSummary {
  api_name: string
  top1_hit_count: number
  top3_hit_count: number
  top1_accuracy: number
  top3_accuracy: number
  avg_response_time_ms: number
  total_time_ms: number
}

interface ComparisonChartProps {
  data: EndpointSummary[]
}

export default function ComparisonChart({ data }: ComparisonChartProps) {
  if (!data || data.length === 0) {
    return null
  }

  // 找出最佳接口（top1准确率最高）
  const bestByTop1 = data.reduce((prev, current) =>
    (prev.top1_accuracy > current.top1_accuracy) ? prev : current
  )

  // 找出最快接口（平均响应时间最短）
  const fastestApi = data.reduce((prev, current) =>
    (prev.avg_response_time_ms < current.avg_response_time_ms) ? prev : current
  )

  // 表格列定义
  const columns = [
    {
      title: "接口名称",
      dataIndex: "api_name",
      key: "api_name",
      render: (text: string, record: EndpointSummary) => (
        <Space>
          <Text strong>{text}</Text>
          {record.api_name === bestByTop1.api_name && (
            <Tag color="gold" icon={<TrophyOutlined />}>准确率最高</Tag>
          )}
          {record.api_name === fastestApi.api_name && (
            <Tag color="green" icon={<RocketOutlined />}>响应最快</Tag>
          )}
        </Space>
      ),
    },
    {
      title: "Top1 准确率",
      dataIndex: "top1_accuracy",
      key: "top1_accuracy",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.top1_accuracy - b.top1_accuracy,
      render: (value: number) => (
        <div style={{ width: 150 }}>
          <Progress
            percent={value * 100}
            format={(percent) => `${(percent || 0).toFixed(2)}%`}
            strokeColor={{
              '0%': '#ff4d4f',
              '50%': '#faad14',
              '100%': '#52c41a',
            }}
          />
        </div>
      ),
    },
    {
      title: "Top3 准确率",
      dataIndex: "top3_accuracy",
      key: "top3_accuracy",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.top3_accuracy - b.top3_accuracy,
      render: (value: number) => (
        <div style={{ width: 150 }}>
          <Progress
            percent={value * 100}
            format={(percent) => `${(percent || 0).toFixed(2)}%`}
            strokeColor={{
              '0%': '#ff4d4f',
              '50%': '#faad14',
              '100%': '#52c41a',
            }}
          />
        </div>
      ),
    },
    {
      title: "Top1 命中数",
      dataIndex: "top1_hit_count",
      key: "top1_hit_count",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.top1_hit_count - b.top1_hit_count,
    },
    {
      title: "Top3 命中数",
      dataIndex: "top3_hit_count",
      key: "top3_hit_count",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.top3_hit_count - b.top3_hit_count,
    },
    {
      title: "平均响应时间 (ms)",
      dataIndex: "avg_response_time_ms",
      key: "avg_response_time_ms",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.avg_response_time_ms - b.avg_response_time_ms,
      render: (value: number) => (
        <Text type={value < 1000 ? "success" : value < 3000 ? "warning" : "danger"}>
          {value.toFixed(2)}
        </Text>
      ),
    },
    {
      title: "总耗时 (ms)",
      dataIndex: "total_time_ms",
      key: "total_time_ms",
      sorter: (a: EndpointSummary, b: EndpointSummary) => a.total_time_ms - b.total_time_ms,
      render: (value: number) => value.toFixed(2),
    },
  ]

  // 计算总体统计
  const avgTop1Accuracy = data.reduce((sum, item) => sum + item.top1_accuracy, 0) / data.length
  const avgTop3Accuracy = data.reduce((sum, item) => sum + item.top3_accuracy, 0) / data.length
  const avgResponseTime = data.reduce((sum, item) => sum + item.avg_response_time_ms, 0) / data.length
  const totalHits = data.reduce((sum, item) => sum + item.top1_hit_count, 0)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* 总体统计卡片 */}
      <Card
        title={
          <span>
            <CheckCircleOutlined style={{ marginRight: 8 }} />
            总体统计
          </span>
        }
      >
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均 Top1 准确率"
                value={avgTop1Accuracy * 100}
                precision={2}
                suffix="%"
                valueStyle={{ color: avgTop1Accuracy > 0.7 ? '#3f8600' : avgTop1Accuracy > 0.5 ? '#faad14' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均 Top3 准确率"
                value={avgTop3Accuracy * 100}
                precision={2}
                suffix="%"
                valueStyle={{ color: avgTop3Accuracy > 0.8 ? '#3f8600' : avgTop3Accuracy > 0.6 ? '#faad14' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均响应时间"
                value={avgResponseTime}
                precision={2}
                suffix="ms"
                prefix={<ClockCircleOutlined />}
                valueStyle={{ color: avgResponseTime < 1000 ? '#3f8600' : avgResponseTime < 3000 ? '#faad14' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="总命中数"
                value={totalHits}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 详细对比表格 */}
      <Card
        title={
          <span>
            <TrophyOutlined style={{ marginRight: 8 }} />
            接口详细对比
          </span>
        }
      >
        <Table
          dataSource={data}
          columns={columns}
          rowKey="api_name"
          pagination={false}
          size="middle"
        />
      </Card>

      {/* 可视化对比 - 使用进度条 */}
      <Card title="准确率可视化对比">
        <Row gutter={[16, 24]}>
          {data.map((item) => (
            <Col span={12} key={item.api_name}>
              <Card
                size="small"
                title={
                  <Space>
                    <Text strong>{item.api_name}</Text>
                    {item.api_name === bestByTop1.api_name && (
                      <Tag color="gold" icon={<TrophyOutlined />}>最佳</Tag>
                    )}
                  </Space>
                }
              >
                <div style={{ marginBottom: 16 }}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary">Top1 准确率</Text>
                  </div>
                  <Progress
                    percent={item.top1_accuracy * 100}
                    format={(percent) => `${(percent || 0).toFixed(2)}%`}
                    strokeColor={{
                      '0%': '#ff4d4f',
                      '50%': '#faad14',
                      '100%': '#52c41a',
                    }}
                    strokeWidth={12}
                  />
                </div>
                <div>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary">Top3 准确率</Text>
                  </div>
                  <Progress
                    percent={item.top3_accuracy * 100}
                    format={(percent) => `${(percent || 0).toFixed(2)}%`}
                    strokeColor={{
                      '0%': '#ff7875',
                      '50%': '#ffc069',
                      '100%': '#95de64',
                    }}
                    strokeWidth={12}
                  />
                </div>
                <div style={{ marginTop: 16, textAlign: "center" }}>
                  <Space size="large">
                    <Statistic
                      title="命中数"
                      value={item.top1_hit_count}
                      valueStyle={{ fontSize: 16 }}
                    />
                    <Statistic
                      title="响应时间"
                      value={item.avg_response_time_ms}
                      precision={2}
                      suffix="ms"
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Space>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 性能对比 */}
      <Card title="响应时间对比">
        <Row gutter={16}>
          {data.map((item) => (
            <Col span={6} key={item.api_name}>
              <Card size="small">
                <Statistic
                  title={item.api_name}
                  value={item.avg_response_time_ms}
                  precision={2}
                  suffix="ms"
                  valueStyle={{
                    color: item.api_name === fastestApi.api_name ? '#3f8600' : '#1890ff',
                    fontSize: 20
                  }}
                />
                {item.api_name === fastestApi.api_name && (
                  <div style={{ marginTop: 8 }}>
                    <Tag color="green" icon={<RocketOutlined />}>最快</Tag>
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  )
}
