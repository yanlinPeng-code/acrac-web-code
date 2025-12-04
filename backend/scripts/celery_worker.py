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
    # 检测操作系统
    is_windows = sys.platform == 'win32'

    # 启动Celery worker
    # 参数说明：
    # -A: 指定Celery应用
    # -l: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    # -P: 并发池类型 (prefork, solo, gevent, eventlet)
    # -c: 并发worker数量（solo模式下无效）
    # -Q: 指定队列（可选）

    worker_args = [
        'worker',
        '--loglevel=INFO',
        '--max-tasks-per-child=1000',  # 每个worker处理1000个任务后重启
        '--time-limit=600',  # 任务硬超时10分钟
    ]

    if is_windows:
        # Windows 使用 solo 池（单进程，更稳定）
        # 注意：solo 模式下 concurrency 参数无效
        worker_args.extend([
            '--pool=solo',
            # 不添加 --soft-time-limit，因为 Windows 不支持
        ])
        print("⚠️  Windows 环境：使用 solo 池（单进程模式）")
    else:
        # Linux/Unix 使用 prefork 池（多进程）
        worker_args.extend([
            '--pool=prefork',
            '--concurrency=4',  # 4个并发worker
            '--soft-time-limit=300',  # 任务软超时5分钟
        ])
        print("✅ Linux/Unix 环境：使用 prefork 池（多进程模式）")

    celery_app.worker_main(worker_args)
