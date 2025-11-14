"""
Celery应用配置
用于异步任务处理（如医学词典更新、批量数据处理等）
"""
from celery import Celery
from app.config.config import settings
from app.utils.logger.simple_logger import get_logger

logger = get_logger(__name__)

# 创建Celery实例
celery_app = Celery(
    "acrac_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.celery.tasks.dict_update_tasks',  # 词典更新任务
        # 在这里添加其他任务模块
    ]
)

# Celery配置
celery_app.conf.update(
    # 任务序列化格式
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # 时区设置
    timezone='Asia/Shanghai',
    enable_utc=True,
    
    # 任务结果过期时间（秒）
    result_expires=3600,
    
    # 任务超时设置
    task_soft_time_limit=300,  # 5分钟软限制（发送信号）
    task_time_limit=600,       # 10分钟硬限制（强制终止）
    
    # 任务重试配置
    task_acks_late=True,       # 任务执行完成后才确认
    task_reject_on_worker_lost=True,  # worker丢失时拒绝任务
    
    # 并发设置
    worker_prefetch_multiplier=4,  # 每个worker预取的任务数
    worker_max_tasks_per_child=1000,  # worker执行多少任务后重启
    
    # 任务路由（可选）
    task_routes={
        'app.celery.tasks.dict_update_tasks.*': {'queue': 'dict_update'},
    },
    
    # 结果后端设置
    result_backend_transport_options={
        'master_name': 'mymaster',
    },
    
    # Broker连接重试配置
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# 自动发现任务
celery_app.autodiscover_tasks(['app.celery.tasks'])


@celery_app.task(bind=True)
def debug_task(self):
    """调试任务，用于测试Celery是否正常工作"""
    logger.info(f'Request: {self.request!r}')
    return f'Celery is working! Task ID: {self.request.id}'


if __name__ == '__main__':
    celery_app.start()
