"""
评测任务模块
用于异步执行评测任务
"""
import os
from pathlib import Path
from datetime import datetime
from app.config.celery_app import celery_app
from app.service.eval_v1.evaluation_service import EvaluationService
from app.utils.logger.simple_logger import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, name='app.celery.tasks.evaluation_tasks.evaluate_all_endpoints')
def evaluate_all_endpoints_task(
    self,
    file_bytes: bytes,
    limit: int = None,
    top_scenarios: int = 3,
    top_recommendations_per_scenario: int = 3,
    similarity_threshold: float = 0.4,
    min_appropriateness_rating: int = 4,
):
    """异步评估所有接口的Celery任务"""
    import asyncio

    logger.info(f"开始评测任务 {self.request.id}, 限制条数: {limit if limit else '全部'}")

    try:
        # 创建评测服务实例
        evaluation_service = EvaluationService()

        # 定义进度回调函数
        def progress_callback(completed: int, total: int, message: str):
            """更新任务进度"""
            self.update_state(
                state='PROGRESS',
                meta={
                    'completed': completed,
                    'total': total,
                    'percentage': int((completed / total) * 100) if total > 0 else 0,
                    'message': message
                }
            )
            logger.info(f"进度: {completed}/{total} - {message}")

        # 运行异步评测（纯异步架构，单event loop）
        result = asyncio.run(
            evaluation_service.evaluate_all_endpoints_concurrent(
                file_bytes=file_bytes,
                limit=limit,
                top_scenarios=top_scenarios,
                top_recommendations_per_scenario=top_recommendations_per_scenario,
                similarity_threshold=similarity_threshold,
                min_appropriateness_rating=min_appropriateness_rating,
                progress_callback=progress_callback,
            )
        )

        # 保存Excel到backend/output_eval目录（使用绝对路径）
        # 获取backend目录的绝对路径
        backend_dir = Path(__file__).resolve().parents[3]  # 从 tasks/evaluation_tasks.py 往上3层到 backend
        output_dir = backend_dir / "output_eval"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_filename = f"evaluation_all_{timestamp}.xlsx"
        excel_path = output_dir / excel_filename

        # 保存Excel文件
        with open(excel_path, 'wb') as f:
            f.write(result['result_excel'])

        logger.info(f"评测完成，结果已保存到: {excel_path}")

        # 返回结果（只返回接口汇总数据）
        return {
            "endpoint_summary": result.get("endpoint_summary", []),
            "excel_path": str(excel_path),  # 转换为字符串
            "task_id": self.request.id
        }

    except Exception as e:
        logger.error(f"评测任务失败: {e}", exc_info=True)
        raise
