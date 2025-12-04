"""
清理 Redis 中的 Celery 消息和任务数据
支持清理任务队列、结果、元数据等
"""
import sys
import redis
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.config.config import settings
from app.utils.logger.simple_logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


class CeleryRedisCleaner:
    """Celery Redis 清理器"""

    def __init__(self):
        """初始化 Redis 连接"""
        self.broker_url = settings.CELERY_BROKER_URL
        self.backend_url = settings.CELERY_RESULT_BACKEND

        # 解析 broker URL 连接到 Redis
        self.redis_client = self._create_redis_client(self.broker_url)

        logger.info(f"已连接到 Redis: {self._mask_url(self.broker_url)}")

    def _create_redis_client(self, url: str) -> redis.Redis:
        """从 URL 创建 Redis 客户端"""
        # 支持 redis:// 和 rediss:// 协议
        if url.startswith('redis://') or url.startswith('rediss://'):
            return redis.from_url(url, decode_responses=False)
        else:
            raise ValueError(f"不支持的 Redis URL 格式: {url}")

    def _mask_url(self, url: str) -> str:
        """隐藏 URL 中的密码信息"""
        if '@' in url:
            parts = url.split('@')
            return f"{parts[0].split(':')[0]}://***@{parts[1]}"
        return url

    def get_celery_keys(self, pattern: str = "*") -> list:
        """获取所有 Celery 相关的键"""
        keys = []
        cursor = 0

        while True:
            cursor, partial_keys = self.redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            keys.extend(partial_keys)

            if cursor == 0:
                break

        return keys

    def list_celery_data(self):
        """列出所有 Celery 相关数据"""
        print("\n" + "="*80)
        print("Redis 中的 Celery 数据")
        print("="*80)

        patterns = {
            "任务队列": "celery*",
            "任务结果": "celery-task-meta-*",
            "任务状态": "celery-task-state-*",
            "Worker 心跳": "*celery@*",
            "其他 Celery 键": "*celery*"
        }

        total_keys = 0
        for category, pattern in patterns.items():
            keys = self.get_celery_keys(pattern)
            if keys:
                print(f"\n📦 {category} ({len(keys)} 个键)")
                for key in keys[:10]:  # 只显示前10个
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    print(f"  - {key_str}")
                if len(keys) > 10:
                    print(f"  ... 还有 {len(keys) - 10} 个键")
                total_keys += len(keys)

        print(f"\n总计: {total_keys} 个 Celery 相关键")
        return total_keys

    def clear_task_queue(self, queue_name: str = "celery"):
        """清空指定的任务队列"""
        queue_key = queue_name

        # 检查队列长度
        queue_length = self.redis_client.llen(queue_key)

        if queue_length > 0:
            print(f"\n🗑️  清空队列: {queue_name} ({queue_length} 个任务)")
            self.redis_client.delete(queue_key)
            logger.info(f"✅ 已清空队列: {queue_name}")
        else:
            print(f"\n✓ 队列 {queue_name} 已经是空的")

    def clear_task_results(self):
        """清空所有任务结果"""
        result_keys = self.get_celery_keys("celery-task-meta-*")

        if result_keys:
            print(f"\n🗑️  清空任务结果 ({len(result_keys)} 个)")
            for key in result_keys:
                self.redis_client.delete(key)
            logger.info(f"✅ 已清除 {len(result_keys)} 个任务结果")
        else:
            print("\n✓ 没有任务结果需要清除")

    def clear_worker_metadata(self):
        """清除 Worker 元数据（心跳、统计等）"""
        patterns = ["*celery@*", "*celeryev*", "*unacked*"]
        total_cleared = 0

        for pattern in patterns:
            keys = self.get_celery_keys(pattern)
            if keys:
                print(f"\n🗑️  清除元数据: {pattern} ({len(keys)} 个键)")
                for key in keys:
                    self.redis_client.delete(key)
                total_cleared += len(keys)

        if total_cleared > 0:
            logger.info(f"✅ 已清除 {total_cleared} 个元数据键")
        else:
            print("\n✓ 没有元数据需要清除")

    def clear_all(self):
        """清空所有 Celery 相关数据"""
        print("\n" + "="*80)
        print("清空所有 Celery 数据")
        print("="*80)

        # 获取所有 celery 相关的键
        all_keys = self.get_celery_keys("*celery*")

        if not all_keys:
            print("\n✓ Redis 中没有 Celery 相关数据")
            return

        print(f"\n⚠️  找到 {len(all_keys)} 个 Celery 相关键")

        # 删除所有键
        deleted_count = 0
        for key in all_keys:
            try:
                self.redis_client.delete(key)
                deleted_count += 1
            except Exception as e:
                logger.error(f"删除键失败 {key}: {e}")

        print(f"✅ 已清除 {deleted_count} 个键")
        logger.info(f"清空完成: {deleted_count}/{len(all_keys)} 个键")

    def clear_specific_patterns(self, patterns: list):
        """根据指定的模式清理数据"""
        total_cleared = 0

        for pattern in patterns:
            keys = self.get_celery_keys(pattern)
            if keys:
                print(f"\n🗑️  清除匹配 '{pattern}' 的键 ({len(keys)} 个)")
                for key in keys:
                    self.redis_client.delete(key)
                total_cleared += len(keys)

        print(f"\n✅ 总计清除 {total_cleared} 个键")

    def get_redis_info(self):
        """获取 Redis 基本信息"""
        info = self.redis_client.info()

        print("\n" + "="*80)
        print("Redis 服务器信息")
        print("="*80)
        print(f"Redis 版本: {info.get('redis_version', 'N/A')}")
        print(f"已用内存: {info.get('used_memory_human', 'N/A')}")
        print(f"连接的客户端: {info.get('connected_clients', 'N/A')}")
        print(f"总键数: {info.get('db0', {}).get('keys', 0) if 'db0' in info else 0}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='清理 Redis 中的 Celery 消息和数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 列出所有 Celery 数据
  python clear_celery_redis.py --list

  # 清空任务队列
  python clear_celery_redis.py --clear-queue

  # 清空任务结果
  python clear_celery_redis.py --clear-results

  # 清空所有 Celery 数据
  python clear_celery_redis.py --clear-all

  # 清空特定模式的数据
  python clear_celery_redis.py --pattern "celery-task-meta-*"

  # 查看 Redis 信息
  python clear_celery_redis.py --info
        """
    )

    parser.add_argument('--list', action='store_true',
                       help='列出所有 Celery 相关数据')
    parser.add_argument('--clear-queue', action='store_true',
                       help='清空任务队列')
    parser.add_argument('--queue-name', default='celery',
                       help='队列名称（默认: celery）')
    parser.add_argument('--clear-results', action='store_true',
                       help='清空所有任务结果')
    parser.add_argument('--clear-metadata', action='store_true',
                       help='清除 Worker 元数据')
    parser.add_argument('--clear-all', action='store_true',
                       help='清空所有 Celery 相关数据')
    parser.add_argument('--pattern', action='append',
                       help='清除匹配指定模式的键（可多次使用）')
    parser.add_argument('--info', action='store_true',
                       help='显示 Redis 服务器信息')
    parser.add_argument('-y', '--yes', action='store_true',
                       help='跳过确认提示')

    args = parser.parse_args()

    # 如果没有提供任何参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        return

    try:
        cleaner = CeleryRedisCleaner()

        # 显示 Redis 信息
        if args.info:
            cleaner.get_redis_info()

        # 列出数据
        if args.list:
            cleaner.list_celery_data()

        # 执行清理操作前确认
        if any([args.clear_queue, args.clear_results, args.clear_metadata,
                args.clear_all, args.pattern]):
            if not args.yes:
                response = input("\n⚠️  确定要执行清理操作吗？(y/N): ")
                if response.lower() != 'y':
                    print("❌ 操作已取消")
                    return

        # 清空队列
        if args.clear_queue:
            cleaner.clear_task_queue(args.queue_name)

        # 清空结果
        if args.clear_results:
            cleaner.clear_task_results()

        # 清除元数据
        if args.clear_metadata:
            cleaner.clear_worker_metadata()

        # 清空所有
        if args.clear_all:
            cleaner.clear_all()

        # 按模式清理
        if args.pattern:
            cleaner.clear_specific_patterns(args.pattern)

        print("\n✅ 操作完成\n")

    except redis.ConnectionError as e:
        logger.error(f"❌ Redis 连接失败: {e}")
        print(f"\n❌ 无法连接到 Redis 服务器")
        print("请检查:")
        print("  1. Redis 服务是否正在运行")
        print("  2. CELERY_BROKER_URL 配置是否正确")
        print(f"  3. 当前配置: {settings.CELERY_BROKER_URL}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}")
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
