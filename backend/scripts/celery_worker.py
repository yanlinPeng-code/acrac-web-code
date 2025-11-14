"""
Celery Worker启动脚本
用于启动Celery worker进程处理异步任务
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.config.celery_app import celery_app

if __name__ == '__main__':
    # 启动Celery worker
    # 参数说明：
    # -A: 指定Celery应用
    # -l: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    # -c: 并发worker数量
    # -Q: 指定队列（可选）
    celery_app.worker_main([
        'worker',
        '--loglevel=INFO',
        '--concurrency=4',  # 4个并发worker
        '--max-tasks-per-child=1000',  # 每个worker处理1000个任务后重启
        '--time-limit=600',  # 任务硬超时10分钟
        '--soft-time-limit=300',  # 任务软超时5分钟
    ])
