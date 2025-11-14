## 改造目标
- 将评估后端改为通过 httpx 异步客户端直连被评估的服务端 URL（由前端传入），不再直接调用内部 RagService。
- 在文件模式与非文件模式下均支持策略参数；文件模式中若未提供则使用默认组合集运行评测。
- 扩展多组合（top@k）评测，横向对比不同 `top_scenarios` 与 `top_recommendations_per_scenario` 的命中率。
- 前端新增服务端 URL 输入框，提交到评估接口；继续保持参数隐藏/互斥规则与端到端耗时统计。

## 后端改造
- 新增/改造服务层：`EvaluationService`
  - 使用 `httpx.AsyncClient` 调用 `${server_url}/api/v1/recommend` 或 `${server_url}/api/v1/recommend-simple`。
  - 构造 JSON 负载：包含 `patient_info`（最小占位）、`clinical_context`（含 `department` 与 `chief_complaint`）、`need_optimize_query`、`retrieval_strategy`、`standard_query`（按互斥与模式传入）。
  - 解析 `BaseResponse.Data.best_recommendations[*].final_choices` 与 `processing_time_ms`。
  - 实现：
    - `evaluate_excel(server_url, endpoint, file_bytes, strategy_variants?)`：
      - 读取 Excel 行（临床场景 + 标准答案）
      - 对每个样本按组合集依次调用接口、计算命中（top@1 等于、top@k 包含）
      - 返回总体统计与各组合明细（保留 `combination_a`=1/1 与 `combination_b`=3/3，同时新增 `variants` 列表）
    - `evaluate_params(server_url, endpoint, standard_query, patient_info, clinical_context, strategy)`：
      - 非文件模式按必填策略执行一次评测并返回结果
- 控制器：`/api/v1/evaluate-recommend`
  - 新增 `server_url`（必填）
  - 文件模式：
    - 若未给策略参数则使用默认组合集：[(1,1),(1,3),(3,1),(3,3)]；
    - 若提供策略参数，则将该组合加入 variants 一并评测。
  - 非文件模式：按互斥与必填规则执行一次评测（也可支持多组合，若传入 variants 列表则循环执行）。
  - 返回统一统计：总体命中率、A/B 与 `variants`、平均 `processing_time_ms`。
- 依赖注入：`EvaluationService` 不依赖 `RagService`，通过 `get_evaluation_service()` 直接实例化。

## 前端改造
- 在评测页新增服务端 URL 输入框（默认 `http://localhost:8000`），提交到评估接口。
- 文件模式：上传后隐藏参数输入区（仍由后端使用默认组合集评测）；也可在后续版本支持自定义组合列表。
- 非文件模式：继续遵守 `standard_query` 与 `patient_info/clinical_context` 互斥、策略参数必填；提交给评估接口。
- 展示：保留总体统计与 A/B；新增 `variants` 区块，表格列示各组合命中率与明细。

## 组合集与约束
- 默认组合集：[(1,1),(1,3),(3,1),(3,3)]。
- 当 `endpoint=recommend-simple` 时遵守其场景数量约束（避免 >=5）；可按端点动态过滤组合。
- 后续可扩展更多 k（如 5），仅对 `recommend` 端点启用。

## 验证
- 用仓库内样例 Excel 运行文件模式评测，核对 `final_choices` 命中与耗时。
- 非文件模式分别以 `standard_query` 与 `patient/clinical` 测试，验证互斥与必填策略生效。

确认后我将：
1) 改造 `EvaluationService` 为 httpx 异步直连实现并加入多组合评测；
2) 更新控制器以接收 `server_url` 并驱动服务；
3) 更新依赖注入与前端页面，添加服务端 URL 输入与 `variants` 展示。