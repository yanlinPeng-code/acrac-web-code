from typing import Sequence

from langchain_openai.embeddings import OpenAIEmbeddings

from app.core.language_model.entities.model_entity import BaseEmbeddingModel


class Reranker(OpenAIEmbeddings,BaseEmbeddingModel):
      def rerank(self, query: str, documents: Sequence[str], top_n: int = 5):
          pass



