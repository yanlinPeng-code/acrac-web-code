# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
# from sqlalchemy.pool import StaticPool
# import logging
#
# from app.core.config import settings
#
# logger = logging.getLogger(__name__)
#
# # Create database engine
# engine = create_engine(
#     settings.DATABASE_URL,
#     pool_size=settings.DATABASE_POOL_SIZE,
#     max_overflow=settings.DATABASE_MAX_OVERFLOW,
#     pool_pre_ping=True,
#     echo=settings.DEBUG,  # Log SQL queries in debug mode
# )
#
# # Create SessionLocal class
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
#
# # Create Base class for models
# Base = declarative_base()
#
# def get_db():
#     """数据库会话依赖"""
#     db = SessionLocal()
#     try:
#         yield db
#     except Exception as e:
#         logger.error(f"Database error: {e}")
#         db.rollback()
#         raise
#     finally:
#         db.close()
#
# def test_db_connection():
#     """测试数据库连接"""
#     try:
#         from sqlalchemy import text
#         with engine.connect() as conn:
#             conn.execute(text("SELECT 1"))
#         logger.info("Database connection successful")
#         return True
#     except Exception as e:
#         logger.error(f"Database connection failed: {e}")
#         return False
import contextlib
from typing import Optional, AsyncGenerator, Generator, Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session as SyncSession,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.config import settings
from app.utils.logger.simple_logger import get_logger

# 创建日志记录器
logger=get_logger("sql")
# 共享的基础模型类
Base = declarative_base()


class PostgreSQLAsyncSessionManager:
    """管理异步的PostgreSQL Session和连接池"""

    def __init__(self):
        self.async_engine: Optional[AsyncEngine] = None
        self.async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    async def init(self) -> None:
        """初始化异步数据库配置"""
        logger.info("----------初始化异步数据库配置----------------!")

        self.async_engine = create_async_engine(
            url=settings.async_connection_url,
            pool_size=settings.POSTGRESQL_POOL_SIZE,
            echo=settings.POSTGRESQL_ECHO,
            max_overflow=settings.POSTGRESQL_MAX_OVERFLOW,
            pool_recycle=settings.POSTGRESQL_POOL_RECYCLE,
            pool_timeout=settings.POSTGRESQL_POOL_TIMEOUT,  # 高并发优化：设置超时
            pool_pre_ping=True  # 健康检查
        )
        logger.info("--------------PostgreSQL异步引擎创建成功----------------")
        print(f"异步连接URL: {settings.async_connection_url}")

        self.async_session_factory = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
        logger.info("---------------异步会话工厂创建成功----------------")

    async def close(self):
        """关闭异步数据库引擎"""
        if self.async_engine:
            logger.info("------------正在关闭异步数据库连接！------------")
            await self.async_engine.dispose()
            logger.info("---------异步数据库连接已关闭！--------")

    @contextlib.asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取事务安全的异步session"""
        if self.async_session_factory is None:
            raise Exception("-----------请先初始化异步数据库连接！------------")

        async with self.async_session_factory() as session:
            async with session.begin():
                try:
                    yield session
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.error(f"异步数据库会话出错: {str(e)}")
                    raise
                finally:

                    await session.close()


class PostgreSQLSyncSessionManager:
    """管理同步的PostgreSQL Session和连接池"""

    def __init__(self):
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker[SyncSession]] = None

    def init(self) -> None:
        """初始化同步数据库配置"""
        logger.info("----------初始化同步数据库配置----------------!")

        self.engine = create_engine(
            url=settings.sync_connection_url,
            pool_size=settings.POSTGRESQL_POOL_SIZE,
            echo=settings.POSTGRESQL_ECHO,
            max_overflow=settings.POSTGRESQL_MAX_OVERFLOW,
            pool_recycle=settings.POSTGRESQL_POOL_RECYCLE,
            pool_timeout=settings.POSTGRESQL_POOL_TIMEOUT,  # 高并发优化：设置超时
            pool_pre_ping=True  # 健康检查
        )
        logger.info("--------------PostgreSQL同步引擎创建成功----------------")
        print(f"同步连接URL: {settings.sync_connection_url}")

        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=SyncSession,
            expire_on_commit=False,
            autoflush=False
        )
        logger.info("---------------同步会话工厂创建成功----------------")

    def close(self):
        """关闭同步数据库引擎"""
        if self.engine:
            logger.info("------------正在关闭同步数据库连接！------------")
            self.engine.dispose()
            logger.info("---------同步数据库连接已关闭！--------")

    @contextlib.contextmanager
    def get_session(self) -> Generator[SyncSession, None, None]:
        """获取事务安全的同步session"""
        if self.session_factory is None:
            raise Exception("-----------请先初始化同步数据库连接！------------")

        session = self.session_factory()
        transaction = session.begin()
        try:
            yield session
            transaction.commit()
        except Exception as e:
            transaction.rollback()
            logger.error(f"同步数据库会话出错: {str(e)}")
            raise
        finally:
            session.close()


# 实例化管理器
async_db_manager = PostgreSQLAsyncSessionManager()
sync_db_manager = PostgreSQLSyncSessionManager()


# 异步会话依赖
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_db_manager.get_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]


# 同步会话依赖
def get_sync_db() -> Generator[SyncSession, None, None]:
    with sync_db_manager.get_session() as session:
        yield session


SyncSessionDep = Annotated[SyncSession, Depends(get_sync_db)]


# 快捷初始化和关闭函数
async def init_dbs():
    """初始化所有数据库连接"""
    await async_db_manager.init()
    sync_db_manager.init()


async def close_dbs():
    """关闭所有数据库连接"""
    await async_db_manager.close()
    sync_db_manager.close()
