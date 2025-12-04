/**
 * 使用 VChart 的接口对比可视化组件
 */

import { Card, Row, Col, Statistic, Typography, Tag, Space } from "antd"
import {
  TrophyOutlined,
  RocketOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons"
import { VChart } from "@visactor/react-vchart"
import type { IBarChartSpec, ILineChartSpec, IRadarChartSpec } from "@visactor/vchart"

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

interface VChartComparisonProps {
  data: EndpointSummary[]
}

export default function VChartComparison({ data }: VChartComparisonProps) {
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

  // 计算总体统计
  const avgTop1Accuracy = data.reduce((sum, item) => sum + item.top1_accuracy, 0) / data.length
  const avgTop3Accuracy = data.reduce((sum, item) => sum + item.top3_accuracy, 0) / data.length
  const avgResponseTime = data.reduce((sum, item) => sum + item.avg_response_time_ms, 0) / data.length
  const totalHits = data.reduce((sum, item) => sum + item.top1_hit_count, 0)

  // 准备准确率对比柱状图数据
  const accuracyBarData = data.flatMap(item => [
    {
      api_name: item.api_name,
      metric: 'Top1准确率',
      value: (item.top1_accuracy * 100).toFixed(2),
      numValue: item.top1_accuracy * 100,
    },
    {
      api_name: item.api_name,
      metric: 'Top3准确率',
      value: (item.top3_accuracy * 100).toFixed(2),
      numValue: item.top3_accuracy * 100,
    }
  ])

  // 准确率对比柱状图配置
  const accuracyBarSpec: IBarChartSpec = {
    type: 'bar',
    data: [
      {
        id: 'barData',
        values: accuracyBarData
      }
    ],
    xField: 'api_name',
    yField: 'numValue',
    seriesField: 'metric',
    bar: {
      style: {
        cornerRadius: [4, 4, 0, 0]
      }
    },
    label: {
      visible: true,
      position: 'top',
      style: {
        fontSize: 12,
        fill: '#333'
      },
      formatMethod: (text: string | string[], datum?: any) => {
        const value = datum?.numValue ?? parseFloat(String(text))
        return `${value.toFixed(2)}%`
      }
    },
    axes: [
      {
        orient: 'left',
        label: {
          formatMethod: (text: string | string[]) => {
            const val = parseFloat(String(text))
            return `${val}%`
          }
        },
        title: {
          visible: true,
          text: '准确率 (%)'
        }
      },
      {
        orient: 'bottom',
        label: {
          style: {
            fontSize: 11
          }
        },
        title: {
          visible: true,
          text: '接口名称'
        }
      }
    ],
    legends: {
      visible: true,
      orient: 'top',
      position: 'middle'
    },
    color: ['#5B8FF9', '#5AD8A6'],
    title: {
      visible: true,
      text: '准确率对比'
    },
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: any) => datum.metric,
            value: (datum: any) => `${datum.value}%`
          }
        ]
      }
    }
  }

  // 准备响应时间折线图数据
  const responseTimeLineData = data.map(item => ({
    api_name: item.api_name,
    avg_time: item.avg_response_time_ms,
    total_time: item.total_time_ms
  }))

  // 响应时间折线图配置
  const responseTimeLineSpec: ILineChartSpec = {
    type: 'line',
    data: [
      {
        id: 'lineData',
        values: responseTimeLineData
      }
    ],
    xField: 'api_name',
    yField: 'avg_time',
    point: {
      visible: true,
      style: {
        size: 6,
        fill: '#FF6B6B'
      }
    },
    line: {
      style: {
        stroke: '#FF6B6B',
        lineWidth: 3,
        lineDash: [0]
      }
    },
    label: {
      visible: true,
      position: 'top',
      style: {
        fontSize: 12,
        fill: '#333'
      },
      formatMethod: (text: string | string[], datum?: any) => {
        const value = datum?.avg_time ?? parseFloat(String(text))
        return `${value.toFixed(2)}ms`
      }
    },
    axes: [
      {
        orient: 'left',
        title: {
          visible: true,
          text: '平均响应时间 (ms)'
        }
      },
      {
        orient: 'bottom',
        label: {
          style: {
            fontSize: 11
          }
        },
        title: {
          visible: true,
          text: '接口名称'
        }
      }
    ],
    title: {
      visible: true,
      text: '响应时间对比'
    },
    tooltip: {
      mark: {
        content: [
          {
            key: '平均响应时间',
            value: (datum: any) => `${datum.avg_time.toFixed(2)}ms`
          },
          {
            key: '总耗时',
            value: (datum: any) => `${datum.total_time.toFixed(2)}ms`
          }
        ]
      }
    }
  }

  // 准备雷达图数据（综合性能对比）
  const radarData = data.map(item => ({
    api_name: item.api_name,
    top1_accuracy: (item.top1_accuracy * 100).toFixed(2),
    top3_accuracy: (item.top3_accuracy * 100).toFixed(2),
    // 响应速度：用倒数表示，越大越好（需要标准化）
    response_speed: (1000 / (item.avg_response_time_ms + 1) * 10).toFixed(2)
  }))

  // 雷达图配置
  const radarSpec: IRadarChartSpec = {
    type: 'radar',
    data: [
      {
        id: 'radarData',
        values: radarData.map(item => [
          { key: 'Top1准确率(%)', value: parseFloat(item.top1_accuracy), api: item.api_name },
          { key: 'Top3准确率(%)', value: parseFloat(item.top3_accuracy), api: item.api_name },
          { key: '响应速度', value: parseFloat(item.response_speed), api: item.api_name }
        ]).flat()
      }
    ],
    categoryField: 'key',
    valueField: 'value',
    seriesField: 'api',
    point: {
      visible: true,
      style: {
        size: 4
      }
    },
    area: {
      visible: true,
      style: {
        fillOpacity: 0.2
      }
    },
    line: {
      style: {
        lineWidth: 2
      }
    },
    axes: [
      {
        orient: 'radius',
        grid: {
          smooth: true,
          style: {
            lineDash: [0]
          }
        }
      },
      {
        orient: 'angle',
        tick: {
          visible: false
        },
        domainLine: {
          visible: true
        },
        grid: {
          style: {
            lineDash: [0]
          }
        }
      }
    ],
    legends: {
      visible: true,
      orient: 'bottom'
    },
    title: {
      visible: true,
      text: '综合性能雷达图'
    },
    color: ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16']
  }

  // 准备命中数对比柱状图数据
  const hitCountBarData = data.flatMap(item => [
    {
      api_name: item.api_name,
      metric: 'Top1命中数',
      value: item.top1_hit_count
    },
    {
      api_name: item.api_name,
      metric: 'Top3命中数',
      value: item.top3_hit_count
    }
  ])

  // 命中数对比柱状图配置
  const hitCountBarSpec: IBarChartSpec = {
    type: 'bar',
    data: [
      {
        id: 'hitCountData',
        values: hitCountBarData
      }
    ],
    xField: 'api_name',
    yField: 'value',
    seriesField: 'metric',
    bar: {
      style: {
        cornerRadius: [4, 4, 0, 0]
      }
    },
    label: {
      visible: true,
      position: 'top',
      style: {
        fontSize: 12,
        fill: '#333'
      }
    },
    axes: [
      {
        orient: 'left',
        title: {
          visible: true,
          text: '命中数'
        }
      },
      {
        orient: 'bottom',
        label: {
          style: {
            fontSize: 11
          }
        },
        title: {
          visible: true,
          text: '接口名称'
        }
      }
    ],
    legends: {
      visible: true,
      orient: 'top',
      position: 'middle'
    },
    color: ['#6395FA', '#62DAAB'],
    title: {
      visible: true,
      text: '命中数对比'
    },
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: any) => datum.metric,
            value: (datum: any) => datum.value
          }
        ]
      }
    }
  }

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

      {/* 准确率对比柱状图 */}
      <Card
        title={
          <span>
            <TrophyOutlined style={{ marginRight: 8 }} />
            准确率对比
          </span>
        }
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Space>
            <Text strong>最佳接口：</Text>
            <Tag color="gold" icon={<TrophyOutlined />}>{bestByTop1.api_name}</Tag>
            <Text type="secondary">
              Top1准确率：{(bestByTop1.top1_accuracy * 100).toFixed(2)}%
            </Text>
          </Space>
        </div>
        <VChart spec={accuracyBarSpec} style={{ height: 400 }} />
      </Card>

      {/* 命中数对比柱状图 */}
      <Card title="命中数对比">
        <VChart spec={hitCountBarSpec} style={{ height: 400 }} />
      </Card>

      {/* 响应时间折线图 */}
      <Card
        title={
          <span>
            <RocketOutlined style={{ marginRight: 8 }} />
            响应时间对比
          </span>
        }
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Space>
            <Text strong>最快接口：</Text>
            <Tag color="green" icon={<RocketOutlined />}>{fastestApi.api_name}</Tag>
            <Text type="secondary">
              平均响应时间：{fastestApi.avg_response_time_ms.toFixed(2)}ms
            </Text>
          </Space>
        </div>
        <VChart spec={responseTimeLineSpec} style={{ height: 400 }} />
      </Card>

      {/* 综合性能雷达图 */}
      <Card title="综合性能对比">
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            雷达图展示了各接口在Top1准确率、Top3准确率和响应速度三个维度的综合表现
          </Text>
        </div>
        <VChart spec={radarSpec} style={{ height: 500 }} />
      </Card>

      {/* 接口性能表现卡片 */}
      <Card title="接口详细表现">
        <Row gutter={[16, 16]}>
          {data.map((item) => (
            <Col span={12} key={item.api_name}>
              <Card
                size="small"
                title={
                  <Space>
                    <Text strong>{item.api_name}</Text>
                    {item.api_name === bestByTop1.api_name && (
                      <Tag color="gold" icon={<TrophyOutlined />}>准确率最高</Tag>
                    )}
                    {item.api_name === fastestApi.api_name && (
                      <Tag color="green" icon={<RocketOutlined />}>响应最快</Tag>
                    )}
                  </Space>
                }
              >
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic
                      title="Top1 准确率"
                      value={item.top1_accuracy * 100}
                      precision={2}
                      suffix="%"
                      valueStyle={{ fontSize: 16, color: '#5B8FF9' }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="Top3 准确率"
                      value={item.top3_accuracy * 100}
                      precision={2}
                      suffix="%"
                      valueStyle={{ fontSize: 16, color: '#5AD8A6' }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="Top1 命中数"
                      value={item.top1_hit_count}
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="Top3 命中数"
                      value={item.top3_hit_count}
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="平均响应时间"
                      value={item.avg_response_time_ms}
                      precision={2}
                      suffix="ms"
                      valueStyle={{ fontSize: 16, color: '#FF6B6B' }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="总耗时"
                      value={item.total_time_ms}
                      precision={2}
                      suffix="ms"
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Col>
                </Row>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  )
}
