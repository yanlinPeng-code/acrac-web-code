from langchain_openai import OpenAIEmbeddings

from app.core.language_model.entities.model_entity import BaseEmbeddingModel


class Embedding(OpenAIEmbeddings, BaseEmbeddingModel):
    """向量模型类"""
    pass
