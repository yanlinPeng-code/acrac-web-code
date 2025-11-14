from fastapi import Depends
from typing_extensions import Annotated
from app.config.database import get_db, SessionDep
from app.service.rag_v1.ai_service import AiService
from app.service.rag_v1.embedding_service import EmbeddingsService
from app.service.rag_v1.model_service import ModelService
from app.service.rag_v1.rag_service import RagService
from app.service.rag_v1.retrieval_service import RetrievalService
from app.service.rag_v1.simple_retrieval_service import SimpleRetrievalService
from app.service.rag_v1.evaluation_service import EvaluationService
from app.service.rag_v1.vector_database_service import VectorDatabaseService





def get_model_service():
    return ModelService()
def get_ai_service():
    return AiService()

def get_embeddings_service(
):
    return EmbeddingsService()


def get_vectorstore_service(
        embeddings_services: EmbeddingsService = Depends(get_embeddings_service),

):
    return VectorDatabaseService(embeddings_services)
def get_retrieval_service(
        session:SessionDep,
        ai_service: AiService = Depends(get_ai_service),
        vectorstore_service: VectorDatabaseService = Depends(get_vectorstore_service),
):
    return RetrievalService(session, ai_service, vectorstore_service)


def get_simple_retrieval_service(
        session: SessionDep,
        ai_service: AiService = Depends(get_ai_service),
        vectorstore_service: VectorDatabaseService = Depends(get_vectorstore_service),
):
    return SimpleRetrievalService(session,ai_service,vectorstore_service)



def get_rag_service(
        session: SessionDep,
        model_service: ModelService = Depends(get_model_service),
        retrieval_service: RetrievalService = Depends(get_retrieval_service),
        simple_retrieval_service:SimpleRetrievalService=Depends(get_simple_retrieval_service)

):
    return RagService(session, model_service, retrieval_service,simple_retrieval_service)



RagRecommendDep = Annotated[RagService, Depends(get_rag_service)]

def get_evaluation_service():
    return EvaluationService()

EvaluationDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
