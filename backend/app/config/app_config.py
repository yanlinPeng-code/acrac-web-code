import contextlib

from  fastapi import  FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config.database import async_db_manager
from app.config.redis_config import redis_manager
from app.core.language_model.registry import model_registry
from app.response.exception.global_exception import GlobalReOrExHandler
from app.response.response_middleware import ResponseMiddleware
from app.controller.rag_v1 import recommend_router
from app.utils.jieba_middleware import jiebaLoader
from app.utils.logger.simple_logger import setup_logging
from app.utils.logger.simple_logger import get_logger
from app.service.rag_v1.ai_service import AiService
from app.controller.eval_v1 import evl_router,judge_router
# 创建日志记录器
logger = get_logger(__name__)






def add_middleware(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    # 添加响应中间件
    app.add_middleware(
        ResponseMiddleware,
        enable_tracing=True,
        enable_request_id=True
    )
    # 添加日志中间件
    # app.add_middleware(StructlogMiddleware,
    #                    enable_request_logging=True,
    #                    enable_performance_logging=True)
    # app.add_middleware(BusinessLoggingMiddleware)
    # app.add_middleware(PerformanceLoggingMiddleware, slow_request_threshold=1000.0)
    # app.add_middleware(SecurityLoggingMiddleware)
    #


async  def init_resource():
      # 初始化日志系统
      setup_logging(level="INFO", log_to_file=False)
      
      logger.info("正在注册数据库")

      #初始化PostgreSQL配置

      await async_db_manager.init()
      # await model_manager_init.init()
      # await preload_all_on_startup()
      logger.info("注册数据库完成")
      
      # 初始化Redis配置
      logger.info("正在初始化 Redis")
      await redis_manager.init()
      logger.info("Redis 初始化完成")

      logger.info("正在注册模型")
      model_registry.initialize_models()
      logger.info("模型注册完成")





async def register_router(app:FastAPI):
    #这里注册的是新版本的路由。

    logger.info("正在注册路由")
    app.include_router(recommend_router)
    app.include_router(evl_router)
    app.include_router(judge_router)
    logger.info("注册路由完成")


@contextlib.asynccontextmanager
async def life_span(app:FastAPI):
    logger.info(f"正在启动fastapi应用")
    try:
         #初始化数据库
         await init_resource()
         #注册路由
         await register_router(app)


         yield
    finally:
         # 关闭 Redis 连接
         logger.info("正在关闭 Redis 连接")
         await redis_manager.close()
         logger.error(f"fastapi应用关闭")
         await AiService.close_client()

def create_app():
    logger.info("创建 FastAPI 应用实例")
    
    app = FastAPI(
        title="acro",
        description="推荐系统",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=life_span
    )
    logger.info("正在注册全局异常管理器")
    GlobalReOrExHandler(app)
    logger.info("注册全局异常管理器成功")
    logger.info("正在注册中间件")
    add_middleware(app)
    logger.info("注册中间件成功")
    # 注册结巴分词服务
    # jiebaLoader(app)
    
    return app



