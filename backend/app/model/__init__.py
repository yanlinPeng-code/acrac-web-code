"""
模型包 - 使用 SQLModel 实现的数据库模型
"""

# ACRAC 核心模型
from .acrac_models import (
    Panel,
    Topic,
    ClinicalScenario,
    ProcedureDictionary,
    ClinicalRecommendation,
    VectorSearchLog,
    DataUpdateHistory,
)

# 临床场景数据模型
from .clinical_data_models import (
    ClinicalScenarioData,
    DataUploadBatch,
)

# 系统模型
from .system_models import (
    User,
    InferenceLog,
    Rule,
    DataImportTask,
    EvaluationProject,
    ExcelEvaluationData,
)

# 评估模型
from .evaluation import (
    EvaluationResult,
    TestData,
)

# RAGAS 评测模型
from .ragas_models import (
    TaskStatus,
    EvaluationTask,
    ScenarioResult,
    EvaluationMetrics,
    DataAdapterLog,
)

__all__ = [
    # ACRAC 核心模型
    "Panel",
    "Topic",
    "ClinicalScenario",
    "ProcedureDictionary",
    "ClinicalRecommendation",
    "VectorSearchLog",
    "DataUpdateHistory",
    # 临床场景数据模型
    "ClinicalScenarioData",
    "DataUploadBatch",
    # 系统模型
    "User",
    "InferenceLog",
    "Rule",
    "DataImportTask",
    "EvaluationProject",
    "ExcelEvaluationData",
    # 评估模型
    "EvaluationResult",
    "TestData",
    # RAGAS 评测模型
    "TaskStatus",
    "EvaluationTask",
    "ScenarioResult",
    "EvaluationMetrics",
    "DataAdapterLog",
]
