
import asyncio
import os
import threading
from threading import Thread
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_milvus import Milvus, BM25BuiltInFunction
from langchain_postgres import PGVectorStore, PGEngine
from typing_extensions import Any

from app.config.database import async_db_manager
from app.service.rag_v1.embedding_service import EmbeddingsService

# 向量数据库的集合名字
COLLECTION_NAME = "Datasets"

# Milvus 配置（从环境变量读取）
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_DB_NAME = os.getenv("MILVUS_DB_NAME", "acrac")
MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "scenarios")



class VectorDatabaseService:
    """向量数据库服务"""



    def __init__(self,
                 embeddings_services: EmbeddingsService,
                 ):
        self.embeddings_service = embeddings_services
        self.pg_engine = PGEngine.from_engine(engine=async_db_manager.async_engine)
        self._vector_store: Optional[PGVectorStore] = None
        self._milvus_store:Optional[Milvus]=None
        self._lock = asyncio.Lock()


    async def vector_store(self) -> PGVectorStore:
        if self._vector_store is None:
            async with self._lock:
                if self._vector_store is None:
                    self._vector_store = await PGVectorStore.create(
                        engine=self.pg_engine,
                        content_column="description_zh",
                        id_column="id",
                        table_name="clinical_scenarios",
                        embedding_column="embedding",
                        embedding_service=self.embeddings_service.cache_backed_embeddings,
                    )
        return self._vector_store
    async def milvus_vector_store(self,hybrid_search:bool=False)->Milvus:
            if self._milvus_store is None:
                async  with self._lock:
                    if self._milvus_store is None:
                        self._milvus_store=Milvus(
                                            embedding_function=self.embeddings_service.cache_backed_embeddings,  # 你的密集向量模型
                                            connection_args={"uri": MILVUS_URI, "db_name": MILVUS_DB_NAME},
                                            collection_name=MILVUS_COLLECTION_NAME,
                                            # builtin_function=BM25BuiltInFunction(  # 关联BM25函数（生成稀疏向量到text_sparse）
                                            #     input_field_names="text",
                                            #     output_field_names="text_sparse",
                                            # ),
                                            # 禁用动态字段，让元数据键写入 schema 明确的列
                                            enable_dynamic_field=True,
                                            index_params={"index_type": "FLAT", "metric_type": "COSINE"},
                                            primary_field="id",

                                            text_field="text",  # 原始文本对应字段
                                            vector_field=["text_dense"],  # 向量字段映射（密集+稀疏）
                                            drop_old=False,  # 关键：不删除旧集合，复用已创建的
                                            consistency_level="Bounded",
            )
            return self._milvus_store
        # else:
        #     return Milvus(
        #         embedding_function=self.embeddings_service.cache_backed_embeddings,  # 你的密集向量模型
        #         connection_args={"uri": "http://10.101.1.178:19530", "db_name": "acrac"},
        #         collection_name="scenarios",
        #         builtin_function=BM25BuiltInFunction(  # 关联BM25函数（生成稀疏向量到text_sparse）
        #             input_field_names="text",
        #             output_field_names="text_sparse",
        #         ),
        #         # 禁用动态字段，让元数据键写入 schema 明确的列
        #         enable_dynamic_field=True,
        #         index_params={"index_type": "FLAT", "metric_type": "COSINE"},
        #         primary_field="id",
        #
        #         text_field="text",  # 原始文本对应字段
        #         vector_field=["text_dense","text_sparse"],  # 向量字段映射（密集+稀疏）
        #         drop_old=False,  # 关键：不删除旧集合，复用已创建的
        #         consistency_level="Bounded",
        #     )

    async def add_documents(self, documents: list[Document], **kwargs: Any):
        """往向量数据库中新增文档，将vector_store使用async进行二次封装，避免在gevent中实现事件循环错误"""
        vector = await self.vector_store()
        return await vector.aadd_documents(documents, **kwargs)

    async def get_milvus_client(self):
        vector_store=await self.milvus_vector_store()
        return vector_store.aclient
    async def get_milvus_retrieval(self):
        vector_store = await self.milvus_vector_store()
        return vector_store.as_retriever(search_type="mmr", search_kwargs={"k": 100})


    async def get_retriever(self) -> VectorStoreRetriever:
        """获取检索器"""
        vector=await self.vector_store()
        return vector.as_retriever()


