import redis.asyncio as aioredis
from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis
from typing import Optional
import asyncio
import threading
from app.config.config import settings
from app.utils.logger.simple_logger import get_logger
logger = get_logger(__name__)
class RedisManager:
    """
    Redis 连接管理器（支持同步和异步，线程安全）
    
    使用异步锁和线程锁保证多线程/多协程环境下的初始化安全
    """
    
    def __init__(self):
        self._async_client: Optional[AsyncRedis] = None
        self._sync_client: Optional[SyncRedis] = None
        self._is_initialized: bool = False
        
        # 异步锁（用于异步初始化）
        self._async_lock: Optional[asyncio.Lock] = None
        
        # 线程锁（用于同步访问状态）
        self._thread_lock = threading.Lock()
    
    async def init(self):
        """
        初始化 Redis 连接（同步和异步）
        
        线程安全：使用异步锁防止并发初始化
        """
        # 初始化异步锁（如果还没有创建）
        if self._async_lock is None:
            with self._thread_lock:
                if self._async_lock is None:
                    self._async_lock = asyncio.Lock()
        
        # 使用异步锁保护初始化过程
        async with self._async_lock:
            # 双重检查：锁内再次检查是否已初始化
            if self._is_initialized:
                logger.warning("Redis 已经初始化，跳过重复初始化")
                return
            
            try:
                logger.info(f"正在连接 Redis: {settings.REDIS_URL}")
                
                # 初始化异步客户端
                self._async_client = await aioredis.from_url(
                    f"{settings.REDIS_URL}/0",
                    max_connections=10
                )
                # 测试异步连接
                await self._async_client.ping()
                
                # 初始化同步客户端（用于普通缓存，自动解码）
                self._sync_client = SyncRedis.from_url(
                    f"{settings.REDIS_URL}/0",
                    max_connections=10
                )
                
                # 原子性更新状态
                with self._thread_lock:
                    self._is_initialized = True
                
                logger.info("Redis 连接成功（同步 + 异步）")
            except Exception as e:
                logger.error(f"Redis 连接失败: {str(e)}")
                raise
    
    async def close(self):
        """
        关闭 Redis 连接
        
        线程安全：使用锁保护关闭操作
        """
        # 如果异步锁存在，使用它来保护关闭操作
        if self._async_lock:
            async with self._async_lock:
                await self._do_close()
        else:
            await self._do_close()
    
    async def _do_close(self):
        """内部关闭方法"""
        try:
            if self._async_client:
                await self._async_client.close()
            if self._sync_client:
                self._sync_client.close()
            
            # 原子性更新状态
            with self._thread_lock:
                self._is_initialized = False
            
            logger.info("Redis 连接已关闭")
        except Exception as e:
            logger.error(f"关闭 Redis 连接时出错: {str(e)}")
    
    @property
    def async_client(self) -> AsyncRedis:
        """
        获取异步 Redis 客户端
        
        线程安全：读取状态时使用线程锁
        """
        with self._thread_lock:
            if not self._is_initialized or not self._async_client:
                raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
            return self._async_client
    
    @property
    def sync_client(self) -> SyncRedis:
        """
        获取同步 Redis 客户端（用于 LangChain 等）
        
        线程安全：读取状态时使用线程锁
        """
        with self._thread_lock:
            if not self._is_initialized or not self._sync_client:
                raise RuntimeError("Redis 未初始化，请先调用 init() 方法")
            return self._sync_client
    


    
    async def aget(self, key: str) -> Optional[str]:
        """获取键值（异步）"""
        return await self.async_client.get(key)
    
    async def aset(self, key: str, value: str, ex: Optional[int] = None):
        """设置键值（异步）"""
        return await self.async_client.set(key, value, ex=ex)
    
    async def adelete(self, *keys: str) -> int:
        """删除键（异步）"""
        return await self.async_client.delete(*keys)
    
    async def aexists(self, *keys: str) -> int:
        """检查键是否存在（异步）"""
        return await self.async_client.exists(*keys)
    
    async def aexpire(self, key: str, seconds: int) -> bool:
        """设置过期时间（异步）"""
        return await self.async_client.expire(key, seconds)

# 创建全局 Redis 管理器实例
redis_manager = RedisManager()