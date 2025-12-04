from fastapi import Depends
from typing_extensions import Annotated
from app.config.database import get_db, SessionDep
from app.service.rag_v1.ai_service import AiService
from app.service.rag_v1.embedding_service import EmbeddingsService
from app.service.rag_v1.model_service import ModelService
from app.service.rag_v1.rag_service import RagService
from app.service.rag_v1.retrieval_service import RetrievalService
from app.service.rag_v1.simple_retrieval_service import SimpleRetrievalService
from app.service.eval_v1.evaluation_service import EvaluationService
from app.service.rag_v1.vector_database_service import VectorDatabaseService
from app.service.eval_v1.judge_service import JudgeService
from app.service.rag_v2.rerank.adaptive_reranker import AdaptiveReranker
from app.service.rag_v2.rerank.detail_reranker import DetailReranker
from app.service.rag_v2.rerank.final_choice_adaptive_reranker import FinalChoiceAdaptiveReranker
from app.service.rag_v2.rerank.final_choice_reranker import FinalChoiceReranker
from app.service.rag_v2.rerank.simple_final_choice_reranker import SimpleFinalChoiceReranker
from app.service.rag_v2.rerank.simple_reranker import SimpleReranker
from app.service.rag_v2.rerank_service import RerankService
from app.service.rag_v2.rag_service import RagService as RagService_V2
from app.service.rag_v2.retrieval_serivce import RetrievalService as RetrievalService_V2







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

def get_retrieval_service_v2():
    return RetrievalService_V2()

def get_adaptive_reranker():
    return AdaptiveReranker()

def get_detail_reranker(
         adaptive_reranker:AdaptiveReranker=Depends(get_adaptive_reranker)
):
    return DetailReranker(adaptive_recommendation_engine_service=adaptive_reranker)

def get_simple_reranker():
    return SimpleReranker()

def get_adaptive_reranker_final():
    return FinalChoiceAdaptiveReranker()

def get_final_choice_reranker(
        adaptive_service:FinalChoiceAdaptiveReranker=Depends(get_adaptive_reranker_final)

):
    return FinalChoiceReranker(adaptive_service=adaptive_service)

def get_simple_final_choice_reranker():
    return SimpleFinalChoiceReranker()

def get_rerank_service(
        detail_reranker:DetailReranker=Depends(get_detail_reranker),
        simple_reranker:SimpleReranker=Depends(get_simple_reranker),
        final_choice_reranker:FinalChoiceAdaptiveReranker=Depends(get_final_choice_reranker),
        simple_final_choice_reranker:SimpleFinalChoiceReranker=Depends(get_simple_final_choice_reranker)

):
    return RerankService(
          detail_reranker=detail_reranker,
          simple_reranker=simple_reranker,
          final_choice_reranker=final_choice_reranker,
          simple_final_choice_reranker=simple_final_choice_reranker


    )

def get_rag_service_v2(
                   session: SessionDep,
                   retrieval_service:RetrievalService=Depends(get_retrieval_service_v2),
                   rerank_service:RerankService=Depends(get_rerank_service),
):
    return RagService_V2(
        session=session,
        rerank_service=rerank_service,
        retrieval_service=retrieval_service
    )

def get_judge_service(
       
):
    return JudgeService()



RagRecommendDep = Annotated[RagService, Depends(get_rag_service)]
RagRecommendDep_V2=Annotated[RagService_V2,Depends(get_rag_service_v2)]
def get_evaluation_service():
    return EvaluationService()






EvaluationDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
JudgeDep = Annotated[JudgeService, Depends(get_judge_service)]
