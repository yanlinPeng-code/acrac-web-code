from langchain_community.vectorstores import Milvus
import asyncio
import json
from typing import Union
from langchain_core.documents import Document
from  langchain_openai import OpenAIEmbeddings
from langchain_milvus import Milvus, BM25BuiltInFunction
from pymilvus import DataType, Function, FunctionType
from sqlalchemy.orm import selectinload
from sqlmodel import select
from app.config.config import settings
from app.config.database import async_db_manager
from app.model import ClinicalScenario, Topic, Panel
def init_embedding_model():
    print(f"api_key:{settings.OPENAI_API_KEY}")
    print(f"base_url:{settings.OLLAMA_BASE_URL}")
    print(f"model:{settings.OLLAMA_EMBEDDING_MODEL}")

    embedding=OpenAIEmbeddings(
        api_key=settings.SILICONFLOW_API_KEY,
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_EMBEDDING_MODEL


    )

    return embedding



async def get_document(
):
    await async_db_manager.init()


    # 获取异步会话
    async with async_db_manager.async_session_factory() as session:
            # 查询所有需要生成embedding的临床场景
            statement = select(ClinicalScenario).options(
                selectinload(ClinicalScenario.panel),
                selectinload(ClinicalScenario.topic)
            )
            result = await session.execute(statement)
            resp:Union[ClinicalScenario,Panel,Topic] = result.scalars().all()

    documents = []
    for r in resp:
        try:
            # 主键与集合字段保持一致（此处使用字符串主键）
            doc_id = str(r.id)
            page_content = r.description_zh


            # 创建 Document 对象，将panel_name和topic_name作为字段而不是Document属性
            # 让 panel_name / topic_name 作为独立列写入，而不是 JSON
            doc = Document(
                id=doc_id,
                page_content=page_content,
                metadata={
                    "panel_name": r.panel.name_zh,
                    "topic_name": r.topic.name_zh,
                    # 其它元数据如需保留可继续放在 dict 中
                    "panel_id": r.panel.id,
                    "panel_semantic_id": r.panel.semantic_id,
                    "topic_id": r.topic.id,
                    "topic_semantic_id": r.topic.semantic_id,
                }
            )
            documents.append(doc)

        except (ValueError, TypeError) as e:
            print(f"转换 ID 时出错: {r.id}, 错误: {e}")
            continue

    print(f"成功创建 {len(documents)} 个文档")
    if documents:
        print(f"第一个文档 ID: {documents[0].id}, 类型: {type(documents[0].id)}")

    return documents
# 假设你的_init_milvus_client返回的是langchain的Milvus实例（含连接信息）
def _init_milvus_client():
    return Milvus(
        drop_old=False,
        collection_name="scenarios",  # 暂时不指定集合名，创建时再指定
        embedding_function=init_embedding_model(),  # 你的密集向量模型
        connection_args={"uri": "http://10.101.1.178:19530", "db_name": "acrac"},
    )


