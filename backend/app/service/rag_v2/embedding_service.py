from dataclasses import dataclass
import tiktoken
from injector import inject
from langchain_classic.embeddings import CacheBackedEmbeddings

from langchain_community.storage import RedisStore

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings


from app.config.config import settings


@inject
@dataclass
class EmbeddingsService:
    """文本嵌入模型服务"""
    _store: RedisStore
    _embeddings: Embeddings
    _cache_backed_embeddings: CacheBackedEmbeddings

    def __init__(self):
        """构造函数，初始化文本嵌入模型客户端、存储器、缓存客户端"""

        
        self.document_store = RedisStore(redis_url=f"{settings.REDIS_URL}/8" )
        self.query_store = RedisStore(redis_url=f"{settings.REDIS_URL}/9")
        # self._embeddings = HuggingFaceEmbeddings(
        #     model_name="Alibaba-NLP/gte-multilingual-base",
        #     cache_folder=os.path.join(os.getcwd(), "internal", "core", "embeddings"),
        #     model_kwargs={
        #         "trust_remote_code": True,
        #     }
        # )
        self._embeddings = OpenAIEmbeddings(
            model=settings.OLLAMA_EMBEDDING_MODEL,
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.OLLAMA_BASE_URL,
        )
        # self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self._cache_backed_embeddings = CacheBackedEmbeddings.from_bytes_store(
            underlying_embeddings= self._embeddings,
            document_embedding_cache=self.document_store,
            namespace="embedding",
            key_encoder="blake2b", # 安全的键编码
            query_embedding_cache=self.query_store,
        )


    @classmethod
    def calculate_token_count(cls, query: str) -> int:
        """计算传入文本的token数"""
        encoding = tiktoken.encoding_for_model("gpt-3.5")
        return len(encoding.encode(query))

    @property
    def store(self) -> RedisStore:
        return self._store

    @property
    def embeddings(self) -> Embeddings:
        return self._embeddings

    @property
    def cache_backed_embeddings(self) -> CacheBackedEmbeddings:
        return self._cache_backed_embeddings