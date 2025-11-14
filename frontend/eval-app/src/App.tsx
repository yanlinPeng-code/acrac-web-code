import { useMemo, useRef, useState } from "react"
import { Upload, Radio, Button, Card, Table, Typography, message, Input, Switch, InputNumber } from "antd"
import type { UploadFile } from "antd"

type Detail = {
  clinical_scenario: string
  standard_answer: string
  recommendations: any
  hit: boolean
  processing_time_ms: number
}

type EvalResponse = {
  RequestId: string
  Data: {
    overall_accuracy: number
    combination_a: {
      accuracy: number
      total_samples: number
      hit_samples: number
      details: Detail[]
    }
    combination_b: {
      accuracy: number
      total_samples: number
      hit_samples: number
      details: Detail[]
    }
    average_processing_time_ms: number
    total_samples: number
  }
}

export default function App() {
  // 基本设置
  const [selectedEndpoint, setSelectedEndpoint] = useState<"recommend" | "recommend-simple">("recommend")
  const [uploadedFiles, setUploadedFiles] = useState<UploadFile[]>([])
  const [backendUrl, setBackendUrl] = useState<string>("http://localhost:8000")

  // 策略参数
  const [enableReranking, setEnableReranking] = useState<boolean>(true)
  const [needLLMRecommendations, setNeedLLMRecommendations] = useState<boolean>(true)
  const [applyRuleFilter, setApplyRuleFilter] = useState<boolean>(true)
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.6)
  const [minAppropriatenessRating, setMinAppropriatenessRating] = useState<number>(5)
  const [variantTopScenarios, setVariantTopScenarios] = useState<number | undefined>(undefined)
  const [variantTopRecommendations, setVariantTopRecommendations] = useState<number | undefined>(undefined)

  // 运行状态
  const [loading, setLoading] = useState(false)
  const [evaluationResult, setEvaluationResult] = useState<EvalResponse["Data"] | null>(null)
  const startTs = useRef<number>(0)
  const [clientLatencyMillis, setClientLatencyMillis] = useState<number | null>(null)

  // 明细表列定义
  const DETAIL_COLUMNS = useMemo(
    () => [
      { title: "临床场景", dataIndex: "clinical_scenario" },
      { title: "标准答案", dataIndex: "standard_answer" },
      {
        title: "推荐",
        dataIndex: "recommendations",
        render: (v: any) => {
          if (Array.isArray(v)) {
            return Array.isArray(v[0]) ? v.map((g: any, i: number) => (<div key={i}>{g.join("，")}</div>)) : v.join("，")
          }
          return String(v)
        },
      },
      { title: "逐场景命中", dataIndex: "per_scenario_hits", render: (v: number[]) => (Array.isArray(v) ? v.join(" / ") : "-") },
      { title: "命中", dataIndex: "hit", render: (v: boolean) => (v ? "是" : "否") },
      { title: "服务端耗时(ms)", dataIndex: "processing_time_ms" },
    ],
    []
  )

  // 组合对比表列定义
  const VARIANT_COLUMNS = useMemo(
    () => [
      { title: "组合", dataIndex: "label" },
      { title: "命中率", dataIndex: "accuracy", render: (v: number) => `${(v*100).toFixed(2)}%` },
      { title: "样本数", dataIndex: "total_samples" },
      { title: "命中样本", dataIndex: "hit_samples" },
    ],
    []
  )

  // 执行评测：组装表单，提交到后端评测路由，并记录端到端耗时
  async function runEvaluate() {
    if (!selectedEndpoint) return
    setLoading(true)
    setEvaluationResult(null)
    setClientLatencyMillis(null)
    startTs.current = Date.now()
    try {
      const form = new FormData()
      form.append("server_url", backendUrl)
      form.append("endpoint", selectedEndpoint)
      form.append("enable_reranking", String(enableReranking))
      form.append("need_llm_recommendations", String(needLLMRecommendations))
      form.append("apply_rule_filter", String(applyRuleFilter))
      form.append("similarity_threshold", String(similarityThreshold))
      form.append("min_appropriateness_rating", String(minAppropriatenessRating))
      if (typeof variantTopScenarios === "number") form.append("top_scenarios", String(variantTopScenarios))
      if (typeof variantTopRecommendations === "number") form.append("top_recommendations_per_scenario", String(variantTopRecommendations))
      if (uploadedFiles[0]) {
        const f = uploadedFiles[0]
        if (f.originFileObj) form.append("file", f.originFileObj as File)
      }
      const resp = await fetch("/api/v1/evaluate-recommend", { method: "POST", body: form })
      const json = await resp.json()
      setClientLatencyMillis(Date.now() - startTs.current)
      if (!json?.Data) throw new Error("无Data")
      setEvaluationResult(json.Data)
      message.success("评测完成")
    } catch (e: any) {
      setClientLatencyMillis(Date.now() - startTs.current)
      message.error(e?.message || "评测失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <Typography.Title level={3}>推荐系统评测</Typography.Title>

        <Card>
          <div className="flex flex-col md:flex-row gap-4 items-center">
            <Input style={{ maxWidth: 320 }} value={backendUrl} onChange={(e) => setBackendUrl(e.target.value)} placeholder="服务端URL，如 http://localhost:8000" />
            <Upload
              fileList={uploadedFiles}
              beforeUpload={() => false}
              onChange={(info) => setUploadedFiles(info.fileList.slice(0, 1))}
            >
              <Button>上传Excel</Button>
            </Upload>
            <Radio.Group
              value={selectedEndpoint}
              onChange={(e) => setSelectedEndpoint(e.target.value)}
              options={[{ label: "recommend", value: "recommend" }, { label: "recommend-simple", value: "recommend-simple" }]}
              optionType="button"
            />
            <Button type="primary" loading={loading} onClick={runEvaluate}>
              开始评测
            </Button>
          </div>
        </Card>

        <Card title="评测参数（可选）">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex items-center gap-2"><span>启用LLM重排序场景</span><Switch checked={enableReranking} onChange={setEnableReranking} /></div>
            <div className="flex items-center gap-2"><span>启动LLM推荐</span><Switch checked={needLLMRecommendations} onChange={setNeedLLMRecommendations} /></div>
            <div className="flex items-center gap-2"><span>启用规则过滤</span><Switch checked={applyRuleFilter} onChange={setApplyRuleFilter} /></div>
            <div className="flex items-center gap-2"><span>相似度阈值</span><InputNumber min={0.1} max={0.9} step={0.05} value={similarityThreshold} onChange={(v) => setSimilarityThreshold(Number(v))} /></div>
            <div className="flex items-center gap-2"><span>最低适宜性评分</span><InputNumber min={1} max={9} step={1} value={minAppropriatenessRating} onChange={(v) => setMinAppropriatenessRating(Number(v))} /></div>
            <div className="flex items-center gap-2"><span>场景数 top_s</span><InputNumber min={1} max={50} step={1} value={variantTopScenarios} onChange={(v) => setVariantTopScenarios(typeof v === "number" ? v : undefined)} /></div>
            <div className="flex items-center gap-2"><span>每场景推荐数 top_r</span><InputNumber min={1} max={20} step={1} value={variantTopRecommendations} onChange={(v) => setVariantTopRecommendations(typeof v === "number" ? v : undefined)} /></div>
          </div>
        </Card>

        {evaluationResult && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="总体">
              <div>端到端耗时：{clientLatencyMillis ?? 0} ms</div>
              <div>服务端平均耗时：{evaluationResult.average_processing_time_ms} ms</div>
              <div>总体命中率：{(evaluationResult.overall_accuracy * 100).toFixed(2)}%</div>
              <div>样本数：{evaluationResult.total_samples}</div>
            </Card>
            <Card title="组合A(1场景/1推荐)">
              <div>命中率：{(evaluationResult.combination_a.accuracy * 100).toFixed(2)}%</div>
              <div>样本数：{evaluationResult.combination_a.total_samples}</div>
              <div>命中样本：{evaluationResult.combination_a.hit_samples}</div>
            </Card>
            <Card title="组合B(3场景/3推荐)">
              <div>命中率：{(evaluationResult.combination_b.accuracy * 100).toFixed(2)}%</div>
              <div>样本数：{evaluationResult.combination_b.total_samples}</div>
              <div>命中样本：{evaluationResult.combination_b.hit_samples}</div>
            </Card>
          </div>
        )}

        {evaluationResult && (
          <Card title="组合A明细">
            <Table rowKey={(r) => r.clinical_scenario + "A"} columns={DETAIL_COLUMNS} dataSource={evaluationResult.combination_a.details} pagination={false} />
          </Card>
        )}

        {evaluationResult && (
          <Card title="组合B明细">
            <Table rowKey={(r) => r.clinical_scenario + "B"} columns={DETAIL_COLUMNS} dataSource={evaluationResult.combination_b.details} pagination={false} />
          </Card>
        )}

        {evaluationResult && evaluationResult["variants"] && (
          <Card title="更多组合(top@k)">
            <Table
              rowKey={(r: any) => r.label}
              columns={VARIANT_COLUMNS}
              dataSource={evaluationResult["variants"]}
              pagination={false}
            />
          </Card>
        )}
      </div>
    </div>
  )
}