/**
 * 推荐系统评测平台 - 主应用组件
 */

import { useState, useRef } from "react"
import { Layout, Menu, Upload, Radio, Button, Card, Typography, message, Spin, Divider, Badge, InputNumber, Table, Progress } from "antd"
import type { UploadFile } from "antd"
import {
  FileTextOutlined,
  RocketOutlined,
  SettingOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons"

// 类型定义
import type { EvalMode, EndpointType, SingleEvaluationData, AllEvaluationData } from "./types/evaluation"

// API请求
import { evaluateSingleEndpoint, evaluateAllEndpoints, getTaskStatus, previewExcelData } from "./api/evaluation"
import { ENDPOINTS } from "./api/config"

// 工具函数
import { generateRandomId } from "./utils/format"

// UI组件
import EvaluationParams from "./components/EvaluationParams"
import SingleEvalResult from "./components/SingleEvalResult"
import AllEvalResult from "./components/AllEvalResult"

const { Header, Sider, Content } = Layout
const { Title, Text } = Typography

export default function App() {
  // 基本设置
  const [evalMode, setEvalMode] = useState<EvalMode>("single")
  const [selectedEndpoint, setSelectedEndpoint] = useState<EndpointType>("recommend-simple")

  // 分别管理两种模式的文件
  const [singleModeFiles, setSingleModeFiles] = useState<UploadFile[]>([])
  const [allModeFiles, setAllModeFiles] = useState<UploadFile[]>([])

  // 非文件模式参数
  const [standardQuery, setStandardQuery] = useState<string>("")
  const [patientInfo, setPatientInfo] = useState<string>("")
  const [clinicalContext, setClinicalContext] = useState<string>("")
  const [goldAnswer, setGoldAnswer] = useState<string>("")

  // 核心参数
  const [topScenarios, setTopScenarios] = useState<number>(3)
  const [topRecommendationsPerScenario, setTopRecommendationsPerScenario] = useState<number>(3)
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.7)
  const [minAppropriatenessRating, setMinAppropriatenessRating] = useState<number>(5)

  // recommend/recommend-simple 特有参数
  const [enableReranking, setEnableReranking] = useState<boolean>(false)
  const [needLLMRecommendations, setNeedLLMRecommendations] = useState<boolean>(false)
  const [applyRuleFilter, setApplyRuleFilter] = useState<boolean>(false)

  // intelligent-recommendation 特有参数
  const [showReasoning, setShowReasoning] = useState<boolean>(false)
  const [includeRawData, setIncludeRawData] = useState<boolean>(false)
  const [debugMode, setDebugMode] = useState<boolean>(false)
  const [computeRagas, setComputeRagas] = useState<boolean>(false)
  const [groundTruth, setGroundTruth] = useState<string>("")

  // recommend_item_with_reason 特有参数
  const [sessionId] = useState<string>(generateRandomId())
  const [patientId] = useState<string>(generateRandomId())
  const [doctorId] = useState<string>(generateRandomId())

  // 评测限制条数
  const [evaluationLimit, setEvaluationLimit] = useState<number | null>(null)

  // Excel预览数据
  const [excelPreview, setExcelPreview] = useState<any[]>([])
  const [loadingPreview, setLoadingPreview] = useState(false)

  // 运行状态
  const [loading, setLoading] = useState(false)
  const [evaluationResult, setEvaluationResult] = useState<SingleEvaluationData | null>(null)
  const [allEvaluationResult, setAllEvaluationResult] = useState<AllEvaluationData | null>(null)
  const startTs = useRef<number>(0)
  const [clientLatencyMillis, setClientLatencyMillis] = useState<number | null>(null)

  // 进度信息
  const [progressPercentage, setProgressPercentage] = useState<number>(0)
  const [progressMessage, setProgressMessage] = useState<string>("")
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false)

  // 侧边栏选中项
  const [selectedMenu, setSelectedMenu] = useState<string>("config")

  // 获取当前模式的文件
  const currentFiles = evalMode === "single" ? singleModeFiles : allModeFiles
  const setCurrentFiles = evalMode === "single" ? setSingleModeFiles : setAllModeFiles

  /**
   * 处理文件上传（all模式下自动预览）
   */
  const handleFileChange = async (info: any) => {
    const newFiles = info.fileList.slice(0, 1)
    setCurrentFiles(newFiles)

    // 仅在all模式下自动预览
    if (evalMode === "all" && newFiles.length > 0) {
      const file = newFiles[0].originFileObj as File
      if (file) {
        setLoadingPreview(true)
        setExcelPreview([])
        try {
          const response = await previewExcelData(file)
          setExcelPreview(response.Data.preview)
          message.success(`成功加载 ${response.Data.preview_limit} 行预览数据`)
        } catch (e: any) {
          message.error(e?.message || "预览加载失败")
          setExcelPreview([])
        } finally {
          setLoadingPreview(false)
        }
      }
    } else if (evalMode === "single" || newFiles.length === 0) {
      // single模式或清空文件时，清空预览
      setExcelPreview([])
    }
  }

  /**
   * 执行单个接口评测
   */
  const runSingleEvaluate = async () => {
    if (singleModeFiles.length === 0) {
      message.error("请上传Excel文件")
      return
    }

    const file = singleModeFiles[0].originFileObj as File
    if (!file) {
      message.error("文件无效")
      return
    }

    setLoading(true)
    setEvaluationResult(null)
    setAllEvaluationResult(null)
    setClientLatencyMillis(null)
    startTs.current = Date.now()

    try {
      const params: any = {
        file,
        endpoint: selectedEndpoint,
        top_scenarios: topScenarios,
        top_recommendations_per_scenario: topRecommendationsPerScenario,
        similarity_threshold: similarityThreshold,
        min_appropriateness_rating: minAppropriatenessRating,
      }

      // 根据endpoint添加特有参数
      if (selectedEndpoint === ENDPOINTS.RECOMMEND || selectedEndpoint === ENDPOINTS.RECOMMEND_SIMPLE) {
        params.enable_reranking = enableReranking
        params.need_llm_recommendations = needLLMRecommendations
        params.apply_rule_filter = applyRuleFilter
      }

      if (selectedEndpoint === ENDPOINTS.INTELLIGENT_RECOMMENDATION) {
        params.show_reasoning = showReasoning
        params.include_raw_data = includeRawData
        params.debug_mode = debugMode
        params.compute_ragas = computeRagas
        if (groundTruth) params.ground_truth = groundTruth
      }

      if (selectedEndpoint === ENDPOINTS.RECOMMEND_ITEM_WITH_REASON) {
        params.session_id = sessionId
        params.patient_id = patientId
        params.doctor_id = doctorId
      }

      const response = await evaluateSingleEndpoint(params)
      setClientLatencyMillis(Date.now() - startTs.current)
      setEvaluationResult(response.Data)
      message.success("评测完成！")
      // 自动跳转到结果页
      setSelectedMenu("result")
    } catch (e: any) {
      setClientLatencyMillis(Date.now() - startTs.current)
      message.error(e?.message || "评测失败")
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  /**
   * 执行所有接口并发评测（异步）
   */
  const runAllEvaluate = async () => {
    if (allModeFiles.length === 0) {
      message.error("请上传Excel文件")
      return
    }

    const file = allModeFiles[0].originFileObj as File
    if (!file) {
      message.error("文件无效")
      return
    }

    setLoading(true)
    setEvaluationResult(null)
    setAllEvaluationResult(null)
    setClientLatencyMillis(null)
    setProgressPercentage(0)
    setProgressMessage("正在提交任务...")
    setIsEvaluating(false)
    startTs.current = Date.now()

    try {
      const params: any = {
        file,
        top_scenarios: topScenarios,
        top_recommendations_per_scenario: topRecommendationsPerScenario,
        similarity_threshold: similarityThreshold,
        min_appropriateness_rating: minAppropriatenessRating,
      }

      // 添加limit参数
      if (evaluationLimit !== null && evaluationLimit > 0) {
        params.limit = evaluationLimit
      }

      // 提交任务
      const submitResponse = await evaluateAllEndpoints(params)
      const responseData = submitResponse.Data as { task_id: string; status: string }
      const taskId = responseData.task_id

      // 立即关闭loading并提示成功
      setLoading(false)
      setIsEvaluating(true)
      setProgressPercentage(0)
      setProgressMessage("任务已提交，评测进行中...")
      message.success("任务提交成功！评测正在后台进行...")

      // 轮询任务状态
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await getTaskStatus(taskId)
          const statusData = statusResponse.Data as any

          if (statusData.status === "success") {
            clearInterval(pollInterval)
            setProgressPercentage(100)
            setProgressMessage("评测完成")
            setClientLatencyMillis(Date.now() - startTs.current)
            setAllEvaluationResult(statusData.result)
            setIsEvaluating(false)
            message.success("所有接口评测完成！")
            setSelectedMenu("result")
          } else if (statusData.status === "failure") {
            clearInterval(pollInterval)
            setClientLatencyMillis(Date.now() - startTs.current)
            setProgressMessage("评测失败")
            setIsEvaluating(false)
            message.error(statusData.error || "评测失败")
          } else if (statusData.status === "progress") {
            // 更新进度
            const progress = statusData.progress || {}
            setProgressPercentage(progress.percentage || 0)
            setProgressMessage(statusData.message || "评测进行中...")
          } else if (statusData.status === "started" || statusData.status === "pending") {
            setProgressMessage(statusData.message || "任务启动中...")
          }
        } catch (e: any) {
          clearInterval(pollInterval)
          setClientLatencyMillis(Date.now() - startTs.current)
          setProgressMessage("查询状态失败")
          setIsEvaluating(false)
          message.error(e?.message || "查询任务状态失败")
        }
      }, 2000) // 每2秒轮询一次

    } catch (e: any) {
      setClientLatencyMillis(Date.now() - startTs.current)
      message.error(e?.message || "提交评测任务失败")
      setLoading(false)
      setIsEvaluating(false)
    }
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {/* 顶部导航栏 */}
      <Header style={{ background: "#001529", padding: "0 24px", display: "flex", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <RocketOutlined style={{ fontSize: 28, color: "#1890ff" }} />
          <Title level={3} style={{ margin: 0, color: "white" }}>
            推荐系统评测平台
          </Title>
        </div>
      </Header>

      <Layout>
        {/* 左侧边栏 */}
        <Sider width={240} style={{ background: "#fff" }}>
          <div style={{ padding: "16px" }}>
            <Badge.Ribbon text={evalMode === "single" ? "单接口" : "并发"} color={evalMode === "single" ? "blue" : "green"}>
              <Card size="small">
                <Text strong>评测模式</Text>
                <Radio.Group
                  value={evalMode}
                  onChange={(e) => {
                    setEvalMode(e.target.value)
                    setEvaluationResult(null)
                    setAllEvaluationResult(null)
                    setSelectedMenu("config")
                  }}
                  style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}
                >
                  <Radio value="single">单个接口评测</Radio>
                  <Radio value="all">所有接口并发评测</Radio>
                </Radio.Group>
              </Card>
            </Badge.Ribbon>
          </div>

          <Divider style={{ margin: "8px 0" }} />

          <Menu
            mode="inline"
            selectedKeys={[selectedMenu]}
            onClick={(e) => setSelectedMenu(e.key)}
            items={[
              {
                key: "config",
                icon: <SettingOutlined />,
                label: "配置评测",
              },
              {
                key: "result",
                icon: <BarChartOutlined />,
                label: "评测结果",
                disabled: !evaluationResult && !allEvaluationResult,
              },
            ]}
          />
        </Sider>

        {/* 主内容区 */}
        <Content style={{ padding: "24px", background: "#f0f2f5", minHeight: "calc(100vh - 64px)" }}>
          {selectedMenu === "config" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              {/* 文件上传 */}
              <Card
                title={
                  <span>
                    <FileTextOutlined /> 上传评测数据
                  </span>
                }
                extra={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    支持 .xlsx 格式
                  </Text>
                }
              >
                <Upload
                  fileList={currentFiles}
                  beforeUpload={() => false}
                  onChange={handleFileChange}
                  maxCount={1}
                  accept=".xlsx,.xls"
                  disabled={loadingPreview}
                >
                  <Button icon={<FileTextOutlined />} size="large" loading={loadingPreview}>
                    {loadingPreview ? "加载预览中..." : "选择Excel文件"}
                  </Button>
                </Upload>
                {currentFiles.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <Text type="success">
                      ✓ 已选择文件: {currentFiles[0].name}
                    </Text>
                  </div>
                )}

                {/* 评测条数限制 - 仅在all模式显示 */}
                {evalMode === "all" && currentFiles.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>评测数据条数: </Text>
                    <InputNumber
                      min={1}
                      placeholder="默认全部"
                      value={evaluationLimit}
                      onChange={(value) => setEvaluationLimit(value)}
                      style={{ width: 200, marginLeft: 8 }}
                    />
                    <Text type="secondary" style={{ marginLeft: 8 }}>
                      （不填则评测全部数据）
                    </Text>
                  </div>
                )}

                {/* 评测进度条 - 在all模式且评测进行中时显示 */}
                {evalMode === "all" && isEvaluating && (
                  <div style={{ marginTop: 16 }}>
                    <Divider orientation="left">评测进度</Divider>
                    <div style={{ padding: "16px", background: "#f5f5f5", borderRadius: 8 }}>
                      <Progress
                        percent={progressPercentage}
                        status={progressPercentage === 100 ? "success" : "active"}
                        strokeColor={{
                          '0%': '#108ee9',
                          '100%': '#87d068',
                        }}
                      />
                      <div style={{ marginTop: 12, textAlign: "center" }}>
                        <Text type="secondary">{progressMessage}</Text>
                      </div>
                      {clientLatencyMillis && (
                        <div style={{ marginTop: 8, textAlign: "center" }}>
                          <Text type="secondary">已用时: {Math.floor(clientLatencyMillis / 1000)}秒</Text>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Excel预览 - 仅在all模式且有预览数据时显示 */}
                {evalMode === "all" && excelPreview.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Divider orientation="left">数据预览（前10条）</Divider>
                    <Table
                      dataSource={excelPreview.slice(0, 10)}
                      columns={Object.keys(excelPreview[0] || {}).map((key) => ({
                        title: key,
                        dataIndex: key,
                        key: key,
                        ellipsis: true,
                        width: 150,
                      }))}
                      pagination={false}
                      scroll={{ x: 'max-content' }}
                      size="small"
                    />
                  </div>
                )}
              </Card>

              {/* 接口选择 */}
              {evalMode === "single" && (
                <Card
                  title={
                    <span>
                      <ThunderboltOutlined /> 选择评测接口
                    </span>
                  }
                >
                  <Radio.Group
                    value={selectedEndpoint}
                    onChange={(e) => setSelectedEndpoint(e.target.value)}
                    style={{ width: "100%" }}
                  >
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
                      <Card
                        size="small"
                        hoverable
                        style={{
                          border: selectedEndpoint === ENDPOINTS.RECOMMEND ? "2px solid #1890ff" : "1px solid #d9d9d9",
                        }}
                        onClick={() => setSelectedEndpoint(ENDPOINTS.RECOMMEND)}
                      >
                        <Radio value={ENDPOINTS.RECOMMEND}>Recommend</Radio>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>标准推荐接口</div>
                      </Card>

                      <Card
                        size="small"
                        hoverable
                        style={{
                          border:
                            selectedEndpoint === ENDPOINTS.RECOMMEND_SIMPLE ? "2px solid #1890ff" : "1px solid #d9d9d9",
                        }}
                        onClick={() => setSelectedEndpoint(ENDPOINTS.RECOMMEND_SIMPLE)}
                      >
                        <Radio value={ENDPOINTS.RECOMMEND_SIMPLE}>Recommend Simple</Radio>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>简化推荐接口</div>
                      </Card>

                      <Card
                        size="small"
                        hoverable
                        style={{
                          border:
                            selectedEndpoint === ENDPOINTS.INTELLIGENT_RECOMMENDATION
                              ? "2px solid #1890ff"
                              : "1px solid #d9d9d9",
                        }}
                        onClick={() => setSelectedEndpoint(ENDPOINTS.INTELLIGENT_RECOMMENDATION)}
                      >
                        <Radio value={ENDPOINTS.INTELLIGENT_RECOMMENDATION}>Intelligent Recommendation</Radio>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>智能推荐接口</div>
                      </Card>

                      <Card
                        size="small"
                        hoverable
                        style={{
                          border:
                            selectedEndpoint === ENDPOINTS.RECOMMEND_ITEM_WITH_REASON
                              ? "2px solid #1890ff"
                              : "1px solid #d9d9d9",
                        }}
                        onClick={() => setSelectedEndpoint(ENDPOINTS.RECOMMEND_ITEM_WITH_REASON)}
                      >
                        <Radio value={ENDPOINTS.RECOMMEND_ITEM_WITH_REASON}>Recommend With Reason</Radio>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>带理由推荐</div>
                      </Card>
                    </div>
                  </Radio.Group>
                </Card>
              )}

              {/* 评测参数 */}
              <EvaluationParams
                endpoint={selectedEndpoint}
                hasFile={currentFiles.length > 0}
                standardQuery={standardQuery}
                setStandardQuery={setStandardQuery}
                patientInfo={patientInfo}
                setPatientInfo={setPatientInfo}
                clinicalContext={clinicalContext}
                setClinicalContext={setClinicalContext}
                goldAnswer={goldAnswer}
                setGoldAnswer={setGoldAnswer}
                topScenarios={topScenarios}
                setTopScenarios={setTopScenarios}
                topRecommendationsPerScenario={topRecommendationsPerScenario}
                setTopRecommendationsPerScenario={setTopRecommendationsPerScenario}
                similarityThreshold={similarityThreshold}
                setSimilarityThreshold={setSimilarityThreshold}
                minAppropriatenessRating={minAppropriatenessRating}
                setMinAppropriatenessRating={setMinAppropriatenessRating}
                enableReranking={enableReranking}
                setEnableReranking={setEnableReranking}
                needLLMRecommendations={needLLMRecommendations}
                setNeedLLMRecommendations={setNeedLLMRecommendations}
                applyRuleFilter={applyRuleFilter}
                setApplyRuleFilter={setApplyRuleFilter}
                showReasoning={showReasoning}
                setShowReasoning={setShowReasoning}
                includeRawData={includeRawData}
                setIncludeRawData={setIncludeRawData}
                debugMode={debugMode}
                setDebugMode={setDebugMode}
                computeRagas={computeRagas}
                setComputeRagas={setComputeRagas}
                groundTruth={groundTruth}
                setGroundTruth={setGroundTruth}
                sessionId={sessionId}
                patientId={patientId}
                doctorId={doctorId}
              />

              {/* 开始评测按钮 */}
              <Card>
                <div style={{ textAlign: "center" }}>
                  <Button
                    type="primary"
                    size="large"
                    loading={loading}
                    onClick={evalMode === "single" ? runSingleEvaluate : runAllEvaluate}
                    disabled={currentFiles.length === 0}
                    icon={<RocketOutlined />}
                    style={{ minWidth: 200, height: 48, fontSize: 16 }}
                  >
                    {loading ? "评测进行中..." : "开始评测"}
                  </Button>
                  {currentFiles.length === 0 && (
                    <div style={{ marginTop: 12 }}>
                      <Text type="secondary">请先上传Excel文件</Text>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          )}

          {selectedMenu === "result" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              {/* 单个接口评测结果 */}
              {evaluationResult && evalMode === "single" && (
                <SingleEvalResult result={evaluationResult} clientLatency={clientLatencyMillis} />
              )}

              {/* 所有接口并发评测结果 */}
              {allEvaluationResult && evalMode === "all" && (
                <AllEvalResult result={allEvaluationResult} clientLatency={clientLatencyMillis} />
              )}

              {!evaluationResult && !allEvaluationResult && (
                <Card>
                  <div style={{ textAlign: "center", padding: "60px 0" }}>
                    <Text type="secondary">暂无评测结果</Text>
                  </div>
                </Card>
              )}
            </div>
          )}
        </Content>
      </Layout>

      {/* Loading遮罩 */}
      {loading && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <Card style={{ textAlign: "center", minWidth: 400, padding: "20px" }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, fontSize: 16 }}>
              <Text strong>评测进行中，请稍候...</Text>
            </div>

            {/* 进度条 - 仅在all模式显示 */}
            {evalMode === "all" && (
              <div style={{ marginTop: 20 }}>
                <Progress
                  percent={progressPercentage}
                  status={progressPercentage === 100 ? "success" : "active"}
                  strokeColor={{
                    '0%': '#108ee9',
                    '100%': '#87d068',
                  }}
                />
                <div style={{ marginTop: 12 }}>
                  <Text type="secondary">{progressMessage}</Text>
                </div>
              </div>
            )}

            {clientLatencyMillis && (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary">已用时: {Math.floor(clientLatencyMillis / 1000)}秒</Text>
              </div>
            )}
          </Card>
        </div>
      )}
    </Layout>
  )
}