async def create_collection(name: str, origin_text_name: str = "text"):
    vector_store = _init_milvus_client()
    client = vector_store.aclient  # 获取Milvus异步客户端

    # 1. 创建Schema
    schema = client.create_schema(
        auto_id=False,
        # 关闭动态字段，避免默认 JSON 动态字段导致自动索引失败
        enable_dynamic_field=False,
    )

    # 主键字段
    schema.add_field(
        field_name="id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=2000,
    )

    schema.add_field(
        field_name="topic_id",
        datatype=DataType.INT64,
    )
    schema.add_field(
        field_name="topic_semantic_id",
        datatype=DataType.VARCHAR,
        max_length = 2000,
    )

    # 密集向量字段（1024维）
    schema.add_field(
        field_name="text_dense",
        datatype=DataType.FLOAT_VECTOR,
        dim=1024,
    )

    # 稀疏向量字段（Milvus稀疏向量不需要显式指定dim，自动推断）
    schema.add_field(
        field_name="text_sparse",
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )

    # 原始文本字段（带分析器，用于BM25）
    schema.add_field(
        field_name=origin_text_name,
        datatype=DataType.VARCHAR,
        max_length=2000,
        enable_analyzer=True,
        enable_match=True,
        analyzer_params={"tokenizer": "jieba", "filter": ["cnalphanumonly"]},
    )

    # 元数据字段
    schema.add_field(
        field_name="panel_semantic_id",
        datatype=DataType.VARCHAR,
        max_length=2000,
    )
    schema.add_field(
        field_name="panel_id",
        datatype=DataType.INT64,

    )
    schema.add_field(
        field_name="panel_name",
        datatype=DataType.VARCHAR,
        max_length=255
    )
    schema.add_field(
        field_name="topic_name",
        datatype=DataType.VARCHAR,
        max_length=255
    )
    # 2. 添加BM25函数（用于生成稀疏向量）
    bm25_function = Function(
        name="text_bm25_emb",
        input_field_names=[origin_text_name],  # 输入：原始文本字段
        output_field_names=["text_sparse"],  # 输出：稀疏向量字段
        function_type=FunctionType.BM25,
    )
    schema.add_function(bm25_function)

    # 3. 配置索引
    index_params = client.prepare_index_params()

    # 稀疏向量索引（BM25）
    index_params.add_index(
        field_name="text_sparse",
        index_type="SPARSE_INVERTED_INDEX",
        index_name="sparse_inverted_index",
        metric_type="BM25",
        params={"invert_index_algo": "DAAT_MAXSCORE"},
    )

    # 密集向量索引（余弦相似度）
    index_params.add_index(
        field_name="text_dense",
        index_type="FLAT",
        index_name="text_dense_index",
        metric_type="COSINE",
    )

    # 4. 实际创建集合
    await client.create_collection(
        collection_name=name,
        schema=schema,
        index_params=index_params,
        consistency_level="Bounded",
    )
    print(f"集合 {name} 创建成功，Schema和索引已应用")


async def insert_vector(collection_name: str, origin_text_name: str = "text"):
    # 1. 先确保集合已创建（实际使用时可加判断，避免重复创建）


    # 2. 获取文档数据
    docs = await get_document()  # 你的文档获取逻辑

    # 3. 初始化Milvus向量存储（复用已创建的集合）
    vector_store = Milvus.from_documents(
        documents=docs,
        embedding=init_embedding_model(),  # 密集向量生成器（输出到text_dense）
        builtin_function=BM25BuiltInFunction(  # 关联BM25函数（生成稀疏向量到text_sparse）
            input_field_names=origin_text_name,
            output_field_names="text_sparse",
        ),
        # 禁用动态字段，使用显式 schema 中的列接收 metadata 键
        enable_dynamic_field=True,

        primary_field="id",
        collection_name=collection_name,
        connection_args={"uri": "http://10.101.1.178:19530", "db_name": "acrac"},
        text_field=origin_text_name,  # 原始文本对应字段
        vector_field=["text_dense", "text_sparse"],  # 向量字段映射（密集+稀疏）
        drop_old=False,  # 关键：不删除旧集合，复用已创建的
        consistency_level="Bounded",
    )

    a=vector_store.similarity_search(
        "35，男，头晕头疼一周", k=1, ranker_type="weighted", ranker_params={"weights": [0.6, 0.4]}
    )
    print(a)
    print(f"成功插入 {len(docs)} 条文档到集合 {collection_name}")
async def recreate_collection(collection_name: str, origin_text_name: str = "text"):
    """删除并重建集合，应用无 JSON 的 schema（会清空原数据）。"""
    vector_store = _init_milvus_client()
    client = vector_store.aclient
    exists = await client.has_collection(collection_name)
    if exists:
        await client.drop_collection(collection_name)
    await create_collection(collection_name, origin_text_name)


if __name__ == '__main__':
   # 如需一键修复 schema，可先执行重建（会清空原集合数据）
   # asyncio.run(recreate_collection(collection_name="scenarios"))
   # asyncio.run(create_collection("scenarios"))
   # vector=_init_milvus_client()
   # print(vector.max_marginal_relevance_search("nihao"))
   asyncio.run(insert_vector(collection_name="scenarios"))