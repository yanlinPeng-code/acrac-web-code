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
    
    # Database - 连接到Docker容器中的PostgreSQL
    # 修复：优先使用环境变量中的DATABASE_URL，如果没有则使用默认值
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres:5432/acrac_db")
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 0
    
    # PostgreSQL 配置
    PGHOST: str = os.getenv("PGHOST", "postgres")  # 修复：使用docker服务名而不是localhost
    PGPORT: str = os.getenv("PGPORT", "5432")
    PGDATABASE: str = os.getenv("PGDATABASE", "acrac_db")
    PGUSER: str = os.getenv("PGUSER", "postgres")
    PGPASSWORD: str = os.getenv("PGPASSWORD", "password")
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
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here-please-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
    )
    
    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # 尝试解析JSON格式
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            
            # 处理类似 [url1,url2] 格式的字符串
            if v.startswith('[') and v.endswith(']'):
                # 移除方括号并按逗号分割
                content = v[1:-1]
                return [origin.strip() for origin in content.split(',') if origin.strip()]
            
            # 如果不是特殊格式，按逗号分割
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v

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

    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")  # 修复：使用docker服务名而不是localhost
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")  # 修复：使用docker服务名而不是localhost
    
    # Embedding Model (统一使用嵌入配置)
    # EMBEDDING_MODEL_TYPE: str = "bge-m3"
    # EMBEDDING_MODEL_NAME: str = "bge-m3:latest"
    # EMBEDDING_DIMENSION: int = 1024

    DASHSCOPE_EMBEDDING_MODEL: str=Field(default="text-embedding-v3", description="DashScope的嵌入模型名称")
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    # Ollama Configuration
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "qwen3:30b")
    # OLLAMA_EMBEDDING_BASE_URL:str=Field(description="ollama_embedding_model的地址",default="http://10.101.1.178:42526/v1")
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
    OLLAMA_EMBEDDING_DIMENSION:str=Field(default=1024,description="嵌入维度")
    # SiliconFlow API Configuration
    # 安全性：不再提供任何默认密钥，必须通过环境变量配置
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_EMBEDDING_MODEL: str = os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
    SILICONFLOW_LLM_MODEL: str = os.getenv("SILICONFLOW_LLM_MODEL", "Qwen/Qwen2.5-32B-Instruct")
    SILICONFLOW_BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    
    # Reranker Configuration
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    
    # OpenAI API Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # RAG API Configuration
    RAG_API_URL: str = os.getenv("RAG_API_URL", "http://127.0.0.1:8002/api/v1/acrac/rag-llm/intelligent-recommendation")

    # RAG 配置
    VECTOR_SIMILARITY_THRESHOLD: float = 0.6
    DEBUG_MODE: bool = True
    
    # 提示词配置参数
    RAG_TOP_SCENARIOS: int = 2
    RAG_TOP_RECOMMENDATIONS_PER_SCENARIO: int = 3
    RAG_SHOW_REASONING: bool = True
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 104857600  # 100MB
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xls", ".csv", ".json"]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/acrac.log"
    
    # Development
    DEBUG: bool = True
    RELOAD: bool = True

    # Rules Engine (default disabled)
    RULES_ENABLED: bool = False
    RULES_AUDIT_ONLY: bool = True
    RULES_CONFIG_PATH: str = str(Path(__file__).resolve().parents[2] / "config" / "rules_packs.json")
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

# Ensure log directory exists
log_dir = Path(settings.LOG_FILE).parent
log_dir.mkdir(exist_ok=True)
if __name__ == '__main__':
   print( settings.async_connection_url)