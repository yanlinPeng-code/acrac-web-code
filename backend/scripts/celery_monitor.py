"""
Celery任务监控和管理脚本
用于查看任务状态、清理队列等
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.config.celery_app import celery_app
from app.utils.logger.simple_logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def inspect_workers():
    """检查活跃的workers"""
    print("\n" + "="*80)
    print("活跃的 Celery Workers")
    print("="*80)
    
    inspector = celery_app.control.inspect()
    
    # 获取活跃workers
    active = inspector.active()
    if active:
        for worker, tasks in active.items():
            print(f"\n🟢 Worker: {worker}")
            if tasks:
                for task in tasks:
                    print(f"  - 任务ID: {task['id']}")
                    print(f"    名称: {task['name']}")
                    print(f"    参数: {task['args']}")
            else:
                print("  (空闲)")
    else:
        print("\n❌ 没有活跃的workers")


def inspect_scheduled():
    """检查计划任务"""
    print("\n" + "="*80)
    print("计划中的任务")
    print("="*80)
    
    inspector = celery_app.control.inspect()
    scheduled = inspector.scheduled()
    
    if scheduled:
        for worker, tasks in scheduled.items():
            print(f"\n📅 Worker: {worker}")
            if tasks:
                for task in tasks:
                    print(f"  - 任务: {task['request']['name']}")
                    print(f"    ETA: {task['eta']}")
            else:
                print("  (无计划任务)")
    else:
        print("\n没有计划中的任务")


def inspect_stats():
    """查看workers统计信息"""
    print("\n" + "="*80)
    print("Workers 统计信息")
    print("="*80)
    
    inspector = celery_app.control.inspect()
    stats = inspector.stats()
    
    if stats:
        for worker, info in stats.items():
            print(f"\n📊 Worker: {worker}")
            print(f"  - 总任务数: {info.get('total', 0)}")
            print(f"  - 进程池大小: {info.get('pool', {}).get('max-concurrency', 'N/A')}")
            print(f"  - Broker: {info.get('broker', {}).get('hostname', 'N/A')}")
    else:
        print("\n❌ 无法获取统计信息")


def purge_queue(queue_name='celery'):
    """清空指定队列"""
    print(f"\n⚠️  正在清空队列: {queue_name}")
    count = celery_app.control.purge()
    print(f"✅ 已清除 {count} 个任务")


def get_task_result(task_id):
    """获取任务结果"""
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=celery_app)
    
    print(f"\n任务ID: {task_id}")
    print(f"状态: {result.state}")
    
    if result.ready():
        print(f"结果: {result.result}")
    else:
        print("任务还在进行中...")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Celery 任务监控和管理')
    parser.add_argument('command', choices=['workers', 'scheduled', 'stats', 'purge', 'result'],
                      help='执行的命令')
    parser.add_argument('--task-id', help='任务ID（用于result命令）')
    parser.add_argument('--queue', default='celery', help='队列名称（用于purge命令）')
    
    args = parser.parse_args()
    
    if args.command == 'workers':
        inspect_workers()
    elif args.command == 'scheduled':
        inspect_scheduled()
    elif args.command == 'stats':
        inspect_stats()
    elif args.command == 'purge':
        purge_queue(args.queue)
    elif args.command == 'result':
        if not args.task_id:
            print("❌ 请提供 --task-id 参数")
        else:
            get_task_result(args.task_id)
