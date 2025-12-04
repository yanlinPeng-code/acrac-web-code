import asyncio
import random

from typing import Optional, List, Dict, Any

from pymilvus import AnnSearchRequest, Function, FunctionType
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.model import ClinicalScenario
from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v1.embedding_service import EmbeddingsService
from app.service.rag_v1.vector_database_service import VectorDatabaseService
from app.service.rag_v2.retrieval.base_retrieval import BaseRetrieval
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)
class VectorRetrieval(BaseRetrieval):


      def __init__(self):
          super().__init__()
          self.vector_service=VectorDatabaseService(EmbeddingsService())

      async def aretrieval(self,
                           query_text: str,
                           patient_info: PatientInfo,
                           clinical_context: ClinicalContext,
                           # embedding_model: EmbeddingClientSDK,
                           top_p: int = 50,
                           top_k: int = 10,
                           similarity_threshold: float = 0.6
                           ):
          # 1. 向量化查询文本（带缓存）
          if not await self.vector_service.milvus_vector_store():
              logger.warning("向量存储未初始化")
              return []

          # 2. 高并发优化：使用独立 session 执行向量相似度检索
          try:
              vector_store = await self.vector_service.milvus_vector_store()
              documents = await vector_store.asimilarity_search_with_relevance_scores(query=query_text, k=top_p)
              logger.info(f"查询成功，共查到：{len(documents)}条数据")
          except Exception as e:
              logger.info(f"查询失败请稍后重试：{e}")
              return []

          # 过滤: 只保留指定科室的文档
          new_documents = [(document, score) for document, score in documents
                           if str(document.metadata.get("panel_name", "")) == str(clinical_context.department)]

          # 文档补充逻辑
          if len(new_documents) < top_p:
              logger.info(f"过滤后文档数量 {len(new_documents)} 不足 {top_p}，开始补充文档")

              # 获取未被过滤的文档（其他科室的文档）
              other_documents = [(document, score) for document, score in documents
                                 if str(document.metadata.get("panel_name", "")) != str(clinical_context.department)]

              # 按相似度分数降序排序其他文档
              other_documents_sorted = sorted(other_documents, key=lambda x: x[1], reverse=True)

              # 计算需要补充的数量
              need_supplement_count = top_p - len(new_documents)

              # 补充文档
              supplement_documents = other_documents_sorted[:need_supplement_count]
              new_documents.extend(supplement_documents)

              logger.info(f"补充了 {len(supplement_documents)} 个文档，现在共有 {len(new_documents)} 个文档")

          # 如果经过过滤和补充后 new_documents 仍然为空，则使用原始 documents
          if not new_documents:
              logger.warning("过滤后无文档，使用原始查询结果")
              new_documents = documents

          # 处理文档ID映射
          id_to_doc_score = {}  # {id: (doc, score)}
          for doc, score in new_documents:
              # 从metadata中获取scenario_id
              try:
                  id = int(doc.metadata.get('id') or doc.id or doc.get('id'))
                  id_to_doc_score[id] = (doc, score)
              except (ValueError, TypeError, AttributeError) as e:
                  logger.warning(f"文档ID解析失败，跳过: {doc.metadata}, 错误: {e}")
                  continue

          if not id_to_doc_score:
              logger.warning("没有有效的ID可供查询")
              return []

          # 3.2 高并发优化：使用独立 session 批量查询所有scenario对象
          scenario_ids = list(id_to_doc_score.keys())

          session = await self._get_independent_session()
          try:
              statement = (
                  select(ClinicalScenario)
                  .options(selectinload(ClinicalScenario.topic),
                           selectinload(ClinicalScenario.panel)
                           )
                  .where(
                      ClinicalScenario.id.in_(scenario_ids)
                  ))
              result = await session.exec(statement)
              scenarios = result.all()

              logger.info(f"批量查询到 {len(scenarios)} 个scenario对象")
          finally:
              await session.close()  # 确保关闭 session

          # 3.3 构建 id -> scenario 映射
          id_to_scenario = {scenario.id: scenario for scenario in scenarios}

          # 3.4 组装候选结果
          candidates = []
          for id, (doc, score) in id_to_doc_score.items():
              scenario = id_to_scenario.get(id)
              if not scenario:
                  logger.warning(f"未找到scenario: {id}")
                  continue

              # 过滤低于阈值的结果
              if score >= similarity_threshold:
                  candidates.append({
                      'scenario': scenario,
                      'scenario_id': scenario.id,
                      'score': score,
                      'document_content': doc.page_content,
                      'source': "semantic"
                      # 保存原始文档内容
                  })

          # 按相似度分数排序并返回前top_k个结果
          candidates_sorted = sorted(candidates, key=lambda x: x['score'], reverse=True)
          return candidates_sorted[:top_k]

      async def aretrieval_mmr(
              self,
              standardized_query: str,
              clinical_context: ClinicalContext,
              top_p: int = 50,
              top_k: int = 10,
              similarity_threshold: float = 0.6
      ) -> List[Dict[str, Any]]:
          """
          基于LangChain的最大边际相关性（MMR）检索

          MMR算法能够在保证相关性的同时，增加结果的多样性

          Args:
              standardized_query: 标准化后的查询文本
              top_p: 初始获取数量（fetch_k）
              top_k: 最终返回数量
              similarity_threshold: 相似度阈值

          Returns:
              候选场景列表，包含mmr_score字段
          """
          try:
              # 尝试从缓存获取 embedding 向量
              query_embedding = await self.vector_service.embeddings_service.cache_backed_embeddings.aembed_query(
                  text=standardized_query)
          except Exception as e:
              logger.error(f"向量化失败: {e}")
              return []

          try:
              # 1. 获取 vector store 和 client
              vector_store = await self.vector_service.milvus_vector_store()
              aclient = await self.vector_service.get_milvus_client()

              # 2. 并发执行MMR搜索和混合搜索
              async def execute_mmr_search():
                  """执行MMR搜索并过滤结果"""
                  mmr_results = await vector_store.amax_marginal_relevance_search_by_vector(
                      query_embedding,
                      fetch_k=top_p,
                      k=top_k * 4
                  )

                  # 按科室过滤MMR结果
                  new_documents = [document for document in mmr_results
                                   if str(document.metadata.get("panel_name", "")) == str(clinical_context.department)]

                  # 补充文档逻辑
                  if len(new_documents) < top_p:
                      logger.info(f"过滤后文档数量 {len(new_documents)} 不足 {top_p}，开始补充文档")

                      other_documents = [document for document in mmr_results
                                         if
                                         str(document.metadata.get("panel_name", "")) != str(
                                             clinical_context.department)]

                      need_supplement_count = top_p - len(new_documents)
                      supplement_documents = other_documents[:need_supplement_count]
                      new_documents.extend(supplement_documents)
                      logger.info(f"补充了 {len(supplement_documents)} 个文档，现在共有 {len(new_documents)} 个文档")

                  # 如果经过过滤和补充后 new_documents 仍然为空，则使用原始 documents
                  if not new_documents:
                      logger.warning("过滤后无文档，使用原始查询结果")
                      new_documents = mmr_results

                  return new_documents

              async def execute_hybrid_search():
                  """执行混合搜索"""
                  # 构建混合搜索请求
                  search_param_1 = {
                      "data": [query_embedding],
                      "anns_field": "text_dense",
                      "param": {"nprobe": 10},
                      "limit": top_k * 2
                  }
                  request_1 = AnnSearchRequest(**search_param_1)

                  search_param_2 = {
                      "data": [standardized_query],
                      "anns_field": "text_sparse",
                      "param": {"drop_ratio_search": 0.2},
                      "limit": top_k * 2
                  }
                  request_2 = AnnSearchRequest(**search_param_2)
                  reqs = [request_1, request_2]

                  ranker = Function(
                      name="rrf",
                      input_field_names=[],
                      function_type=FunctionType.RERANK,
                      params={
                          "reranker": "rrf",
                          "k": 100
                      }
                  )

                  hybrid_results = await aclient.hybrid_search(
                      collection_name="scenarios",
                      reqs=reqs,
                      ranker=ranker,
                      limit=top_k,
                      output_fields=["panel_name", "topic_name", "text", "id"]
                  )

                  return hybrid_results

              # 并发执行两个搜索任务
              mmr_task = execute_mmr_search()
              hybrid_task = execute_hybrid_search()

              new_documents, hybrid_results = await asyncio.gather(mmr_task, hybrid_task)

              # 3. 处理混合搜索结果
              hybrid_hits = []
              not_existed_hybrid_hits = []

              if hybrid_results:
                  for hits in hybrid_results:
                      for hit in hits:
                          if hasattr(hit, 'distance') and hit["panel_name"] == clinical_context.department:
                              hybrid_hits.append({
                                  "id": int(hit.id),
                                  "distance": hit.distance,
                                  "entity": hit.entity
                              })
                          else:
                              not_existed_hybrid_hits.append({
                                  "id": int(hit.id),
                                  "distance": hit.distance,
                                  "entity": hit.entity
                              })

              # 补充混合搜索结果
              need_supply = top_k - len(hybrid_hits)
              hybrid_hits.extend(not_existed_hybrid_hits[:need_supply])

              # 4. 合并结果并去重
              # 从MMR结果中提取ID
              mmr_ids = set()
              for doc in new_documents:
                  try:
                      doc_id = int(doc.metadata.get("id"))  # 确保ID是整数
                      mmr_ids.add(doc_id)
                  except (ValueError, AttributeError) as e:
                      logger.warning(f"无效的MMR文档ID: {doc.id}, 错误: {e}")
                      continue

              # 从混合搜索结果中提取ID（已经按科室过滤）
              hybrid_ids = {hit["id"] for hit in hybrid_hits}

              # 合并所有唯一ID
              all_scenario_ids = mmr_ids.union(hybrid_ids)

              if not all_scenario_ids:
                  logger.warning("没有找到匹配的候选场景")
                  return []

              # 5. 批量查询scenario对象
              session = await self._get_independent_session()
              try:
                  statement = (
                      select(ClinicalScenario)
                      .options(
                          selectinload(ClinicalScenario.topic),
                          selectinload(ClinicalScenario.panel)
                      )
                      .where(ClinicalScenario.id.in_(list(all_scenario_ids))))
                  result = await session.exec(statement)
                  scenarios = result.all()
                  logger.info(f"批量查询到 {len(scenarios)} 个scenario对象")
              finally:
                  await session.close()

              # 6. 构建候选结果并计算分数
              id_to_scenario = {scenario.id: scenario for scenario in scenarios}

              # 创建距离到分数的映射（混合搜索）
              hybrid_scores = {}
              for hit in hybrid_hits:
                  # 将距离转换为相似度分数（距离越小，相似度越高）
                  similarity_score = max(0.0, 1.0 - hit["distance"])
                  hybrid_scores[hit["id"]] = similarity_score

              candidates = []

              # 处理MMR结果
              for doc in new_documents:
                  try:
                      doc_id = int(doc.metadata.get("id", 0))
                      scenario = id_to_scenario.get(doc_id)
                      if not scenario:
                          continue

                      # 优先使用混合搜索的分数，如果没有则使用默认值
                      if doc_id in hybrid_scores:
                          mmr_score = hybrid_scores[doc_id]
                      else:
                          # 对于只有MMR的结果，使用较高的默认分数
                          mmr_score = random.uniform(0.9, 0.95)

                      if mmr_score >= similarity_threshold:
                          candidates.append({
                              'scenario': scenario,
                              'scenario_id': scenario.id,
                              'score': mmr_score,
                              'document_content': doc.page_content,
                              'source': 'hybrid'
                          })
                  except (ValueError, AttributeError) as e:
                      logger.warning(f"处理MMR文档失败: {e}")
                      continue

              # 7. 按分数排序并返回top_k
              candidates.sort(key=lambda x: x['score'], reverse=True)
              final_candidates = candidates[:top_k]

              logger.info(f"最终返回 {len(final_candidates)} 个候选场景")
              return final_candidates

          except Exception as e:
              logger.error(f"向量搜索失败: {e}")
              return []


