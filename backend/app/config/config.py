import os
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, computed_field
from typing import List, Optional
import os
from pathlib import Path

# Determine whether to load local .env (skip in Docker)
_skip_local = os.getenv("SKIP_LOCAL_DOTENV", "").lower() in ("1", "true", "yes") or \
               os.getenv("DOCKER_CONTEXT", "").lower() in ("1", "true", "yes")
_env_file_path = str(Path(__file__).resolve().parents[2] / ".env") if not _skip_local else None


class Settings(BaseSettings):
    # Project info
    PROJECT_NAME: str = "ACRAC System"
    VERSION: str = "1.1.0"
    API_V1_STR: str = "/api/rag_v1"


    POSTGRESQL_DATABASE_NAME: str = Field(default="your_database_name", description="所连接的数据库名称")
    POSTGRESQL_ASYNC_DRIVER: str = Field(default="asyncpg", description="异步数据库驱动")
    POSTGRESQL_SYNC_DRIVER: str = Field(default="psycopg2", description="同步数据库驱动")
    POSTGRESQL_USER_NAME: str = Field(default="your_username", description="数据库用户名")
    POSTGRESQL_PASSWORD: str = Field(default="your_password", description="数据库密码")
    POSTGRESQL_HOST: str = Field(default="localhost", description="数据库地址")
    POSTGRESQL_PORT: int = Field(default=5432, description="数据库端口")
    # 高并发场景优化配置
    POSTGRESQL_POOL_SIZE: int = Field(default=50, description="数据库连接池大小（高并发优化：50）")
    POSTGRESQL_MAX_OVERFLOW: int = Field(default=30, description="数据库连接池溢出大小（高并发优化：30）")
    POSTGRESQL_POOL_RECYCLE: int = Field(default=1800, description="数据库连接池回收时间（30分钟）")
    POSTGRESQL_POOL_TIMEOUT: int = Field(default=10, description="连接池获取连接超时时间（秒）")
    POSTGRESQL_ECHO: bool = Field(default=False, description="数据库是否打印SQL")
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")  # 修复：使用docker服务名而不是localhost
    # Celery
    CELERY_BROKER_URL: str = Field(default= "redis://redis:6379/1")  # 修复：使用docker服务名而不是localhost
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis:6379/2")  # 修复：使用docker服务名而不是localhost

    DASHSCOPE_EMBEDDING_MODEL: str = Field(default="text-embedding-v3", description="DashScope的嵌入模型名称")
    DASHSCOPE_API_KEY: str = Field(default="")
    DASHSCOPE_BASE_URL: str = Field(default="")
    # deepseek在线模型配置
    DEEPSEEK_API_KEY: str = Field(default=None, description="deepseek在线api_key")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1", description="deepseek在线base_url")
    DEEPSEEK_MODEL_NAME: str = Field(default="deepseek-chat", description="deepseek模型名称")

    # Ollama Configuration
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "qwen3:30b")
    OLLAMA_LLM_MAX_TOKENS:int=Field(default=4096,description="部署的模型上下文长度")
    # OLLAMA_EMBEDDING_BASE_URL:str=Field(description="ollama_embedding_model的地址",default="http://10.101.1.178:42526/v1")
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
    OLLAMA_EMBEDDING_DIMENSION: str = Field(default=1024, description="嵌入维度")
    # SiliconFlow API Configuration
    # 安全性：不再提供任何默认密钥，必须通过环境变量配置
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_EMBEDDING_MODEL: str = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
    SILICONFLOW_LLM_MODEL: str = os.getenv("SILICONFLOW_LLM_MODEL", "Qwen/Qwen2.5-32B-Instruct")
    SILICONFLOW_BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

    # Development
    DEBUG: bool = True
    RELOAD: bool = True



    @computed_field
    @property
    def async_connection_url(self) -> str:
        """构建异步数据库连接URL"""
        encoded_password = quote_plus(self.POSTGRESQL_PASSWORD)
        return (
            f"postgresql+{self.POSTGRESQL_ASYNC_DRIVER}://"
            f"{self.POSTGRESQL_USER_NAME}:{encoded_password}@"
            f"{self.POSTGRESQL_HOST}:{self.POSTGRESQL_PORT}/"
            f"{self.POSTGRESQL_DATABASE_NAME}"
        )

    @computed_field
    @property
    def sync_connection_url(self) -> str:
        """构建同步数据库连接URL"""
        encoded_password = quote_plus(self.POSTGRESQL_PASSWORD)
        return (
            f"postgresql+{self.POSTGRESQL_SYNC_DRIVER}://"
            f"{self.POSTGRESQL_USER_NAME}:{encoded_password}@"
            f"{self.POSTGRESQL_HOST}:{self.POSTGRESQL_PORT}/"
            f"{self.POSTGRESQL_DATABASE_NAME}"
        )



    # Pydantic v2 settings configuration
    # - In Docker, skip loading backend/.env to avoid localhost DSNs
    # - Otherwise, load backend/.env for local dev
    # - Be case sensitive; ignore extra env keys
    model_config = SettingsConfigDict(
        env_file=_env_file_path,
        case_sensitive=True,
        extra="ignore",
    )

# Create settings instance
settings = Settings()


if __name__ == '__main__':
   print( settings.async_connection_url)