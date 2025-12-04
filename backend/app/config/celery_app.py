"""
Celery应用配置
用于异步任务处理（如医学词典更新、批量数据处理等）
"""
import sys
import asyncio
from celery import Celery
from celery.signals import worker_process_init
from app.config.config import settings
from app.utils.logger.simple_logger import get_logger

logger = get_logger(__name__)

# 检测操作系统
IS_WINDOWS = sys.platform == 'win32'

# 创建Celery实例
celery_app = Celery(
    "acrac_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # 'app.celery.tasks.dict_update_tasks',  # 词典更新任务 (已禁用)
        'app.celery.tasks.evaluation_tasks',  # 评测任务
    ]
)

# Celery配置
celery_config = {
    # 任务序列化格式
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',

    # 时区设置
    'timezone': 'Asia/Shanghai',
    'enable_utc': True,

    # 任务结果过期时间（秒）
    'result_expires': 3600,

    # 任务超时设置
    'task_time_limit': 600,  # 10分钟硬限制（强制终止）

    # 任务重试配置
    'task_acks_late': True,  # 任务执行完成后才确认
    'task_reject_on_worker_lost': True,  # worker丢失时拒绝任务

    # 并发设置
    'worker_prefetch_multiplier': 4,  # 每个worker预取的任务数
    'worker_max_tasks_per_child': 1000,  # worker执行多少任务后重启

    # Broker连接重试配置
    'broker_connection_retry_on_startup': True,
    'broker_connection_retry': True,
    'broker_connection_max_retries': 10,
}

# Windows 不支持软超时（需要 SIGUSR1 信号）
if not IS_WINDOWS:
    celery_config['task_soft_time_limit'] = 300  # 5分钟软限制（仅Linux/Unix）

celery_app.conf.update(**celery_config)

# 自动发现任务
celery_app.autodiscover_tasks(['app.celery.tasks'])


@worker_process_init.connect
def init_worker(**kwargs):
    """Celery worker 进程启动时初始化 Redis"""
    try:
        from app.config.redis_config import redis_manager
        # 在新的事件循环中初始化 Redis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(redis_manager.init())
        # 保持事件循环开启，供后续任务使用
        logger.info("✅ Celery worker Redis 初始化成功")
    except Exception as e:
        logger.warning(f"⚠️ Celery worker Redis 初始化失败: {e}")
        logger.warning("⚠️ 评测任务将在无缓存模式下运行")


@celery_app.task(bind=True)
def debug_task(self):
    """调试任务，用于测试Celery是否正常工作"""
    logger.info(f'Request: {self.request!r}')
    return f'Celery is working! Task ID: {self.request.id}'


if __name__ == '__main__':
    celery_app.start()
