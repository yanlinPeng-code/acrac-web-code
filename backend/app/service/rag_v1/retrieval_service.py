"""
临床场景检索服务
实现四阶段混合检索策略：
1. 结构化筛选（年龄/性别等硬性条件）
2. 向量语义检索（主诉+病史+诊断）
3. 关键词匹配检索
4. 规则引擎过滤（禁忌症/特殊考虑）
5. 推荐排序（appropriateness_rating）
"""
import asyncio
import datetime
import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Coroutine
import copy

from pymilvus import AnnSearchRequest, Function, FunctionType
from sqlalchemy.orm import selectinload
from sqlmodel import select, and_, or_
from sqlalchemy import func, cast, text
from sqlmodel.ext.asyncio.session import AsyncSession
from app.config.redis_config import redis_manager
from app.core.language_model.model_client_wrapper import EmbeddingClientSDK
from app.core.language_model.providers.siliconflow.embedding import Embedding
from app.model.acrac_models import ClinicalScenario, ClinicalRecommendation, ProcedureDictionary
from app.schema.IntelligentRecommendation_schemas import (RerankingStrategy, PatientInfo, ClinicalContext,
                                                          SearchStrategy
                                                          )
from app.service.rag_v1.adaptive_recommend_service import LearningThresholdStrategy, AdaptiveRecommendationEngineService
# 导入AI服务（查询标准化）
from app.service.rag_v1.ai_service import AiService
from app.service.rag_v1.vector_database_service import VectorDatabaseService
from app.config.database import async_db_manager
from app.utils.helper.helper import assemble_database_results
from app.utils.logger.simple_logger import get_logger
from app.celery.tasks.dict_update_tasks import batch_persist_by_category, batch_persist_by_category_async

logger = get_logger(__name__)




class RetrievalService:
    """临床场景检索服务
    
    高并发优化：为每个并发检索方法创建独立的session，避免事务冲突
    """
    
    def __init__(self,
                 session: AsyncSession,
                 ai_service: AiService,
                 vector_service:VectorDatabaseService,
                 ):
        """
        初始化检索服务
        
        Args:
            session: 数据库会话（主要用于非并发场景）
        """
        self.session = session

        
        # 初始化AI服务（使用requests调用API）
        self.ai_service =ai_service
        self.vector_service = vector_service
        self.redis_client=redis_manager.async_client
        self.adaptive_recommendation_engine_service= AdaptiveRecommendationEngineService(environment="production")

        # 性别映射
        self.gender_mapping = {
            '男性': [
                '男', '男性', '男人', '男士', '男患者', '男童', '男孩', '男生', '男婴', '男青年',
                '男子', '男病人', '男科', '雄性', '公', '雄', 'male', 'm', 'man', 'boy', 'gentleman'
            ],
            '女性': [
                '女', '女性', '女人', '女士', '女患者', '女童', '女孩', '女生', '女婴', '女青年',
                '女子', '女病人', '妇科', '雌性', '母', '雌', 'female', 'f', 'woman', 'girl', 'lady'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', '男女', '男女均可', '男女皆可',
                'any', 'all', 'both', 'either', '通用', 'common', 'general',"成人","成年人"
            ]
        }

        # 妊娠状态映射
        self.pregnancy_mapping = {
            '妊娠期': [
                '妊娠', '怀孕', '孕妇', '孕期', '妊娠期', '孕产妇', '孕产期', '孕周', '孕早期',
                '孕中期', '孕晚期', '早孕', '中孕', '晚孕', '怀孕期', 'pregnancy', 'pregnant',
                'gestation', 'gestational', 'prenatal', 'antenatal'
            ],
            '非妊娠期': [
                '非妊娠', '非孕妇', '未怀孕', '未妊娠', '非孕期', '未孕', '非孕', 'non-pregnancy',
                'not pregnant', 'non-pregnant', 'non-gestational'
            ],
            '哺乳期': [
                '哺乳', '哺乳期', '母乳喂养', '母乳', '哺乳期妇女', '哺乳母亲', 'lactation',
                'breastfeeding', 'nursing', 'lactating'
            ],
            '备孕期': [
                '备孕', '备孕期', '计划怀孕', '准备怀孕', 'preconception', 'trying to conceive',
                'fertility', 'pre-pregnancy'
            ],
            '产后': [
                '产后', '分娩后', '生产后', 'postpartum', 'postnatal', 'after delivery',
                'puerperium', 'post-partum'
            ],
            '不孕': [
                '不孕', '不孕症', '不育', '不育症', 'infertility', 'infertile', 'sterility'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', 'any', 'all', 'both', 'either',
                '通用', 'common', 'general'
            ]
        }

        # 年龄组映射
        self.age_group_mapping = {
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'pediatric', 'children'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager'],
            '成人': ['成人', '成年人', 'adult'],
            '老年': ['老年', '老年人', '老人', 'elderly', 'geriatric', 'senior'],
            '不限': ['不限', '通用', 'all', 'both', 'any', '均可']
        }

        # 科室别名映射
        self.department_mapping = {
            '心内科': ['心血管内科', '心脏内科', ' Cardiology', 'cardiology'],
            '消化科': ['消化内科', ' Gastroenterology', 'gastroenterology'],
            '神经科': ['神经内科', ' Neurology', 'neurology'],
            '骨科': ['骨科', ' Orthopedics', 'orthopedics'],
            '儿科': ['小儿科', ' Pediatrics', 'pediatrics'],
            '妇产科': ['妇科', '产科', ' Obstetrics', 'Gynecology', 'obstetrics', 'gynecology'],
            '急诊科': ['急诊', ' Emergency', 'emergency'],
            '肿瘤科': ['肿瘤内科', ' Oncology', 'oncology']
        }

        # 紧急程度映射
        self.urgency_mapping = {
            '紧急': ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute'],
            '中度': ['中度', '中等', 'moderate', 'serious'],
            '常规': ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine'],
            '复发性': ['复发性', '复发', '反复', 'recurrent', 'relapse'],
            '亚急性': ['亚急性', 'subacute'],
            '重度': ['重度', '严重', 'severe'],
            '轻微': ['轻微', '轻度', 'mild', 'minor'],
            '稳定': ['稳定', 'stable'],
            '不稳定': ['不稳定', 'unstable'],
            '危及生命': ['危及生命', '生命危险', 'life-threatening', 'critical condition'],
            '择期': ['择期', 'elective'],
            '预防性': ['预防性', '预防', 'preventive', 'prophylactic'],
            '筛查': ['筛查', 'screening'],
            '随访': ['随访', 'follow-up'],
            '康复': ['康复', '康复期', 'rehabilitation', 'recovery'],
            '终末期': ['终末期', '晚期', '末期', 'end-stage', 'terminal'],
            '姑息治疗': ['姑息治疗', '姑息', 'palliative'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }
    
    async def _get_independent_session(self) -> AsyncSession:
        """
        为并发检索创建独立的session
        
        高并发优化：每个检索方法使用独立的session，避免事务冲突
        从连接池中获取连接，自动管理生命周期
        """
        return async_db_manager.async_session_factory()


    async def retrieve_clinical_scenarios(
        self,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        search_strategy: Optional[SearchStrategy] = None,
        need_optimize_query:Optional[bool]=False,
        top_k: int = 16,
        similarity_threshold: float = 0.6,  # 相似度阈值
        # reranker_model: Optional[RerankerClientSDK] = None,
        # embedding_model: Optional[EmbeddingClientSDK] = None,
        medical_dict: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        新的混合检索流程（2025-10优化版）：
        1. LLM查询标准化（转换为ACR标准格式）
        2. 并行检索：
           2a. jieba分词 + 模糊匹配检索 -> top_p -> 重叠度评分 -> top_k
           2b. 语义向量检索 -> top_p -> 相似度评分(>0.6) -> top_k
        3. 合并去重，混合打分（jieba 30% + 语义 70%）
        4. 排序返回
        
        Args:
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            search_strategy: 检索策略配置
            top_k: 返回的场景数量
            similarity_threshold: 相似度阈值
        
        Returns:
            排序后的临床场景列表，每个场景包含匹配分数
        """
        start_time = time.time()
        # 使用默认策略
        if search_strategy is None:
            search_strategy = SearchStrategy()
        
        # ========== 阶段1: LLM查询标准化（带缓存） ==========
        logger.info("开始查询标准化...")
        
        # 生成缓存键（基于患者信息和临床上下文）
        cache_key = await self._generate_cache_key(patient_info, clinical_context)
        
        # 尝试从Redis获取缓存的标准化查询
        cached_query = await self._get_cached_standardized_query(cache_key)
        
        if cached_query:
            logger.info(f"从缓存获取标准化查询: {cached_query}")
            standardized_query = cached_query
        else:
            # if need_optimize_query:
            #     # 缓存未命中，调用LLM进行标准化
            #     logger.info("缓存未命中，调用LLM进行查询标准化...")
            #     standardized_query = await self.ai_service.standardize_query(
            #         patient_info,
            #         clinical_context
            #     )
            #     logger.info(f"标准化后的查询: {standardized_query}")
            #
            #     # 将标准化结果存入缓存
            #     await self._cache_standardized_query(cache_key, standardized_query)
            #     logger.info("已将标准化查询存入缓存")
            # else:
            if patient_info.gender in self.gender_mapping["男性"] :
                standardized_query=f"{patient_info.age}岁,{patient_info.gender},{clinical_context.chief_complaint}"
            else:
                standardized_query=f"{patient_info.age}岁,{patient_info.gender},{patient_info.pregnancy_status},{clinical_context.chief_complaint}"
        # ========== 阶段2: 并行检索（使用asyncio.gather） ==========
        top_p = top_k   # 中间候选集大小
        
        logger.info("开始并行检索（jieba + 语义）...")
        # jieba_candidates=await self._jieba_fuzzy_search(
        #          standardized_query,
        #          medical_dict,
        #          top_p=top_p,
        #          top_k=top_k
        #      )
        # semantic_candidates=await  self._semantic_vector_search(
        #                 standardized_query,
        #                 patient_info,
        #                 clinical_context,
        #                 # embedding_model,
        #                 top_p=top_p,
        #                 top_k=top_k,
        #                 similarity_threshold=similarity_threshold
        #             )
        # vector_candidates=await self._vector_mmr_search(
        #                 standardized_query,
        #                 clinical_context,
        #                 # embedding_model,
        #                 top_p=top_p,
        #                 top_k=top_k,
        #                 similarity_threshold=similarity_threshold
        #             )
        # # # 使用asyncio.gather实现真正的并行执行
        jieba_candidates, semantic_candidates, vector_candidates = await asyncio.gather(
            # 2a. jieba分词 + 模糊匹配检索
            self._jieba_fuzzy_search(
                standardized_query,
                medical_dict,
                top_p=top_p,
                top_k=top_k
            ),
            # 2b. 语义向量检索
            self._semantic_vector_search(
                standardized_query,
                patient_info,
                clinical_context,
                # embedding_model,
                top_p=top_p,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            ),
            #3.基于langchain封装的vector_store作最大边沿检索
            self._vector_mmr_search(
                standardized_query,
                clinical_context,
                # embedding_model,
                top_p=top_p,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            ),
            return_exceptions=True  # 捕获异常，避免一个失败导致全部失败
        )

        # 处理可能的异常
        if isinstance(jieba_candidates, Exception):
            logger.error(f"jieba检索失败: {jieba_candidates}")
            jieba_candidates = []
        else:
            logger.info(f"jieba检索返回 {len(jieba_candidates)} 条结果")
        
        if isinstance(semantic_candidates, Exception):
            logger.error(f"语义检索失败: {semantic_candidates}")
            semantic_candidates = []
        else:
            logger.info(f"语义检索返回 {len(semantic_candidates)} 条结果")
        
        if isinstance(vector_candidates, Exception):
            logger.error(f"MMR检索失败: {vector_candidates}")
            vector_candidates = []
        else:
            logger.info(f"MMR检索返回 {len(vector_candidates)} 条结果")
        
        # ========== 阶段3: 合并去重与混合打分 ==========
        # 如果所有检索都失败，直接返回空结果
        if not jieba_candidates and not semantic_candidates and not vector_candidates:
            logger.warning("所有检索方法都未返回结果")
            return []
        
        logger.info("开始合并去重与混合打分...")
        
        # 使用新的权重配置：jieba:semantic:mmr = 3:5:2
        merged_results =self._merge_and_score_v3(
            search_strategy,
            jieba_candidates,
            semantic_candidates,
            vector_candidates,  # 添加MMR结果
            target_count=top_k
        )
        logger.info(f"合并后共 {len(merged_results)} 条结果（已去重）")
        
        # ========== 阶段4: 排序并返回top_k ==========
        merged_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        # 过滤低于阈值的结果
        filtered_results = [
            s for s in merged_results 
            if s.get('final_score', 0) >= similarity_threshold
        ]
        
        logger.info(f"过滤后剩余 {len(filtered_results)} 条结果，返回top_{top_k}")
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"第一阶段处理时间：{processing_time_ms}")
        return filtered_results[:top_k]

   
    async def _jieba_fuzzy_search(
            self,
            query_text: str,
            medical_dict: Optional[List] = None,
            top_p: int = 50,
            top_k: int = 10
    ) -> list[Any] | list[Exception]:
        """
        jieba分词 + 模糊匹配检索（高并发优化：使用独立 session）
        """
        #暂时不使用
        return []
        # 1. 使用混合分词（jieba + LLM并发验证）
        keywords, new_terms = await self._hybrid_tokenize_with_llm_verification(query_text, medical_dict)
        logger.info(f"🔍 混合分词提取到 {len(keywords)} 个关键词: {keywords[:10]}")
        if new_terms:
            logger.info(f"✨ 本次新发现 {len(new_terms)} 个医学术语: {new_terms}")
            logger.info(f"✅ 这些新词已动态添加到jieba内置词典，后续分词会自动使用")

        if not keywords:
            logger.warning("jieba分词未提取到关键词，返回空结果")
            return []

        # 2. 构建SQL模糊匹配条件（使用LIKE）
        top_keywords = keywords
        like_conditions = [
            ClinicalScenario.description_zh.contains(keyword)
            for keyword in top_keywords
        ]

        # 3. 高并发优化：使用独立 session 执行模糊匹配查询
        session = await self._get_independent_session()
        try:
            statement = (
                select(ClinicalScenario)
                .options(
                    selectinload(ClinicalScenario.panel),
                    selectinload(ClinicalScenario.topic)
                )
                .where(
                    and_(
                        ClinicalScenario.is_active == True,
                        or_(*like_conditions)
                    )
                )
                .limit(top_p)
            )

            result = await session.exec(statement)
            scenarios = result.all()
            logger.info(f"模糊匹配检索到 {len(scenarios)} 条场景")
        except Exception as e:
            logger.error(f"数据库查询失败: {e}")
            return []
        finally:
            await session.close()

        if not scenarios:
            return []

        # 4. 计算每个场景的jieba分词重叠度得分
        query_keywords_set = set(keywords)
        candidates_with_scores = []

        for scenario in scenarios:
            scenario_keywords = set(self._jieba_tokenize(
                scenario.description_zh or "",
                medical_dict,
                new_terms
            ))

            overlap = query_keywords_set.intersection(scenario_keywords)
            union = query_keywords_set.union(scenario_keywords)

            if len(union) > 0:
                jieba_score = len(overlap) / len(union)
            else:
                jieba_score = 0.0

            candidates_with_scores.append({
                'scenario': scenario,
                'scenario_id': scenario.id,
                'score': jieba_score,
                'matched_keywords': list(overlap),
                'source':"jieba"
            })

        logger.info(f"✅ 分词评分完成，共 {len(candidates_with_scores)} 个结果")

        # 5. 检查是否需要归一化并处理
        if candidates_with_scores:
            max_score = max(candidate['jieba_score'] for candidate in candidates_with_scores)
            logger.info(f"📊 归一化前最大分数: {max_score:.4f}")

            if max_score < 0.7:
                logger.info("📈 最大分数低于0.7，进行非线性归一化处理")
                candidates_with_scores = self._normalize_scores_nonlinear(candidates_with_scores,
                                                                          method="power"
                                                                          )
            else:
                logger.info("✅ 最大分数达到0.7，保持原始分数")

        # 6. 按jieba_score排序
        candidates_with_scores.sort(key=lambda x: x['jieba_score'], reverse=True)
        logger.info(f"📊 排序后前3名分数: {[r['jieba_score'] for r in candidates_with_scores[:3]]}")

        # 7. 返回top_k
        final_results = candidates_with_scores[:top_k]
        logger.info(f"✅ 返回 {len(final_results)} 条jieba检索结果")
        return final_results

    def _normalize_scores_nonlinear(self, candidates: List[Dict], method: str = "sigmoid") -> List[Dict]:
        """
        非线性归一化分数到0.5~0.95范围

        Args:
            candidates: 包含jieba_score的候选列表
            method: 归一化方法，可选 "sigmoid", "power", "log", "exponential"

        Returns:
            归一化后的候选列表
        """

        if not candidates:
            return candidates

        # 提取原始分数
        scores = [candidate['jieba_score'] for candidate in candidates]
        min_score = min(scores)
        max_score = max(scores)

        logger.info(f"📈 {method}归一化前分数范围: [{min_score:.4f}, {max_score:.4f}]")

        # 如果所有分数相同，直接设置到中间值
        if abs(max_score - min_score) < 1e-6:
            for candidate in candidates:
                candidate['jieba_score'] = 0.8
            logger.info("📊 所有分数相同，设置为中间值0.725")
            return candidates

        for candidate in candidates:
            # 先线性归一化到0-1范围
            x = (candidate['jieba_score'] - min_score) / (max_score - min_score)

            if method == "sigmoid":
                # Sigmoid函数归一化 - 强化中间区域
                normalized_score = self._sigmoid_normalize(x)
            elif method == "power":
                # 幂函数归一化 - 可以强化高分或低分区域
                normalized_score = self._power_normalize(x, power=0.6)
            elif method == "log":
                # 对数归一化 - 压缩高分区域，拉伸低分区域
                normalized_score = self._log_normalize(x)
            elif method == "exponential":
                # 指数归一化 - 拉伸高分区域，压缩低分区域
                normalized_score = self._exponential_normalize(x)
            elif method == "tanh":
                # 双曲正切归一化 - 温和的非线性
                normalized_score = self._tanh_normalize(x)
            else:
                # 默认使用线性归一化
                normalized_score = 0.5 + 0.45 * x

            candidate['jieba_score'] = normalized_score

        # 验证归一化结果
        normalized_scores = [candidate['jieba_score'] for candidate in candidates]
        logger.info(f"📈 {method}归一化后分数范围: [{min(normalized_scores):.4f}, {max(normalized_scores):.4f}]")

        return candidates

    def _sigmoid_normalize(self, x: float) -> float:
        """Sigmoid函数归一化 - 强化中间区域"""
        # 将输入调整到更适合sigmoid的范围
        x_scaled = (x - 0.5) * 6  # 调整缩放因子来控制曲线陡峭程度
        sigmoid = 1 / (1 + math.exp(-x_scaled))
        # 映射到0.5-0.95范围
        return 0.5 + 0.45 * sigmoid

    def _power_normalize(self, x: float, power: float = 0.7) -> float:
        """幂函数归一化 - power<1强化高分，power>1强化低分"""
        powered = x ** power
        return 0.5 + 0.45 * powered

    def _log_normalize(self, x: float) -> float:
        """对数归一化 - 压缩高分区域"""
        # 避免log(0)
        if x < 0.001:
            x = 0.001
        log_norm = math.log(x + 1) / math.log(2)  # log2(x+1) 归一化到0-1
        return 0.5 + 0.45 * log_norm

    def _exponential_normalize(self, x: float) -> float:
        """指数归一化 - 拉伸高分区域"""
        exp_norm = (math.exp(x) - 1) / (math.e - 1)
        return 0.5 + 0.45 * exp_norm

    def _tanh_normalize(self, x: float) -> float:
        """双曲正切归一化 - 温和的非线性"""
        x_scaled = (x - 0.5) * 3  # 调整缩放因子
        tanh_norm = (math.tanh(x_scaled) + 1) / 2
        return 0.5 + 0.45 * tanh_norm
    def _normalize_scores_by_linear(self, candidates: List[Dict]) -> List[Dict]:
        """
        归一化分数到0.5~0.95范围

        Args:
            candidates: 包含jieba_score的候选列表

        Returns:
            归一化后的候选列表
        """
        if not candidates:
            return candidates

        # 提取原始分数
        scores = [candidate['jieba_score'] for candidate in candidates]
        min_score = min(scores)
        max_score = max(scores)

        logger.info(f"📈 归一化前分数范围: [{min_score:.4f}, {max_score:.4f}]")

        # 如果所有分数相同，直接设置到中间值
        if abs(max_score - min_score) < 1e-6:
            for candidate in candidates:
                candidate['jieba_score'] = 0.725  # 0.5~0.95的中间值
            logger.info("📊 所有分数相同，设置为中间值0.725")
            return candidates

        # 线性归一化到0.5~0.95范围
        # 公式: normalized = 0.5 + 0.45 * (原始分数 - 最小值) / (最大值 - 最小值)
        for candidate in candidates:
            normalized_score = 0.5 + 0.45 * (candidate['jieba_score'] - min_score) / (max_score - min_score)
            candidate['jieba_score'] = normalized_score

        # 验证归一化结果
        normalized_scores = [candidate['jieba_score'] for candidate in candidates]
        logger.info(f"📈 归一化后分数范围: [{min(normalized_scores):.4f}, {max(normalized_scores):.4f}]")

        return candidates
    
    async def _semantic_vector_search(
        self,
        query_text: str,
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        # embedding_model: EmbeddingClientSDK,
        top_p: int = 50,
        top_k: int = 10,
        similarity_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
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
                    'source':"semantic"
                    # 保存原始文档内容
                })

        # 按相似度分数排序并返回前top_k个结果
        candidates_sorted = sorted(candidates, key=lambda x: x['score'], reverse=True)
        return candidates_sorted[:top_k]






































    def _merge_and_score_v3(
            self,
            search_strategy: SearchStrategy,
            jieba_candidates: List[Dict[str, Any]],
            semantic_candidates: List[Dict[str, Any]],
            mmr_candidates: List[Dict[str, Any]] = None,
            target_count: int = 16
    ) -> List[Dict[str, Any]]:
        """
        Fine-grained hierarchical merging strategy

        Strategy:
        1. First level: All three methods match (all retained)
        2. Second Level: Two methods match (using different weights based on combination type)
        3. Third Level: Single method match (average allocation of slots based on category)

        Return Logic:
        - All of the first level are retained
        - Ranked by weighted score at level 2
        - If the total is less than target_count, supplement from level 3
        - Level 3 allocates spots with priority semantic>mmr>jieba

        Args:
            jieba_candidates: jieba search results
            semantic_candidates: semantic search results
            mmr_candidates: MMR search results
            target_count: target return count (default 16)

        Returns:
            The merged result list
        """
        if mmr_candidates is None:
            mmr_candidates = []
        if jieba_candidates is None:
            jieba_candidates = []
        if semantic_candidates is None:
            semantic_candidates = []

        # Build ID to candidate mapping
        jieba_dict = {item['scenario_id']: item for item in jieba_candidates}
        semantic_dict = {item['scenario_id']: item for item in semantic_candidates}
        mmr_dict = {item['scenario_id']: item for item in mmr_candidates}

        all_ids = set(jieba_dict.keys()) | set(semantic_dict.keys()) | set(mmr_dict.keys())

        # Hierarchical processing
        level_1 = []  # Matched by all three methods
        level_2_js = []  # jieba + semantic
        level_2_jm = []  # jieba + mmr
        level_2_ms = []  # mmr + semantic
        level_3_j = []  # only jieba
        level_3_s = []  # Only semantic
        level_3_m = []  # Only mmr

        for scenario_id in all_ids:
            sources = []
            if scenario_id in jieba_dict:
                sources.append('jieba')
            if scenario_id in semantic_dict:
                sources.append('semantic')
            if scenario_id in mmr_dict:
                sources.append('mmr')

            # Building merged data with unified field names
            merged_data = {
                'scenario_id': scenario_id,
                'scenario': None,
                'jieba_score': 0.0,
                'semantic_score': 0.0,
                'mmr_score': 0.0,
                'document_content': '',
                'matched_keywords': [],
                'source': 'merged'
            }

            # Merge data from all available sources
            if scenario_id in jieba_dict:
                jieba_item = jieba_dict[scenario_id]
                merged_data['jieba_score'] = jieba_item['score']
                merged_data['scenario'] = jieba_item['scenario']
                if 'matched_keywords' in jieba_item:
                    merged_data['matched_keywords'] = jieba_item['matched_keywords']

            if scenario_id in semantic_dict:
                semantic_item = semantic_dict[scenario_id]
                merged_data['semantic_score'] = semantic_item['score']
                merged_data['scenario'] = semantic_item['scenario']
                if 'document_content' in semantic_item:
                    merged_data['document_content'] = semantic_item['document_content']

            if scenario_id in mmr_dict:
                mmr_item = mmr_dict[scenario_id]
                merged_data['mmr_score'] = mmr_item['score']
                merged_data['scenario'] = mmr_item['scenario']
                if 'document_content' in mmr_item and not merged_data['document_content']:
                    merged_data['document_content'] = mmr_item['document_content']

            # Categorize based on the number of matching methods
            if len(sources) == 3:
                # Level 1: All three methods match, use fixed weights
                jieba_score_standard = search_strategy.keyword_weight * merged_data[
                    'jieba_score'] if search_strategy.keyword_weight else 0.2 * merged_data['jieba_score']
                semantic_score_standard = search_strategy.vector_weight * merged_data[
                    'semantic_score'] if search_strategy.vector_weight else 0.5 * merged_data['semantic_score']
                mmr_score_standard = search_strategy.diversity_weight * merged_data[
                    'mmr_score'] if search_strategy.diversity_weight else 0.3 * merged_data['mmr_score']

                final_score = (
                        jieba_score_standard +
                        semantic_score_standard +
                        mmr_score_standard
                )
                merged_data['final_score'] = final_score
                merged_data['match_level'] = 1
                level_1.append(merged_data)

            elif len(sources) == 2:
                # Second level: Two methods match, use different weights based on different combinations
                if 'jieba' in sources and 'semantic' in sources:
                    final_score = (
                            0.4 * merged_data['jieba_score'] +
                            0.6 * merged_data['semantic_score']
                    )
                    merged_data['final_score'] = final_score
                    merged_data['match_level'] = 2
                    merged_data['combo_type'] = 'jieba+semantic'
                    level_2_js.append(merged_data)

                elif 'jieba' in sources and 'mmr' in sources:
                    final_score = (
                            0.4 * merged_data['jieba_score'] +
                            0.6 * merged_data['mmr_score']
                    )
                    merged_data['final_score'] = final_score
                    merged_data['match_level'] = 2
                    merged_data['combo_type'] = 'jieba+mmr'
                    level_2_jm.append(merged_data)

                elif 'mmr' in sources and 'semantic' in sources:
                    final_score = (
                            0.5 * merged_data['mmr_score'] +
                            0.5 * merged_data['semantic_score']
                    )
                    merged_data['final_score'] = final_score
                    merged_data['match_level'] = 2
                    merged_data['combo_type'] = 'mmr+semantic'
                    level_2_ms.append(merged_data)

            else:
                # Third level: Single method matching
                merged_data['match_level'] = 3
                if 'jieba' in sources:
                    merged_data['final_score'] = merged_data['jieba_score']
                    merged_data['combo_type'] = 'jieba_only'
                    level_3_j.append(merged_data)
                elif 'semantic' in sources:
                    merged_data['final_score'] = merged_data['semantic_score']
                    merged_data['combo_type'] = 'semantic_only'
                    level_3_s.append(merged_data)
                else:  # 'mmr'
                    merged_data['final_score'] = merged_data['mmr_score']
                    merged_data['combo_type'] = 'mmr_only'
                    level_3_m.append(merged_data)

        # Sorting within levels
        level_1.sort(key=lambda x: x['final_score'], reverse=True)
        level_2_js.sort(key=lambda x: x['final_score'], reverse=True)
        level_2_jm.sort(key=lambda x: x['final_score'], reverse=True)
        level_2_ms.sort(key=lambda x: x['final_score'], reverse=True)
        level_3_j.sort(key=lambda x: x['final_score'], reverse=True)
        level_3_s.sort(key=lambda x: x['final_score'], reverse=True)
        level_3_m.sort(key=lambda x: x['final_score'], reverse=True)

        # Merge Level 2
        level_2_all = level_2_js + level_2_jm + level_2_ms
        level_2_all.sort(key=lambda x: x['final_score'], reverse=True)

        # Statistics Information
        logger.info(
            f"Tiered statistics: First tier ({len(level_1)}), Second tier(js:{len(level_2_js)}, jm:{len(level_2_jm)}, ms:{len(level_2_ms)}), "
            f"Level 3 (j:{len(level_3_j)}, s:{len(level_3_s)}, m:{len(level_3_m)})"
        )

        # Execute return strategy
        return self._level_based_selection(
            level_1, level_2_all, level_3_j, level_3_s, level_3_m, target_count
        )

    def _level_based_selection(
            self, level_1, level_2, level_3_j, level_3_s, level_3_m, target_count
    ):
        """
        Tiered selection strategy
        """
        results = []

        # First tier: Keep all
        results.extend(level_1)
        logger.info(f"First level selected {len(level_1)} results")

        # If the first level already meets the requirements, return directly
        if len(results) >= target_count:
            logger.info(f"First-level results have met the target count {target_count}, returning directly")
            return results[:target_count]

        # Second level: Add all (already sorted by score)
        results.extend(level_2)
        logger.info(f"Selected {len(level_2)} results at level 2")

        # If level 1 + level 2 already meet the requirement, return
        current_count = len(results)
        if current_count >= target_count:
            logger.info(
                f"First level + second level results have met the target count {target_count}, returning directly")
            return results[:target_count]

        # Third level: Number of items needed to supplement
        needed_from_level_3 = target_count - current_count
        logger.info(f"Need to supplement {needed_from_level_3} results from level 3")

        # Level 3 allocation strategy
        level_3_selected = self._select_from_level_3(
            level_3_j, level_3_s, level_3_m, needed_from_level_3
        )
        results.extend(level_3_selected)

        # Final statistics
        final_count = len(results)
        level_1_count = len(level_1)
        level_2_count = len(level_2)
        level_3_count = len(level_3_selected)

        logger.info(
            f"Final result distribution: Level 1 ({level_1_count}), Level 2 ({level_2_count}), "
            f"Level 3 ({level_3_count}), Total ({final_count})"
        )

        return results[:target_count]

    def _select_from_level_3(self, level_3_j, level_3_s, level_3_m, needed_count):
        """
        Selection from Level 3 Results - Improved Round-Robin Selection Strategy

        Strategy:
        1. Select in a rotating loop according to the priority order of semantic -> mmr -> jieba
        2. In each loop, select the result with the highest score from the current category
        3. Until the required number is reached or all categories are exhausted
        """
        if needed_count <= 0:
            return []

        selected = []

        # Create copies of each category to avoid modifying the original data
        j_list = level_3_j.copy()
        s_list = level_3_s.copy()
        m_list = level_3_m.copy()

        # Priority order: semantic -> mmr -> jieba
        priority_order = [
            ('semantic', s_list),
            ('mmr', m_list),
            ('jieba', j_list)
        ]

        # Select in a loop until the required count is met or all lists are empty
        while needed_count > 0 and any(lst for _, lst in priority_order):
            # Take the first item (with the highest score) from each non-empty list in turn according to priority order
            for source_type, source_list in priority_order:
                if needed_count <= 0:
                    break

                if source_list:  # If there are still candidates in the current category
                    # Select the candidate with the highest score in the current category
                    candidate = source_list.pop(0)
                    selected.append(candidate)
                    needed_count -= 1

                    logger.debug(
                        f"Selecting from {source_type}: {candidate['scenario_id']} (score: {candidate['final_score']:.4f})"
                    )

        # Record the final assignment
        final_j_count = len(level_3_j) - len(j_list)
        final_s_count = len(level_3_s) - len(s_list)
        final_m_count = len(level_3_m) - len(m_list)

        logger.info(
            f"Third-level loop assignment completed: semantic({final_s_count}), mmr({final_m_count}), jieba({final_j_count}), "
            f"Total ({len(selected)})"
        )

        return selected



    def _build_merged_data(self, scenario_id, jieba_dict, semantic_dict, mmr_dict):
        """构建合并数据"""
        data = {
            'scenario_id': scenario_id,
            'jieba_score': 0,
            'semantic_score': 0,
            'mmr_score': 0,
            'matched_keywords': [],
            'sources': []
        }

        # 合并jieba数据
        if scenario_id in jieba_dict:
            item = jieba_dict[scenario_id]
            data['scenario'] = item['scenario']
            data['jieba_score'] = item.get('score', 0)
            data['matched_keywords'] = item.get('matched_keywords', [])
            data['sources'].append('jieba')

        # 合并语义数据
        if scenario_id in semantic_dict:
            item = semantic_dict[scenario_id]
            data['scenario'] = item['scenario']  # 会覆盖，但scenario应该相同
            data['semantic_score'] = item.get('score', 0)
            data['sources'].append('semantic')

        # 合并MMR数据
        if scenario_id in mmr_dict:
            item = mmr_dict[scenario_id]
            data['scenario'] = item['scenario']  # 会覆盖，但scenario应该相同
            data['mmr_score'] = item.get('score', 0)
            data['sources'].append('mmr')
            if 'document_content' in item:
                data['document_content'] = item['document_content']

        return data

    def _select_by_level_strategy(self, level_1, level_2, level_3_jieba, level_3_semantic, level_3_mmr, max_results=15):
        """
        分级返回策略：
        1. 第一级全部保留
        2. 第二级取前6个（不足则全取）
        3. 剩余名额分配给第三级，各方法分别取前4个
        """
        results = []

        # 第一级：全部保留（最高优先级）
        results.extend(level_1)
        remaining_slots = max_results - len(results)

        if remaining_slots <= 0:
            logger.info("第一级结果已满额，直接返回")
            return results[:max_results]

        # 第二级：取前min(6, remaining_slots/2)个
        level_2_slots = min(6, remaining_slots // 2)
        level_2_selected = level_2[:level_2_slots]
        results.extend(level_2_selected)
        remaining_slots = max_results - len(results)

        if remaining_slots <= 0:
            logger.info("第一级+第二级结果已满额")
            return results[:max_results]

        # 第三级：各方法分别取前4个，按分数排序
        level_3_all = []

        # 各方法分别选取
        jieba_selected = level_3_jieba[:4]
        semantic_selected = level_3_semantic[:4]
        mmr_selected = level_3_mmr[:4]

        level_3_all.extend(jieba_selected)
        level_3_all.extend(semantic_selected)
        level_3_all.extend(mmr_selected)

        # 按分数排序并选取剩余名额
        level_3_all.sort(key=lambda x: x['final_score'], reverse=True)
        level_3_selected = level_3_all[:remaining_slots]
        results.extend(level_3_selected)

        # 最终统计
        final_count = len(results)
        logger.info(
            f"最终结果: 第一级({len(level_1)}), 第二级({len(level_2_selected)}), "
            f"第三级({len(level_3_selected)}), 总计({final_count})"
        )

        return results[:max_results]
    # def _select_from_level_3(self, level_3_j, level_3_s, level_3_m, needed_count):
    #     """
    #     从第三级选择结果
    #
    #     策略：
    #     1. 如果需要的数量 <= 9，按 semantic > mmr > jieba 优先级分配
    #     2. 如果需要的数量 > 9，每类平均分配（各取 needed_count/3）
    #     """
    #     if needed_count <= 0:
    #         return []
    #
    #     selected = []
    #
    #     # 如果需求数量较少，按优先级分配
    #     if needed_count <= 9:
    #         # 计算每类应该分配的名额
    #         semantic_slots = min((needed_count + 2) // 3, len(level_3_s))  # 向上取整
    #         mmr_slots = min((needed_count + 1) // 3, len(level_3_m))  # 中间值
    #         jieba_slots = min(needed_count // 3, len(level_3_j))  # 向下取整
    #
    #         # 按优先级调整：semantic > mmr > jieba
    #         remaining_slots = needed_count - (semantic_slots + mmr_slots + jieba_slots)
    #         while remaining_slots > 0:
    #             if len(level_3_s) > semantic_slots:
    #                 semantic_slots += 1
    #             elif len(level_3_m) > mmr_slots:
    #                 mmr_slots += 1
    #             elif len(level_3_j) > jieba_slots:
    #                 jieba_slots += 1
    #             else:
    #                 break
    #             remaining_slots -= 1
    #     else:
    #         # 需求数量较多，平均分配
    #         slots_per_type = (needed_count + 2) // 3  # 向上取整
    #         semantic_slots = min(slots_per_type, len(level_3_s))
    #         mmr_slots = min(slots_per_type, len(level_3_m))
    #         jieba_slots = min(slots_per_type, len(level_3_j))
    #
    #         # 如果还有剩余名额，按优先级分配
    #         current_total = semantic_slots + mmr_slots + jieba_slots
    #         remaining_slots = needed_count - current_total
    #
    #         priority_order = [('semantic', level_3_s), ('mmr', level_3_m), ('jieba', level_3_j)]
    #         for source_type, source_list in priority_order:
    #             if remaining_slots <= 0:
    #                 break
    #             if source_type == 'semantic' and len(level_3_s) > semantic_slots:
    #                 semantic_slots += 1
    #                 remaining_slots -= 1
    #             elif source_type == 'mmr' and len(level_3_m) > mmr_slots:
    #                 mmr_slots += 1
    #                 remaining_slots -= 1
    #             elif source_type == 'jieba' and len(level_3_j) > jieba_slots:
    #                 jieba_slots += 1
    #                 remaining_slots -= 1
    #
    #     # 选取结果
    #     selected.extend(level_3_s[:semantic_slots])
    #     selected.extend(level_3_m[:mmr_slots])
    #     selected.extend(level_3_j[:jieba_slots])
    #
    #     logger.info(
    #         f"第三级分配: semantic({semantic_slots}), mmr({mmr_slots}), jieba({jieba_slots})"
    #     )
    #
    #     return selected
    # def _merge_and_score(
    #     self,
    #     jieba_candidates: List[Dict[str, Any]],
    #     semantic_candidates: List[Dict[str, Any]],
    #     mmr_candidates: List[Dict[str, Any]] = None,
    #     jieba_weight: float = 0.3,
    #     semantic_weight: float = 0.5,
    #     mmr_weight: float = 0.2
    # ) -> List[Dict[str, Any]]:
    #     """
    #     合并三个检索结果，去重并计算混合得分
    #
    #     公式：final_score = jieba_weight * jieba_score + semantic_weight * semantic_score + mmr_weight * mmr_score
    #
    #     Args:
    #         jieba_candidates: jieba检索结果
    #         semantic_candidates: 语义检索结果
    #         mmr_candidates: MMR检索结果（可选）
    #         jieba_weight: jieba分数权重（默认30%）
    #         semantic_weight: 语义分数权重（默认50%）
    #         mmr_weight: MMR分数权重（默认20%）
    #
    #     Returns:
    #         合并后的结果列表，包含final_score字段
    #     """
    #     # 如果没有提供MMR结果，初始化为空列表
    #     if mmr_candidates is None:
    #         mmr_candidates = []
    #
    #     # 使用scenario_id作为key进行合并（去重）
    #     merged_dict = {}
    #
    #     # 1. 处理jieba结果
    #     for item in jieba_candidates:
    #         scenario_id = item['scenario_id']
    #         merged_dict[scenario_id] = {
    #             'scenario': item['scenario'],
    #             'scenario_id': scenario_id,
    #             'jieba_score': item.get('jieba_score', 0),
    #             'semantic_score': 0,  # 默认0
    #             'mmr_score': 0,  # 默认0
    #             'matched_keywords': item.get('matched_keywords', []),
    #             'sources': ['jieba']  # 记录来源
    #         }
    #
    #     # 2. 处理语义结果（合并或新增）
    #     for item in semantic_candidates:
    #         scenario_id = item['scenario_id']
    #         if scenario_id in merged_dict:
    #             # 已存在，更新semantic_score
    #             merged_dict[scenario_id]['semantic_score'] = item.get('semantic_score', 0)
    #             merged_dict[scenario_id]['sources'].append('semantic')
    #         else:
    #             # 不存在，新增
    #             merged_dict[scenario_id] = {
    #                 'scenario': item['scenario'],
    #                 'scenario_id': scenario_id,
    #                 'jieba_score': 0,  # 默认0
    #                 'semantic_score': item.get('semantic_score', 0),
    #                 'mmr_score': 0,  # 默认0
    #                 'matched_keywords': [],
    #                 'sources': ['semantic']
    #             }
    #
    #     # 3. 处理MMR结果（合并或新增）
    #     for item in mmr_candidates:
    #         scenario_id = item['scenario_id']
    #         if scenario_id in merged_dict:
    #             # 已存在，更新mmr_score
    #             merged_dict[scenario_id]['mmr_score'] = item.get('mmr_score', 0)
    #             merged_dict[scenario_id]['sources'].append('mmr')
    #             # 保存MMR的文档内容
    #             if 'document_content' in item:
    #                 merged_dict[scenario_id]['document_content'] = item['document_content']
    #         else:
    #             # 不存在，新增
    #             merged_dict[scenario_id] = {
    #                 'scenario': item['scenario'],
    #                 'scenario_id': scenario_id,
    #                 'jieba_score': 0,  # 默认0
    #                 'semantic_score': 0,  # 默认0
    #                 'mmr_score': item.get('mmr_score', 0),
    #                 'matched_keywords': [],
    #                 'document_content': item.get('document_content', ''),
    #                 'sources': ['mmr']
    #             }
    #
    #     # 4. 计算混合得分
    #     merged_results = []
    #     for scenario_id, data in merged_dict.items():
    #         # 加权计算最终得分
    #         final_score = (
    #             jieba_weight * data['jieba_score'] +
    #             semantic_weight * data['semantic_score'] +
    #             mmr_weight * data['mmr_score']
    #         )
    #         data['final_score'] = final_score
    #
    #         # 记录各项得分的贡献
    #         data['score_breakdown'] = {
    #             'jieba': jieba_weight * data['jieba_score'],
    #             'semantic': semantic_weight * data['semantic_score'],
    #             'mmr': mmr_weight * data['mmr_score']
    #         }
    #
    #         merged_results.append(data)
    #
    #     # 5. 记录合并统计信息
    #     logger.info(
    #         f"合并结果: jieba={len(jieba_candidates)}, "
    #         f"semantic={len(semantic_candidates)}, "
    #         f"mmr={len(mmr_candidates)}, "
    #         f"merged={len(merged_results)} (去重后)"
    #     )
    #     logger.info(
    #         f"权重配置: jieba={jieba_weight:.1%}, "
    #         f"semantic={semantic_weight:.1%}, "
    #         f"mmr={mmr_weight:.1%}"
    #     )
    #
    #     m=merged_results.sort(key=lambda x: x['final_score'], reverse=True)
    #     return m[:15]
    #
    async def _build_structured_filters(
        self, 
        patient_info: PatientInfo, 
        clinical_context: ClinicalContext
    ) -> List[Any]:
        """
        构建结构化过滤条件
        
        基于患者的硬性条件（年龄、性别、妊娠状态、紧急程度）进行筛选
        """
        filters = []
        
        # 年龄过滤
        if patient_info.age is not None:
            # 匹配年龄组（如"40岁以上"、"18-65岁"等）
            # 这里需要根据实际数据格式调整逻辑
            filters.append(
                or_(
                    ClinicalScenario.age_group.is_(None),
                    ClinicalScenario.age_group.like(f"%{patient_info.age}%")
                )
            )
        
        # 性别过滤
        if patient_info.gender:
            filters.append(
                or_(
                    ClinicalScenario.gender.is_(None),
                    ClinicalScenario.gender == patient_info.gender,
                    ClinicalScenario.gender == "不限"
                )
            )
        
        # 妊娠状态过滤
        if patient_info.pregnancy_status:
            filters.append(
                or_(
                    ClinicalScenario.pregnancy_status.is_(None),
                    ClinicalScenario.pregnancy_status == patient_info.pregnancy_status
                )
            )
        
        # 紧急程度过滤
        if clinical_context.urgency_level:
            filters.append(
                or_(
                    ClinicalScenario.urgency_level.is_(None),
                    ClinicalScenario.urgency_level == clinical_context.urgency_level
                )
            )
        
        # 激活状态
        filters.append(ClinicalScenario.is_active == True)
        
        return filters
    
    # async def _vector_semantic_search(
    #     self,
    #     patient_info: PatientInfo,
    #     clinical_context: ClinicalContext,
    #     embedding_model: Optional[Embedding],
    #     top_k: int = 30,
    # ) -> List[Dict[str, Any]]:
    #     """
    #     向量语义检索（基于结构化格式）
    #
    #     构建查询文本格式：
    #     主诉: xxx
    #     既往病史: xxx
    #     现病史: xxx
    #     诊断: xxx
    #     患者人群: xxx
    #     年龄组: xxx
    #     性别: xxx
    #     妊娠状态: xxx
    #     紧急程度: xxx
    #     """
    #     # 构建结构化查询文本（匹配数据库中的embedding格式）
    #     query_parts = []
    #
    #     # 添加临床上下文信息
    #     if clinical_context.chief_complaint:
    #         query_parts.append(f"主诉: {clinical_context.chief_complaint}")
    #
    #     if clinical_context.medical_history:
    #         query_parts.append(f"既往病史: {clinical_context.medical_history}")
    #
    #     if clinical_context.present_illness:
    #         query_parts.append(f"现病史: {clinical_context.present_illness}")
    #
    #     if clinical_context.diagnosis:
    #         query_parts.append(f"诊断: {clinical_context.diagnosis}")
    #
    #     # 添加患者信息（增强语义匹配）
    #     if patient_info.age:
    #         query_parts.append(f"年龄: {patient_info.age}岁")
    #
    #     if patient_info.gender:
    #         query_parts.append(f"性别: {patient_info.gender}")
    #
    #     if patient_info.pregnancy_status:
    #         query_parts.append(f"妊娠状态: {patient_info.pregnancy_status}")
    #
    #     if clinical_context.urgency_level:
    #         query_parts.append(f"紧急程度: {clinical_context.urgency_level}")
    #
    #     if clinical_context.symptom_severity:
    #         query_parts.append(f"症状严重程度: {clinical_context.symptom_severity}")
    #
    #     # 用换行符连接，模拟数据库中的embedding格式
    #     query_text = "\n".join(query_parts)
    #
    #     # 使用嵌入模型生成查询向量
    #     if not embedding_model:
    #         # 如果没有嵌入模型，使用文本匹配降级方案
    #         return await self._text_based_search(clinical_context, top_k)
    #
    #     try:
    #         query_embedding = await self._get_embedding(embedding_model, query_text)
    #     except Exception as e:
    #         print(f"向量化失败，降级到文本检索: {e}")
    #         return await self._text_based_search(clinical_context, top_k)
    #
    #     # 执行向量相似度检索
    #     # 使用pgvector的余弦距离函数，需要将Python list转换为vector类型
    #
    #     query_vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
    #
    #     statement = (
    #         select(
    #             ClinicalScenario,
    #             func.cosine_distance(  # 或者使用 cosine_distance, inner_product
    #                 ClinicalScenario.embedding,  # 假设字段已定义为vector类型
    #                 text(f"'{query_vector_str}'")
    #             ).label('distance')
    #         )
    #         .where(ClinicalScenario.is_active == True)
    #         .order_by(text('distance'))
    #         .limit(top_k)
    #     )
    #
    #     result = await self.session.exec(statement)
    #     rows = result.all()
    #
    #     # 转换为字典格式，包含相似度分数
    #     candidates = []
    #     for scenario, distance in rows:
    #         # 将距离转换为相似度分数（0-1，越高越相似）
    #         similarity_score = 1 - distance
    #         candidates.append({
    #             'scenario': scenario,
    #             'vector_similarity': max(0, similarity_score),
    #             'scenario_id': scenario.semantic_id
    #         })
    #
    #     return candidates
    
    def _apply_structured_filter(
        self,
        candidates: List[Dict[str, Any]],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext
    ) -> List[Dict[str, Any]]:
        """
        应用结构化筛选（在向量检索结果上进行过滤）
        
        基于患者的硬性条件（年龄、性别、妊娠状态、紧急程度）进行筛选
        """
        filtered = []
        
        for candidate in candidates:
            scenario = candidate['scenario']
            should_include = True
            
            # 年龄过滤
            if patient_info.age is not None and scenario.age_group:
                # 简单匹配逻辑，可以根据实际需求优化
                if not self._match_age_group(patient_info.age, scenario.age_group):
                    should_include = False
            
            # 性别过滤
            if patient_info.gender and scenario.gender:
                if scenario.gender not in [patient_info.gender, "不限", None]:
                    should_include = False
            
            # 妊娠状态过滤
            if patient_info.pregnancy_status and scenario.pregnancy_status:
                if scenario.pregnancy_status != patient_info.pregnancy_status:
                    should_include = False
            
            # 紧急程度过滤
            if clinical_context.urgency_level and scenario.urgency_level:
                if scenario.urgency_level != clinical_context.urgency_level:
                    should_include = False
            
            if should_include:
                filtered.append(candidate)
        
        return filtered
    
    def _match_age_group(self, age: int, age_group: str) -> bool:
        """
        匹配年龄组
        
        纯CPU计算（正则匹配），保持同步方法
        
        示例：
        - "40岁以上" -> age >= 40
        - "18-65岁" -> 18 <= age <= 65
        - "儿童" -> age < 18
        """
        import re
        
        # 匹配 "XX岁以上"
        match = re.search(r'(\d+)岁以上', age_group)
        if match:
            threshold = int(match.group(1))
            return age >= threshold
        
        # 匹配 "XX-YY岁"
        match = re.search(r'(\d+)-(\d+)岁', age_group)
        if match:
            min_age = int(match.group(1))
            max_age = int(match.group(2))
            return min_age <= age <= max_age
        
        # 匹配 "XX岁以下"
        match = re.search(r'(\d+)岁以下', age_group)
        if match:
            threshold = int(match.group(1))
            return age <= threshold
        
        # 特殊情况
        if "儿童" in age_group or "小儿" in age_group:
            return age < 18
        if "老年" in age_group:
            return age >= 65
        if "成人" in age_group:
            return 18 <= age < 65
        
        # 默认通过
        return True
    
    # async def _text_based_search(
    #     self,
    #     clinical_context: ClinicalContext,
    #     top_k: int = 30
    # ) -> List[Dict[str, Any]]:
    #     """
    #     基于文本的降级检索方案（当向量检索不可用时）
    #     """
    #     # 提取关键词
    #     keywords = self._extract_keywords(clinical_context)
    #
    #     # 构建文本匹配条件
    #     text_conditions = [ClinicalScenario.is_active == True]
    #
    #     for keyword in keywords:
    #         text_conditions.append(
    #             or_(
    #                 ClinicalScenario.description_zh.contains(keyword),
    #                 ClinicalScenario.clinical_context.contains(keyword),
    #                 ClinicalScenario.symptom_category.contains(keyword)
    #             )
    #         )
    #
    #     statement = (
    #         select(ClinicalScenario)
    #         .where(and_(*text_conditions))
    #         .limit(top_k)
    #     )
    #
    #     result = await self.session.exec(statement)
    #     scenarios = result.all()
    #
    #     # 返回候选场景（使用默认相似度）
    #     candidates = []
    #     for scenario in scenarios:
    #         candidates.append({
    #             'scenario': scenario,
    #             'vector_similarity': 0.5,  # 默认中等相似度
    #             'scenario_id': scenario.semantic_id
    #         })
    #
    #     return candidates
    
    async def _calculate_keyword_scores(
        self,
        clinical_context: ClinicalContext,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        计算关键词匹配分数
        
        提取临床上下文中的关键词，计算每个候选场景的关键词匹配度
        """
        # 提取查询关键词
        query_keywords = self._extract_keywords(clinical_context)
        
        keyword_scores = {}
        
        for candidate in candidates:
            scenario = candidate['scenario']
            scenario_id = candidate['scenario_id']
            
            # 提取场景中的文本内容
            scenario_text = " ".join([
                scenario.description_zh or "",
                scenario.clinical_context or "",
                scenario.symptom_category or "",
                scenario.patient_population or ""
            ])
            
            # 计算关键词重叠度
            matched_keywords = sum(
                1 for keyword in query_keywords 
                if keyword in scenario_text
            )
            
            # 归一化分数（0-1）
            if query_keywords:
                keyword_scores[scenario_id] = matched_keywords / len(query_keywords)
            else:
                keyword_scores[scenario_id] = 0.0
        
        return keyword_scores
    
    async def _apply_contraindication_filter(
        self,
        candidates: List[Dict[str, Any]],
        patient_info: PatientInfo
    ) -> List[Dict[str, Any]]:
        """
        应用禁忌症和特殊考虑过滤
        
        根据患者的过敏史、合并症等信息，过滤掉有禁忌症的场景
        """
        filtered = []
        
        for candidate in candidates:
            scenario = candidate['scenario']
            
            # 检查禁忌症（这里需要根据实际数据结构调整）
            # 示例：如果患者有某种过敏，排除相关场景
            has_contraindication = False
            
            # 如果患者是孕妇，检查妊娠安全性
            if patient_info.pregnancy_status in ['pregnant', 'lactating']:
                if scenario.pregnancy_status and '禁忌' in scenario.pregnancy_status:
                    has_contraindication = True
            
            # 检查患者过敏史
            if patient_info.allergies:
                # 这里可以扩展更复杂的禁忌症逻辑
                pass
            
            if not has_contraindication:
                filtered.append(candidate)
        
        return filtered
    
    # async def _hybrid_scoring(
    #     self,
    #     candidates: List[Dict[str, Any]],
    #     keyword_scores: Dict[str, float],
    #     search_strategy: SearchStrategy
    # ) -> List[Dict[str, Any]]:
    #     """
    #     混合打分：结合向量相似度、关键词匹配、规则匹配
    #
    #     加权公式：
    #     final_score = vector_weight * vector_sim + keyword_weight * keyword_score + rule_weight * rule_score
    #     """
    #     scored = []
    #
    #     for candidate in candidates:
    #         scenario_id = candidate['scenario_id']
    #         vector_sim = candidate.get('vector_similarity', 0)
    #         keyword_score = keyword_scores.get(scenario_id, 0)
    #
    #         # 规则分数（可以基于场景的其他属性计算）
    #         rule_score = self._calculate_rule_score(candidate['scenario'])
    #
    #         # 加权融合
    #         final_score = (
    #             search_strategy.vector_weight * vector_sim +
    #             search_strategy.keyword_weight * keyword_score +
    #             search_strategy.rule_weight * rule_score
    #         )
    #
    #         candidate['keyword_score'] = keyword_score
    #         candidate['rule_score'] = rule_score
    #         candidate['final_score'] = final_score
    #
    #         scored.append(candidate)
    #
    #     # 按最终分数降序排序
    #     scored.sort(key=lambda x: x['final_score'], reverse=True)
    #
    #     return scored
    
    def _calculate_rule_score(self, scenario: ClinicalScenario) -> float:
        """
        计算规则匹配分数
        
        纯CPU计算（简单算术），保持同步方法
        基于场景的其他属性（如风险等级、症状分类等）计算分数
        """
        score = 0.5  # 基础分数
        
        # 根据风险等级调整
        if scenario.risk_level:
            if scenario.risk_level == "低风险":
                score += 0.2
            elif scenario.risk_level == "中风险":
                score += 0.1
        
        # 如果有临床上下文，略微提升分数
        if scenario.clinical_context:
            score += 0.1
        
        return min(score, 1.0)  # 限制在0-1范围
    
    async def _rerank_scenarios(
        self,
        clinical_context: ClinicalContext,
        scenarios: List[Dict[str, Any]],
        reranker_model: Any
    ) -> List[Dict[str, Any]]:
        """
        使用重排序模型对候选场景重新排序
        """
        if not reranker_model or not scenarios:
            return scenarios
        
        # 构建查询文本
        query_text = f"{clinical_context.chief_complaint} {clinical_context.diagnosis or ''}"
        
        # 准备文档列表
        documents = [
            s['scenario'].description_zh for s in scenarios
        ]
        
        try:
            # 调用重排序模型
            rerank_scores = await self._get_rerank_scores(reranker_model,query_text, documents)
            
            # 更新分数
            for i, scenario in enumerate(scenarios):
                if i < len(rerank_scores):
                    scenario['rerank_score'] = rerank_scores[i]
                    # 混合原始分数和重排序分数
                    scenario['final_score'] = (
                        0.7 * scenario['final_score'] + 
                        0.3 * rerank_scores[i]
                    )
            
            # 重新排序
            scenarios.sort(key=lambda x: x['final_score'], reverse=True)
        except Exception as e:
            print(f"重排序失败: {e}")
        
        return scenarios
    
    async def _get_embedding(self,embedding_model:EmbeddingClientSDK, text: str) -> List[float]:
        """调用嵌入模型生成向量"""
        # 这里需要根据实际的嵌入模型接口实现
        # 示例实现：
        if hasattr(embedding_model, 'aembed_query'):
            result = await embedding_model.aembed_query(text)
            return result

        elif hasattr(embedding_model,"aembedding"):
            return await embedding_model.aembedding(text)
        else:
            raise NotImplementedError("嵌入模型接口未实现")
    
    async def _get_rerank_scores(self, reranker_model: Any,query: str, documents: List[str]) -> List[float]:
        """调用重排序模型计算分数"""
        # 这里需要根据实际的重排序模型接口实现
        if hasattr(reranker_model, 'rerank'):
            result = await reranker_model.rerank(query, documents)
            return result
        elif hasattr(reranker_model, '__call__'):
            result = await reranker_model(query, documents)
            return result
        else:
            raise NotImplementedError("重排序模型接口未实现")
    
    async def _extract_keywords(self, clinical_context: ClinicalContext, medical_dict: list = None) -> List[str]:
        """
        从临床上下文中提取关键词
        
        使用jieba进行中文分词，提取医学关键词
        注意：此方法通过线程池执行CPU密集型的jieba分词，避免阻塞事件循环
        """
        if medical_dict is None:
            medical_dict = {}
        
        # 收集需要分词的文本
        texts_to_tokenize = []
        if clinical_context.chief_complaint:
            texts_to_tokenize.append(clinical_context.chief_complaint)
        if clinical_context.diagnosis:
            texts_to_tokenize.append(clinical_context.diagnosis)
        if clinical_context.present_illness:
            texts_to_tokenize.append(clinical_context.present_illness[:200])
        if clinical_context.medical_history:
            texts_to_tokenize.append(clinical_context.medical_history[:200])
        
        # 在线程池中并发执行所有分词任务（CPU密集型）
        tasks = [
            asyncio.get_event_loop().run_in_executor(
                None,
                self._jieba_tokenize,
                text,
                medical_dict,
                None
            )
            for text in texts_to_tokenize
        ]
        
        # 等待所有分词任务完成
        results = await asyncio.gather(*tasks) if tasks else []
        
        # 合并所有关键词
        keywords = []
        for result in results:
            keywords.extend(result)
        
        # 去重并过滤
        keywords = list(set(keywords))
        
        # 按关键词长度排序，优先保留长词（医学术语通常较长）
        keywords.sort(key=len, reverse=True)
        
        # 限制关键词数量，避免过多噪音
        return keywords[:50]
    
    def _jieba_tokenize(self, text: str,medical_dict:list,new_item:list=None) -> List[str]:
        """
        使用jieba进行中文分词和关键词提取
        
        特性：
        - 自动加载外部医学词典（dict目录下的文件）
        - 内置200+医学术语作为补充
        - TextRank + TF-IDF双算法提取关键词
        - 智能停用词过滤
        - 优先级排序（医学术语>长词>短词）
        """
        # project_root = Path(__file__).parent.parent.parent.parent
        # dict_dir = project_root / "dict"

        import jieba
        import jieba.analyse
        # jieba.analyse.set_stop_words(dict_dir / "stops.txt")
        # 内置医学术语作为补充（以防外部词典加载失败）
        # 这些术语会与外部词典合并使用
        builtin_medical_terms = [
            '冠心病', '急性冠脉综合征', '心肌梗死', '心绞痛', '高血压',
            '糖尿病', '脑卒中', '肺栓塞', '主动脉夹层', '心力衰竭',
            '肺炎', '支气管炎', '哮喘', '慢阻肺', '肺结核',
            '阑尾炎', '胆囊炎', '胰腺炎', '肠梗阻', '消化道出血',
            '肾结石', '尿路感染', '肾功能不全', '肾炎',
            '骨折', '脱位', '韧带损伤', '软组织挫伤',
            '甲状腺功能亢进', '甲状腺功能减退', '甲状腺结节',
            '妊娠高血压', '妊娠糖尿病', '宫外孕', '先兆流产',
            '压榨性疼痛', '呼吸困难', '咳嗽咳痰', '胸闷气短',
            '腹痛腹泻', '恶心呕吐', '头痛头晕', '发热畏寒',
            'CT', 'MRI', '超声', 'X线', '心电图', '冠状动脉造影',
            "非妊娠", "非妊娠期", "非妊娠状态"
        ]
        if new_item:
           builtin_medical_terms.extend(new_item)
        
        # 补充添加内置词汇（外部词典已在初始化时加载）
        for term in set(builtin_medical_terms):
            jieba.add_word(term, freq=10000, tag='medical')
        
        # 方法1: 使用TextRank算法提取关键词（推荐）
        keywords_textrank = jieba.analyse.textrank(
            text,
            topK=20,  # 提取前20个关键词
            withWeight=False,
            allowPOS=('n', 'nr', 'nt', 'nz', 'v', 'a',
                      "f","ns","ad","q",'u','s','vd','r','xc','t',
                      'vn'

                      ),
            # 名词、动词、形容词
        )
        
        # 方法2: 使用TF-IDF算法提取关键词（作为补充）
        keywords_tfidf = jieba.analyse.extract_tags(
            text,
            topK=15,
            withWeight=False
        )

        all_words=set(builtin_medical_terms)
        for suggest in all_words:
             jieba.suggest_freq(suggest,True)
        # 方法3: 基础分词（保留所有医学相关词）
        words = jieba.lcut(text, cut_all=False)
        
        # 停用词列表（扩展版）
        stop_words = {
            # 通用停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
            '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
            '自己', '这', '那', '里', '啊', '吗', '呢', '吧', '哦', '嗯', '哈',
            # 临床常见虚词
            '患者', '病人', '病史', '年', '岁', '次', '天', '小时', '分钟',
            '主诉', '现病史', '既往史', '诊断', '症状', '表现'
        }
        
        # 过滤停用词和单字
        words_filtered = [
            w for w in words
            if w not in stop_words and len(w) >= 2  # 保留长度>=2的词
        ]

        
        # 合并三种方法的结果
        all_keywords = list(set(keywords_textrank + keywords_tfidf + words_filtered))
        
        # 获取所有已加载的医学术语（外部词典 + 内置词典）
        all_medical_terms = set(builtin_medical_terms)
        try:
            all_medical_terms.update(medical_dict)
        except:
            pass  # 如果获取失败，使用内置词典即可
        
        # 优先级排序：医学术语 > 长词 > 其他
        medical_keywords = [w for w in all_keywords if w in all_medical_terms]
        long_keywords = [w for w in all_keywords if len(w) >= 3 and w not in medical_keywords]
        other_keywords = [w for w in all_keywords if len(w) == 2 and w not in medical_keywords]
        
        return medical_keywords + long_keywords + other_keywords
    
    async def _get_cached_keywords(self, text: str) -> Optional[Dict[str, List[str]]]:
        """尝试从Redis缓存读取关键词，避免重复触发LLM调用"""
        if not text or not self.redis_client:
            return None
        cache_key = f"medical_keywords:{hashlib.md5(text.encode('utf-8')).hexdigest()}"
        try:
            cached_value = await self.redis_client.get(cache_key)
        except Exception as exc:
            logger.warning(f"获取关键词缓存失败: {exc}")
            return None
        if not cached_value:
            return None
        if isinstance(cached_value, bytes):
            try:
                cached_value = cached_value.decode('utf-8')
            except Exception as exc:
                logger.warning(f"关键词缓存解码失败: {exc}")
                return None
        try:
            cached_data = json.loads(cached_value)
        except json.JSONDecodeError as exc:
            logger.warning(f"关键词缓存JSON解析失败: {exc}")
            return None
        return {
            'keywords': cached_data.get('keywords') or [],
            'new_terms': cached_data.get('new_terms') or []
        }

    async def _cache_keywords(
        self,
        text: str,
        keywords: List[str],
        new_terms: List[str],
        ttl: int = 12 * 60 * 60,
    ) -> None:
        """将关键词结果写入Redis缓存"""
        if not keywords or not self.redis_client:
            return
        cache_key = f"medical_keywords:{hashlib.md5(text.encode('utf-8')).hexdigest()}"
        payload = json.dumps({'keywords': keywords, 'new_terms': new_terms}, ensure_ascii=False)
        try:
            await self.redis_client.set(cache_key, payload, ex=ttl)
        except Exception as exc:
            logger.warning(f"写入关键词缓存失败: {exc}")

    async def _hybrid_tokenize_with_llm_verification(
        self,
        text: str,
        medical_dict: list
    ) -> tuple[List[str], List[str]]:
        """Run jieba and LLM keyword extraction in parallel and update the dictionary dynamically."""
        import jieba

        cached_keywords = await self._get_cached_keywords(text)
        if cached_keywords and cached_keywords["keywords"]:
            cached_new_terms = cached_keywords.get("new_terms") or []
            if cached_new_terms:
                for term in cached_new_terms:
                    if len(term) >= 2:
                        jieba.add_word(term, freq=10000, tag="medical_dynamic")
                logger.info("keywords cache hit; restored %s new terms", len(cached_new_terms))
            logger.info("reusing %s cached keywords", len(cached_keywords["keywords"]))
            return cached_keywords["keywords"], cached_new_terms

        logger.info("starting parallel jieba + LLM keyword extraction")
        jieba_task = asyncio.get_event_loop().run_in_executor(
            None,
            self._jieba_tokenize,
            text,
            medical_dict,
            None
        )
        llm_task = self.ai_service.extract_medical_keywords_by_llm(text, top_k=20)
        try:
            jieba_keywords, llm_keywords = await asyncio.gather(
                jieba_task,
                llm_task,
                return_exceptions=True
            )
            if isinstance(jieba_keywords, Exception):
                logger.error("jieba keyword extraction failed: %s", jieba_keywords)
                jieba_keywords = []
            if isinstance(llm_keywords, Exception):
                logger.error("LLM keyword extraction failed: %s", llm_keywords)
                llm_keywords = []

            jieba_set = set(jieba_keywords)
            llm_set = set(llm_keywords)
            new_terms = list(llm_set - jieba_set)

            if new_terms:
                logger.info("LLM discovered %s new medical terms", len(new_terms))
                for term in new_terms:
                    if len(term) >= 2:
                        jieba.add_word(term, freq=10000, tag="medical_dynamic")
                        logger.debug("added dynamic term: %s", term)
            else:
                logger.info("jieba and LLM keywords are identical; dictionary unchanged")

            merged_keywords = list(jieba_set | llm_set)
            merged_keywords.sort(key=len, reverse=True)

            logger.info(
                "merged keywords=%s (jieba=%s, llm=%s, new=%s)",
                len(merged_keywords),
                len(jieba_keywords),
                len(llm_keywords),
                len(new_terms)
            )

            await self._cache_keywords(text, merged_keywords, new_terms)
            return merged_keywords, new_terms

        except Exception as exc:
            logger.error("hybrid tokenization failed: %s", exc)
            fallback_keywords = self._jieba_tokenize(text, medical_dict, None)
            await self._cache_keywords(text, fallback_keywords, [])
            return fallback_keywords, []
    async def _async_persist_new_terms(self, new_terms: List[str]):
        """
        异步持久化新发现的医学术语到词典文件
        
        使用Celery异步任务在后台执行，完全不阻塞主流程
        
        Args:
            new_terms: 新发现的医学术语列表
        """
        try:
            # 触发Celery异步任务
            task = batch_persist_by_category_async.delay(new_terms)
            logger.info(f"✅ 已触发Celery任务：ID={task.id}, 待持久化 {len(new_terms)} 个新术语")
        except Exception as e:
            logger.error(f"❌ Celery任务触发失败，降级为线程池执行: {e}")
            # 降级方案：如果Celery不可用，使用线程池
            await asyncio.get_event_loop().run_in_executor(
                None,
                batch_persist_by_category,
                new_terms
            )
    
    def _simple_tokenize(self, text: str) -> List[str]:
        """
        简单分词（降级方案，当jieba不可用时）
        
        纯CPU计算，保持同步方法
        已废弃，保留作为后备方案
        """
        import re
        # 提取中文词汇（2-4个字）
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        
        # 停用词过滤（简化版）
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        words = [w for w in words if w not in stop_words]
        
        return words

    async def get_scenario_recommendations(
            self,
            scenario_id: str,
            top_k: int = 10,
            min_rating: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取指定临床场景的推荐项目

        Args:
            scenario_id: 临床场景ID
            top_k: 返回的推荐数量
            min_rating: 最低适宜性评分

        Returns:
            推荐项目列表，按appropriateness_rating降序排序
        """
        session = await self._get_independent_session()
        try:
            # 构建查询
            statement = (
                select(ClinicalRecommendation, ProcedureDictionary)
                .join(ProcedureDictionary, ClinicalRecommendation.procedure_id == ProcedureDictionary.semantic_id)
                .where(
                    and_(
                        ClinicalRecommendation.scenario_id == scenario_id,
                        ClinicalRecommendation.is_active == True,
                        ProcedureDictionary.is_active == True
                    )
                )
            )

            if min_rating is not None:
                statement = statement.where(ClinicalRecommendation.appropriateness_rating >= min_rating)

            statement = statement.order_by(ClinicalRecommendation.appropriateness_rating.desc())
            statement = statement.limit(top_k)

            result = await session.exec(statement)
            rows = result.all()

            recommendations_list = []
            for recommendation, procedure in rows:
                recommendations_list.append({
                    "recommendation": recommendation,
                    "procedure": procedure
                })

            return recommendations_list

        except Exception as e:
            logger.error(f"获取场景 {scenario_id} 推荐项目失败: {e}")
            # 可以选择返回空列表或重新抛出异常
            return []
        finally:
            await session.close()

    async def _vector_mmr_search(
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
                                       str(document.metadata.get("panel_name", "")) != str(clinical_context.department)]

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
    
    # ========== 缓存相关方法 ==========
    
    async def _generate_cache_key(self, patient_info: PatientInfo, clinical_context: ClinicalContext) -> str:
        """
        生成缓存键（基于患者信息和临床上下文）
        
        使用 MD5 哈希确保键的唤一性和简洁性
        
        Args:
            patient_info: 患者信息
            clinical_context: 临床上下文
            
        Returns:
            缓存键字符串
        """
        # 构建用于生成键的数据结构
        cache_data = {
            'patient': {
                'age': patient_info.age,
                'gender': patient_info.gender,
                'pregnancy_status': patient_info.pregnancy_status,
                'allergies': sorted(patient_info.allergies) if patient_info.allergies else None,
                'comorbidities': sorted(patient_info.comorbidities) if patient_info.comorbidities else None,
                'physical_examination': patient_info.physical_examination,
            },
            'clinical': {
                'department': clinical_context.department,
                'chief_complaint': clinical_context.chief_complaint,
                'medical_history': clinical_context.medical_history,
                'present_illness': clinical_context.present_illness,
                'diagnosis': clinical_context.diagnosis,
                'symptom_duration': clinical_context.symptom_duration,
                'symptom_severity': clinical_context.symptom_severity,
            }
        }
        
        # 将数据序列化为JSON字符串（排序键以确保一致性）
        cache_str = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
        
        # 生成MD5哈希
        cache_hash = hashlib.md5(cache_str.encode('utf-8')).hexdigest()
        
        # 添加前缀，方便管理
        cache_key = f"query_standardization:{cache_hash}"
        
        return cache_key
    
    async def _get_cached_standardized_query(self, cache_key: str) -> Optional[str]:
        """
        从Redis获取缓存的标准化查询
        
        Args:
            cache_key: 缓存键
            
        Returns:
            标准化查询字符串，如果未命中则返回None
        """
        try:
            cached_value = await self.redis_client.get(cache_key)
            if cached_value:
                # Redis 返回的是 bytes，需要解码
                if isinstance(cached_value, bytes):
                    return cached_value.decode('utf-8')
                return cached_value
            return None
        except Exception as e:
            logger.error(f"从缓存获取标准化查询失败: {e}")
            return None
    
    async def _cache_standardized_query(self, cache_key: str, standardized_query: str, ttl: int = 86400):
        """
        将标准化查询存入Redis缓存
        
        Args:
            cache_key: 缓存键
            standardized_query: 标准化查询字符串
            ttl: 缓存过期时间（秒），默认24小时
        """
        try:
            await self.redis_client.set(cache_key, standardized_query, ex=ttl)
            logger.debug(f"标准化查询已缓存，键: {cache_key}, TTL: {ttl}秒")
        except Exception as e:
            logger.error(f"存储标准化查询到缓存失败: {e}")
    
    # ========== Embedding 缓存相关方法 ==========
    
    async def _get_embedding_with_cache(
        self, 
        embedding_model: EmbeddingClientSDK|None,
        text: str
    ) -> List[float]:
        """
        获取文本的 embedding 向量（带缓存）
        
        工作流程：
        1. 生成缓存键（基于文本内容）
        2. 尝试从Redis获取缓存的向量
        3. 如果缓存未命中，调用模型生成向量
        4. 将新生成的向量存入缓存
        
        Args:
            embedding_model: 嵌入模型
            text: 要向量化的文本
            
        Returns:
            embedding 向量列表
        """
        # 1. 生成缓存键
        cache_key = await self._generate_embedding_cache_key(text)
        
        # 2. 尝试从缓存获取
        cached_embedding = await self._get_cached_embedding(cache_key)
        
        if cached_embedding is not None:
            logger.info(f"从缓存获取 embedding 向量，文本长度: {len(text)}")
            return cached_embedding
        
        # 3. 缓存未命中，调用模型生成
        logger.info(f"缓存未命中，调用模型生成 embedding，文本长度: {len(text)}")
        embedding = await self._get_embedding(embedding_model, text)
        
        # 4. 将新生成的向量存入缓存
        await self._cache_embedding(cache_key, embedding)
        logger.info("已将 embedding 向量存入缓存")
        
        return embedding
    
    async def _generate_embedding_cache_key(self, text: str) -> str:
        """
        生成 embedding 缓存键
        
        使用 MD5 哈希文本内容生成唯一键
        
        Args:
            text: 要向量化的文本
            
        Returns:
            缓存键字符串
        """
        # 对文本进行 MD5 哈希
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        
        # 添加前缀，方便管理
        cache_key = f"embedding:{text_hash}"
        
        return cache_key
    
    async def _get_cached_embedding(self, cache_key: str) -> Optional[List[float]]:
        """
        从Redis获取缓存的 embedding 向量
        
        Args:
            cache_key: 缓存键
            
        Returns:
            embedding 向量列表，如果未命中则返回None
        """
        try:
            cached_value = await self.redis_client.get(cache_key)
            if cached_value:
                # Redis 返回的是 bytes，需要解码并解析为列表
                if isinstance(cached_value, bytes):
                    cached_value = cached_value.decode('utf-8')
                
                # 将 JSON 字符串转换为列表
                embedding = json.loads(cached_value)
                return embedding
            return None
        except Exception as e:
            logger.error(f"从缓存获取 embedding 失败: {e}")
            return None
    
    async def _cache_embedding(self, cache_key: str, embedding: List[float], ttl: int = 604800):
        """
        将 embedding 向量存入Redis缓存
        
        Args:
            cache_key: 缓存键
            embedding: embedding 向量列表
            ttl: 缓存过期时间（秒），默认7天
        """
        try:
            # 将列表转换为 JSON 字符串
            embedding_json = json.dumps(embedding)
            
            await self.redis_client.set(cache_key, embedding_json, ex=ttl)
            logger.debug(f"embedding 向量已缓存，键: {cache_key}, 维度: {len(embedding)}, TTL: {ttl}秒")
        except Exception as e:
            logger.error(f"存储 embedding 到缓存失败: {e}")
    
    # ========== LLM智能场景选择相关方法 ==========
    
    async def llm_rank_scenarios(
        self,
        scenarios: List[Dict[str, Any]],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        使用LLM根据患者信息智能选择最匹配的临床场景
        
        Args:
            scenarios: 候选场景列表（来自混合检索）
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            top_k: 返回的场景数量
            
        Returns:
            LLM选择的场景列表，包含llm_reasoning和llm_rank字段
        """
        if not scenarios:
            logger.warning("输入场景为空，LLM选择跳过")
            return []

        try:
            # 1. 构建场景列表文本


            # 2. 构建患者信息文本
            patient_text = f"""患者信息:
                            - 年龄: {patient_info.age}岁
                            - 性别: {patient_info.gender}
                            - 妊娠状态: {patient_info.pregnancy_status or '非妊娠期'}
                            - 过敏史: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
                            - 合并症: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
                            - 检查报告: {patient_info.physical_examination or '无'}
                            临床信息:
                            - 科室: {clinical_context.department}
                            - 主诉: {clinical_context.chief_complaint}
                            - 既往病史: {clinical_context.medical_history or '无'}
                            - 现病史: {clinical_context.present_illness or '无'}
                            - 主诊断结果: {clinical_context.diagnosis or '待诊断'}
                            - 症状严重程度: {clinical_context.symptom_severity or '未知'}
                            - 症状持续时间: {clinical_context.symptom_duration or '未知'}
                           """
            patient_token=self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(patient_text)
            available_tokens = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]-400 - patient_token -300
            scenario_texts = []
            total_scenarios_token = 0
            included_scenarios = 0

            for idx, item in enumerate(scenarios, 1):
                scenario = item['scenario']
                scenario_text = f"""场景{idx}:
                                    - ID: {scenario.id}
                                    - 科室: {scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'}
                                    - 主题: {scenario.topic.name_zh if hasattr(scenario, 'topic') and scenario.topic else '未知'}
                                    - 描述: {scenario.description_zh}
                                    - 适用人群: {scenario.patient_population or '不限'}
                                    - 年龄组: {scenario.age_group or '不限'}
                                    - 性别: {scenario.gender or '不限'}
                                    - 妊娠状态: {scenario.pregnancy_status or '不限'}
                                    - 紧急程度: {scenario.urgency_level or '不限'}
                                    - 症状分类: {scenario.symptom_category or '未知'}
                                    """

                scenario_token = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(
                    scenario_text)

                # 检查是否还有足够的token空间
                if total_scenarios_token + scenario_token <= available_tokens:
                    scenario_texts.append(scenario_text)
                    total_scenarios_token += scenario_token
                    included_scenarios += 1
                else:
                    logger.warning(
                        f"Token限制，只包含前{included_scenarios}个场景，跳过后{len(scenarios) - included_scenarios}个场景")
                    break

            # 5. 如果token仍然超限，尝试简化场景描述
            if total_scenarios_token > available_tokens and scenario_texts:
                # 简化最后一个场景的描述
                last_scenario = scenarios[included_scenarios - 1]
                scenario = last_scenario['scenario']
                simplified_text = f"""场景{included_scenarios}:
                                    - ID: {scenario.id}
                                    - 科室: {scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'}
                                    - 主题: {scenario.topic.name_zh if hasattr(scenario, 'topic') and scenario.topic else '未知'}
                                    - 描述: {scenario.description_zh[:100]}...  # 截断描述
                                    """
                simplified_token = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(
                    simplified_text)

                if total_scenarios_token - scenario_token + simplified_token <= available_tokens:
                    scenario_texts[-1] = simplified_text
                    total_scenarios_token = total_scenarios_token - scenario_token + simplified_token
                else:
                    # 如果简化后仍然超限，移除最后一个场景
                    scenario_texts.pop()
                    included_scenarios -= 1
                    logger.warning(f"移除最后一个场景以符合token限制，最终包含{included_scenarios}个场景")

            # 3. 构建Prompt
            prompt = f"""你是一位经验丰富的临床医生，需要根据患者情况从以下临床场景中选择最匹配的{top_k}个场景。

                        {patient_text}
                        
                        可选临床场景:
                        {''.join(scenario_texts)}
                        
                        请综合考虑以下因素进行选择：
                        1. 患者年龄、性别、妊娠状态是否符合场景要求
                        2. 主诉与场景描述的匹配度（语义相关性）
                        3. 科室是否对应
                        4. 症状严重程度与场景的紧急程度匹配
                        5. 是否存在禁忌症（如孕妇避免辐射检查相关场景）
                        
                        请直接输出选择的场景ID列表（数字ID，不是语义ID），格式为JSON，这是一个例子：
                        {{"selected_scenario_ids": [1, 5, 8], "reasoning": "这里填写你选择的原因"}}
                        
                        要求：
                        - 输出必须是完整的、可解析的JSON格式
                        - 根据实际用户情况和临床场景严谨的选择{top_k}个场景（为了专业性，可以选择的比top_k小，但不能为0个）
                        - 按匹配度从高到低排序
                        - 不要输出其他解释文字，只输出JSON格式结果
                        """

            # 4. 调用LLM（使用ai_service）
            response = await self.ai_service._call_llm(prompt)

            try:
                # ... 构建prompt和调用LLM的代码保持不变 ...

                # 5. 解析LLM返回的JSON - 增强健壮性
                import re
                import json

                def robust_json_parse(response: str) -> Dict[str, Any]:
                    """增强的JSON解析，处理不完整的JSON响应"""
                    # 方法1: 尝试直接解析
                    try:
                        return json.loads(response.strip())
                    except json.JSONDecodeError:
                        pass

                    # 方法2: 提取JSON对象部分
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        try:
                            json_str = json_match.group()
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass

                    # 方法3: 修复常见的JSON格式问题
                    # 修复未闭合的字符串
                    json_str = response.strip()
                    if '"reasoning": "' in json_str and not json_str.endswith('"}'):
                        # 查找reasoning字段的开始位置
                        reasoning_start = json_str.find('"reasoning": "') + len('"reasoning": "')
                        # 从reasoning开始到结尾都是reasoning的内容
                        reasoning_content = json_str[reasoning_start:]
                        # 转义特殊字符并闭合字符串
                        reasoning_content_escaped = reasoning_content.replace('"', '\\"')
                        fixed_json = json_str[:reasoning_start] + reasoning_content_escaped + '"}'
                        try:
                            return json.loads(fixed_json)
                        except json.JSONDecodeError:
                            pass

                    # 方法4: 最后尝试，构建最小有效JSON
                    try:
                        # 提取selected_scenario_ids
                        ids_match = re.search(r'"selected_scenario_ids":\s*\[([^\]]+)\]', response)
                        if ids_match:
                            ids_str = ids_match.group(1)
                            ids = [int(id_str.strip()) for id_str in ids_str.split(',')]
                            reasoning_match = re.search(r'"reasoning":\s*"([^"]*)', response)
                            reasoning = reasoning_match.group(1) if reasoning_match else "解析失败，使用默认推理"
                            return {
                                "selected_scenario_ids": ids[:top_k],
                                "reasoning": reasoning
                            }
                    except:
                        pass

                    raise json.JSONDecodeError("无法解析LLM响应", response, 0)

                # 使用增强的JSON解析
                try:
                    result = robust_json_parse(response)
                    selected_ids = result.get('selected_scenario_ids', [])
                    reasoning = result.get('reasoning', 'LLM返回格式不完整')

                    if not selected_ids:
                        logger.warning("LLM未返回选择的场景ID")
                        return []

                    # 6. 根据ID筛选场景
                    selected_scenarios = []
                    id_to_item = {item['scenario'].id: item for item in scenarios}

                    for rank, scenario_id in enumerate(selected_ids, 1):
                        if scenario_id in id_to_item:
                            item = id_to_item[scenario_id]
                            item['llm_reasoning'] = reasoning
                            item['llm_rank'] = rank
                            item['selection_source_by_llm'] = 'LLM'
                            selected_scenarios.append(item)
                        else:
                            logger.warning(f"LLM返回的场景ID {scenario_id} 不在候选列表中")

                    logger.info(f"✅ LLM选择了{len(selected_scenarios)}个场景: {selected_ids}")
                    logger.info(f"📝 LLM推理: {reasoning}")

                    return selected_scenarios[:top_k]

                except Exception as parse_error:
                    logger.error(f"❌ LLM响应解析失败: {str(parse_error)}")
                    logger.error(f"原始响应: {response}")
                    return []

            except Exception as e:
                logger.error(f"❌ LLM场景选择失败: {str(e)}")
                return []
        except Exception as e:
             logger.info(f"rananker失败{str(e)}")

    
    async def rule_rank_scenarios(
        self,
        scenarios: List[Dict[str, Any]],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        传统多维度打分排序（保底方案）
        
        Args:
            scenarios: 候选场景列表
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            top_k: 返回的场景数量
            
        Returns:
            规则排序的场景列表
        """
        if not scenarios:
            return []
        
        scored_scenarios = []
        for item in scenarios:
            scenario = item['scenario']

            # 1. 语义相似度得分（来自向量检索）
            semantic_score = item.get('semantic_score')

            # 2. 关键词匹配得分（来自jieba检索）
            keyword_score = item.get('jieba_score')

            # 3. 结构化匹配
            structure_score = self._calculate_structure_match(scenario, patient_info)

            # 4. 临床优先级
            priority_score = self._calculate_priority(scenario, clinical_context)

            # 5. MMR多样性
            diversity_score = item.get('mmr_score')

            # 修正条件判断逻辑
            if structure_score != 0 and priority_score != 0:
                # 两个都不为0的情况
                if semantic_score and diversity_score:
                    final_score = (
                            0.3 * semantic_score +
                            0.2 * structure_score +
                            0.2 * priority_score +
                            0.3 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            elif structure_score != 0:
                # 只有structure_score不为0
                if semantic_score and diversity_score:
                    final_score = (
                            0.35 * semantic_score +
                            0.3 * structure_score +
                            0.35 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            elif priority_score != 0:
                # 只有priority_score不为0
                if semantic_score and diversity_score:
                    final_score = (
                            0.35 * semantic_score +
                            0.3 * priority_score +
                            0.35 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score
            else:
                # 两个都为0的情况
                if semantic_score and diversity_score:
                    final_score = (
                            0.5 * semantic_score +
                            0.5 * diversity_score
                    )
                else:
                    final_score = semantic_score if semantic_score else diversity_score



            item['rule_score'] = final_score
            item['selection_source_by_rule'] = 'Rule'
            item['score_breakdown'] = {
                'semantic_score': semantic_score,
                'keyword_score': keyword_score,
                'structure_score': structure_score,
                'priority_score': priority_score,
                'diversity_score': diversity_score
            }
            scored_scenarios.append(item)


        scored_scenarios.sort(key=lambda  x:x["rule_score"],reverse=True)
        return scored_scenarios

    
    def _calculate_structure_match(
        self, 
        scenario: ClinicalScenario, 
        patient_info: PatientInfo
    ) -> float:
        """
        计算结构化匹配得分
        
        Args:
            scenario: 临床场景
            patient_info: 患者信息
            
        Returns:
            结构化匹配得分 (0-1)
        """
        score = 0
        count = 0

        # 年龄匹配（支持别名和范围解析）
        if patient_info.age or scenario.age_group:
            age_match_score = self._match_age(patient_info.age, scenario)
            score += age_match_score
            if age_match_score!=0:
               count += 1

        # 性别匹配（支持别名）
        if scenario.gender or patient_info.gender:
            gender_match_score = self._match_gender(patient_info.gender,scenario.gender, scenario)
            score += gender_match_score
            if gender_match_score!=0:
               count += 1

        # 妊娠状态匹配（支持别名）
        if scenario.pregnancy_status or patient_info.pregnancy_status:
            pregnancy_match_score = self._match_pregnancy_status(
                patient_info.pregnancy_status, scenario.pregnancy_status,scenario
            )
            score += pregnancy_match_score
            if pregnancy_match_score!=0:
               count += 1
        if score==0:
            return score
        return score / count if count > 0 else 0

    def _match_age(self, patient_age: int, scenario) -> float:
        """
        年龄匹配（支持范围解析和别名）

        Args:
            patient_age: 患者年龄
            scenario: 临床场景对象

        Returns:
            匹配得分 (0-1)
        """
        import re
        import jieba

        if not scenario:
            return 0

        # 首先尝试使用age_group
        age_group = scenario.age_group
        description_zh = scenario.description_zh or ""

        # 如果age_group为空，则从description_zh中提取年龄信息
        if not age_group and description_zh:
            age_group = self._extract_age_from_description(description_zh)

        # 标准化年龄组描述
        normalized_group = (age_group or "").lower().replace(' ', '').replace('岁', '')
        normalized_desc = description_zh.lower().replace(' ', '').replace('岁', '')

        # 检查"不限"
        if any(unlimited in normalized_group for unlimited in ['不限', '通用', 'all', 'both', 'any']) or \
                any(unlimited in normalized_desc for unlimited in ['不限', '通用', 'all', 'both', 'any']):
            return 1.0

        # 解析数字范围（从age_group或description中）
        range_pattern = r'(\d+)[-~至](\d+)'
        matches = []

        if age_group:
            matches.extend(re.findall(range_pattern, age_group))
        if description_zh and not matches:  # 如果age_group中没有找到范围，再从description中找
            matches.extend(re.findall(range_pattern, description_zh))

        if matches:
            for min_age, max_age in matches:
                if int(min_age) <= patient_age <= int(max_age):
                    return 1.0
            # 不在范围内，检查是否接近边界
            for min_age, max_age in matches:
                min_age_int, max_age_int = int(min_age), int(max_age)
                if abs(patient_age - min_age_int) <= 2 or abs(patient_age - max_age_int) <= 2:
                    return 0.7  # 接近边界，给较高分数
            return 0.3  # 不在范围内，给部分分数

        # 基于关键词的匹配（同时检查age_group和description）
        search_text = normalized_group + normalized_desc

        # 完整的年龄映射
        age_mapping = {
            '胎儿': ['胎儿', 'fetus', 'fetal'],
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn', '出生', '刚出生'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby', '婴孩'],
            '幼儿': ['幼儿', 'toddler', '幼童'],
            '学龄前': ['学龄前', 'preschool'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'children', 'kid'],
            '学龄期': ['学龄期', '学龄儿童', 'school-age'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager', '青春期', 'puberty'],
            '青年': ['青年', 'young adult', 'young'],
            '成人': ['成人', '成年', 'adult', 'grown-up'],
            '中年': ['中年', 'middle-aged', 'midlife'],
            '老年': ['老年', '老人', 'elderly', 'aged', 'senior', 'geriatric', '老年人', '高龄'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        # 定义各年龄段的年龄范围
        age_ranges = {
            '胎儿': (0, 0),  # 特殊处理
            '新生儿': (0, 1),  # 0-1个月
            '婴儿': (0, 2),  # 0-2岁
            '幼儿': (2, 5),  # 2-5岁
            '学龄前': (3, 6),  # 3-6岁
            '儿童': (6, 12),  # 6-12岁
            '学龄期': (6, 12),  # 6-12岁
            '青少年': (12, 18),  # 12-18岁
            '青年': (18, 40),  # 18-40岁
            '成人': (18, 65),  # 18-65岁
            '中年': (40, 65),  # 40-65岁
            '老年': (65, 150)  # 65岁以上
        }

        # 检查每个年龄段的关键词
        for age_group_name, keywords in age_mapping.items():
            if any(keyword in search_text for keyword in keywords):
                if age_group_name == '不限':
                    return 1.0
                elif age_group_name == '胎儿':
                    # 胎儿是特殊情况，通常无法匹配实际年龄
                    return 0.5
                elif age_group_name in age_ranges:
                    min_age, max_age = age_ranges[age_group_name]
                    if min_age <= patient_age <= max_age:
                        return 1.0
                    else:
                        # 不在范围内，检查是否接近边界
                        if abs(patient_age - min_age) <= 2 or abs(patient_age - max_age) <= 2:
                            return 0.7
                        else:
                            return 0.3

        return 0  # 默认分数

    def _extract_age_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取年龄信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的年龄信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 使用正则表达式提取明显的年龄范围
        range_pattern = r'(\d+)[-~至](\d+)岁?'
        range_matches = re.findall(range_pattern, description_zh)
        if range_matches:
            for min_age, max_age in range_matches:
                return f"{min_age}-{max_age}岁"

        # 完整的年龄映射
        age_mapping = {
            '胎儿': ['胎儿', 'fetus', 'fetal'],
            '新生儿': ['新生儿', '新生', 'neonate', 'newborn', '出生', '刚出生'],
            '婴儿': ['婴儿', '婴幼儿', 'infant', 'baby', '婴孩'],
            '幼儿': ['幼儿', 'toddler', '幼童'],
            '学龄前': ['学龄前', 'preschool'],
            '儿童': ['儿童', '小儿', '儿科', 'child', 'children', 'kid'],
            '学龄期': ['学龄期', '学龄儿童', 'school-age'],
            '青少年': ['青少年', '少年', 'adolescent', 'teenager', '青春期', 'puberty'],
            '青年': ['青年', 'young adult', 'young'],
            '成人': ['成人', '成年', 'adult', 'grown-up'],
            '中年': ['中年', 'middle-aged', 'midlife'],
            '老年': ['老年', '老人', 'elderly', 'aged', 'senior', 'geriatric', '老年人', '高龄'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        # 使用jieba分词并查找年龄相关关键词
        words = jieba.cut(description_zh)

        for word in words:
            word_lower = word.lower()
            for age_group, keywords in age_mapping.items():
                if word_lower in [kw.lower() for kw in keywords]:
                    return age_group

        return ""

    def _match_gender(self, patient_gender: str, scenario_gender: str, scenario: ClinicalScenario = None) -> float:
        """
        性别匹配（支持别名）

        Args:
            patient_gender: 患者性别
            scenario_gender: 场景性别要求
            scenario: 临床场景对象（可选，用于从描述中提取性别）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_gender:
            return 0  # 患者性别为空时返回中等分数

        # 如果scenario_gender为空，尝试从场景描述中提取
        if not scenario_gender and scenario and scenario.description_zh:
            scenario_gender = self._extract_gender_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_gender:
            return 0

        # 标准化输入
        patient_gender_norm = patient_gender.strip().lower()
        scenario_gender_norm = scenario_gender.strip().lower()

        # 检查是否匹配任何别名
        for standard_gender, aliases in self.gender_mapping.items():
            # 患者性别匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_gender_norm in patient_aliases_lower

            # 场景性别要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_gender_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_gender == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_gender_norm in scenario_gender_norm or scenario_gender_norm in patient_gender_norm:
            return 0.8

        return 0.0

    def _extract_gender_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取性别信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的性别信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 扩展的性别映射
        gender_mapping = {
            '男性': [
                '男', '男性', '男人', '男士', '男患者', '男童', '男孩', '男生', '男婴', '男青年',
                '男子', '男病人', '男科', '雄性', '公', '雄', 'male', 'm', 'man', 'boy', 'gentleman'
            ],
            '女性': [
                '女', '女性', '女人', '女士', '女患者', '女童', '女孩', '女生', '女婴', '女青年',
                '女子', '女病人', '妇科', '雌性', '母', '雌', 'female', 'f', 'woman', 'girl', 'lady'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', '男女', '男女均可', '男女皆可',
                'any', 'all', 'both', 'either', '通用', 'common', 'general',"成人","成年人"
            ]
        }

        # 使用正则表达式提取明显的性别信息
        gender_patterns = [
            r'([男女])性?患者?',
            r'患者?([男女])',
            r'([男女])性',
            r'([男女])子',
            r'([男女])',
            r'(雄性|雌性)',
            r'(男性|女性)',
            r'(男科|妇科)'
        ]

        for pattern in gender_patterns:
            matches = re.findall(pattern, description_zh)
            if matches:
                gender_char = matches[0]
                if gender_char in ['男', '男性', '男科', '雄性']:
                    return '男性'
                elif gender_char in ['女', '女性', '妇科', '雌性']:
                    return '女性'

        # 使用jieba分词并查找性别相关关键词
        words = jieba.cut(description_zh)

        # 创建关键词到标准性别的映射
        keyword_to_gender = {}
        for gender, keywords in gender_mapping.items():
            for keyword in keywords:
                keyword_to_gender[keyword.lower()] = gender

        # 检查每个分词是否匹配性别关键词
        for word in words:
            word_lower = word.lower()
            if word_lower in keyword_to_gender:
                return keyword_to_gender[word_lower]

        # 检查整个描述中是否包含性别关键词（用于处理未正确分词的情况）
        description_lower = description_zh.lower()
        for gender, keywords in gender_mapping.items():
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    return gender

        return ""

    def _match_pregnancy_status(self, patient_status: str, scenario_status: str,
                                scenario: ClinicalScenario = None) -> float:
        """
        妊娠状态匹配（支持别名）

        Args:
            patient_status: 患者妊娠状态
            scenario_status: 场景妊娠状态要求
            scenario: 临床场景对象（可选，用于从描述中提取妊娠状态）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_status:
            return 0  # 患者妊娠状态为空时返回中等分数

        # 如果scenario_status为空，尝试从场景描述中提取
        if not scenario_status and scenario and scenario.description_zh:
            scenario_status = self._extract_pregnancy_status_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_status:
            return 0

        # 标准化输入
        patient_status_norm = patient_status.strip().lower()
        scenario_status_norm = scenario_status.strip().lower()

        # 检查是否匹配任何别名
        for standard_status, aliases in self.pregnancy_mapping.items():
            # 患者状态匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_status_norm in patient_aliases_lower

            # 场景状态要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_status_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_status == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_status_norm in scenario_status_norm or scenario_status_norm in patient_status_norm:
            return 0.8

        return 0.0

    def _extract_pregnancy_status_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取妊娠状态信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的妊娠状态信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 扩展的妊娠状态映射
        pregnancy_mapping = {
            '妊娠期': [
                '妊娠', '怀孕', '孕妇', '孕期', '妊娠期', '孕产妇', '孕产期', '孕周', '孕早期',
                '孕中期', '孕晚期', '早孕', '中孕', '晚孕', '怀孕期', 'pregnancy', 'pregnant',
                'gestation', 'gestational', 'prenatal', 'antenatal'
            ],
            '非妊娠期': [
                '非妊娠', '非孕妇', '未怀孕', '未妊娠', '非孕期', '未孕', '非孕', 'non-pregnancy',
                'not pregnant', 'non-pregnant', 'non-gestational'
            ],
            '哺乳期': [
                '哺乳', '哺乳期', '母乳喂养', '母乳', '哺乳期妇女', '哺乳母亲', 'lactation',
                'breastfeeding', 'nursing', 'lactating'
            ],
            '备孕期': [
                '备孕', '备孕期', '计划怀孕', '准备怀孕', 'preconception', 'trying to conceive',
                'fertility', 'pre-pregnancy'
            ],
            '产后': [
                '产后', '分娩后', '生产后', 'postpartum', 'postnatal', 'after delivery',
                'puerperium', 'post-partum'
            ],
            '不孕': [
                '不孕', '不孕症', '不育', '不育症', 'infertility', 'infertile', 'sterility'
            ],
            '不限': [
                '不限', '通用', '全部', '所有', '任何', '均可', 'any', 'all', 'both', 'either',
                '通用', 'common', 'general'
            ]
        }

        # 使用正则表达式提取明显的妊娠状态信息
        pregnancy_patterns = [
            r'(妊娠|怀孕|孕妇|孕期|孕周|孕早期|孕中期|孕晚期)',
            r'(非妊娠|非孕妇|未怀孕|未妊娠|未孕|非孕)',
            r'(哺乳|哺乳期|母乳喂养)',
            r'(备孕|备孕期|计划怀孕)',
            r'(产后|分娩后|生产后)',
            r'(不孕|不孕症|不育|不育症)'
        ]

        for pattern in pregnancy_patterns:
            matches = re.findall(pattern, description_zh)
            if matches:
                status_char = matches[0]
                if status_char in ['妊娠', '怀孕', '孕妇', '孕期', '孕周', '孕早期', '孕中期', '孕晚期']:
                    return '妊娠期'
                elif status_char in ['非妊娠', '非孕妇', '未怀孕', '未妊娠', '未孕', '非孕']:
                    return '非妊娠期'
                elif status_char in ['哺乳', '哺乳期', '母乳喂养']:
                    return '哺乳期'
                elif status_char in ['备孕', '备孕期', '计划怀孕']:
                    return '备孕期'
                elif status_char in ['产后', '分娩后', '生产后']:
                    return '产后'
                elif status_char in ['不孕', '不孕症', '不育', '不育症']:
                    return '不孕'

        # 使用jieba分词并查找妊娠状态相关关键词
        words = jieba.cut(description_zh)

        # 创建关键词到标准状态的映射
        keyword_to_status = {}
        for status, keywords in pregnancy_mapping.items():
            for keyword in keywords:
                keyword_to_status[keyword.lower()] = status

        # 检查每个分词是否匹配妊娠状态关键词
        for word in words:
            word_lower = word.lower()
            if word_lower in keyword_to_status:
                return keyword_to_status[word_lower]

        # 检查整个描述中是否包含妊娠状态关键词（用于处理未正确分词的情况）
        description_lower = description_zh.lower()
        for status, keywords in pregnancy_mapping.items():
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    return status

        return ""

    def _calculate_priority(
            self,
            scenario: ClinicalScenario,
            clinical_context: ClinicalContext
    ) -> float:
        """
        计算临床优先级得分（支持科室别名）

        Args:
            scenario: 临床场景
            clinical_context: 临床上下文

        Returns:
            优先级得分 (0-1)
        """
        score = 0.0 # 基础分
        count=0
        # 科室匹配（支持别名和模糊匹配）
        if clinical_context.department and scenario.panel:
            panel_name = scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else ''
            department_score = self._match_department(clinical_context.department, panel_name)
            score += department_score
            if department_score !=0:
               count+=1

        # 症状严重程度匹配
        severity_score = self._match_urgency(clinical_context.symptom_severity, scenario.urgency_level,scenario)
        score += severity_score
        if severity_score !=0:
            count+=1

        if score ==0:
            return score

        return min(score//count, 1.0)

    def _match_department(self, patient_dept: str, scenario_dept: str) -> float:
        """
        科室匹配（支持别名和模糊匹配）

        Args:
            patient_dept: 患者科室
            scenario_dept: 场景科室

        Returns:
            匹配得分 (0-1)
        """
        if not patient_dept or not scenario_dept:
            return 0.0

        patient_dept_norm = patient_dept.lower().strip()
        scenario_dept_norm = scenario_dept.lower().strip()

        # 完全匹配
        if patient_dept_norm == scenario_dept_norm:
            return 1.0

        # 包含关系
        if patient_dept_norm in scenario_dept_norm or scenario_dept_norm in patient_dept_norm:
            return 0.8

        # 常见科室别名映射
        for standard_dept, aliases in self.department_mapping.items():
            patient_aliases = [standard_dept] + aliases
            scenario_aliases = [standard_dept] + aliases

            patient_match = any(alias.lower() in patient_dept_norm for alias in patient_aliases)
            scenario_match = any(alias.lower() in scenario_dept_norm for alias in scenario_aliases)

            if patient_match and scenario_match:
                return 0.9

        return 0.0

    def _match_urgency(self, patient_urgency: str, scenario_urgency: str, scenario: ClinicalScenario = None) -> float:
        """
        紧急程度匹配（支持别名）

        Args:
            patient_urgency: 患者紧急程度
            scenario_urgency: 场景紧急程度要求
            scenario: 临床场景对象（可选，用于从描述中提取紧急程度）

        Returns:
            匹配得分 (0-1)
        """
        if not patient_urgency:
            return 0

        # 如果scenario_urgency为空，尝试从场景描述中提取
        if not scenario_urgency and scenario and scenario.description_zh:
            scenario_urgency = self._extract_urgency_from_description(scenario.description_zh)

        # 如果提取后仍为空，返回默认分数
        if not scenario_urgency:
            return 0

        # 标准化输入
        patient_urgency_norm = patient_urgency.strip().lower()
        scenario_urgency_norm = scenario_urgency.strip().lower()

        # 检查是否匹配任何别名
        for standard_urgency, aliases in self.urgency_mapping.items():
            # 患者紧急程度匹配
            patient_aliases_lower = [alias.lower() for alias in aliases]
            patient_match = patient_urgency_norm in patient_aliases_lower

            # 场景紧急程度要求匹配
            scenario_aliases_lower = [alias.lower() for alias in aliases]
            scenario_match = scenario_urgency_norm in scenario_aliases_lower

            if patient_match and scenario_match:
                return 1.0
            elif scenario_match and standard_urgency == '不限':
                return 1.0

        # 模糊匹配：检查字符串包含关系
        if patient_urgency_norm in scenario_urgency_norm or scenario_urgency_norm in patient_urgency_norm:
            return 0.8

        return 0.0

    def _extract_urgency_from_description(self, description_zh: str) -> str:
        """
        从场景描述中提取紧急程度信息

        Args:
            description_zh: 中文描述

        Returns:
            提取的紧急程度信息字符串
        """
        import re
        import jieba

        if not description_zh:
            return ""

        # 使用正则表达式提取明显的紧急程度信息
        urgency_patterns = [
            r'(危及生命|生命危险|life-threatening|critical condition)',
            r'(紧急|急诊|急症|急性|urgent|emergency|critical|acute)',
            r'(重度|严重|severe)',
            r'(中度|中等|moderate|serious)',
            r'(亚急性|subacute)',
            r'(复发性|复发|反复|recurrent|relapse)',
            r'(常规|慢性|常规检查|mild|chronic|routine)',
            r'(轻微|轻度|mild|minor)',
            r'(不稳定|unstable)',
            r'(稳定|stable)',
            r'(择期|elective)',
            r'(预防性|预防|preventive|prophylactic)',
            r'(筛查|screening)',
            r'(随访|follow-up)',
            r'(康复|康复期|rehabilitation|recovery)',
            r'(终末期|晚期|末期|end-stage|terminal)',
            r'(姑息治疗|姑息|palliative)'
        ]

        for pattern in urgency_patterns:
            matches = re.findall(pattern, description_zh, re.IGNORECASE)
            if matches:
                urgency_char = matches[0]
                if urgency_char in ['危及生命', '生命危险', 'life-threatening', 'critical condition']:
                    return '危及生命'
                elif urgency_char in ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute']:
                    return '紧急'
                elif urgency_char in ['重度', '严重', 'severe']:
                    return '重度'
                elif urgency_char in ['中度', '中等', 'moderate', 'serious']:
                    return '中度'
                elif urgency_char in ['亚急性', 'subacute']:
                    return '亚急性'
                elif urgency_char in ['复发性', '复发', '反复', 'recurrent', 'relapse']:
                    return '复发性'
                elif urgency_char in ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine']:
                    return '常规'
                elif urgency_char in ['轻微', '轻度', 'mild', 'minor']:
                    return '轻微'
                elif urgency_char in ['不稳定', 'unstable']:
                    return '不稳定'
                elif urgency_char in ['稳定', 'stable']:
                    return '稳定'
                elif urgency_char in ['择期', 'elective']:
                    return '择期'
                elif urgency_char in ['预防性', '预防', 'preventive', 'prophylactic']:
                    return '预防性'
                elif urgency_char in ['筛查', 'screening']:
                    return '筛查'
                elif urgency_char in ['随访', 'follow-up']:
                    return '随访'
                elif urgency_char in ['康复', '康复期', 'rehabilitation', 'recovery']:
                    return '康复'
                elif urgency_char in ['终末期', '晚期', '末期', 'end-stage', 'terminal']:
                    return '终末期'
                elif urgency_char in ['姑息治疗', '姑息', 'palliative']:
                    return '姑息治疗'

        # 使用jieba分词并查找紧急程度相关关键词
        words = jieba.cut(description_zh)

        urgency_keywords = {
            '危及生命': ['危及生命', '生命危险', 'life-threatening', 'critical condition'],
            '紧急': ['紧急', '急诊', '急症', '急性', 'urgent', 'emergency', 'critical', 'acute'],
            '重度': ['重度', '严重', 'severe'],
            '中度': ['中度', '中等', 'moderate', 'serious'],
            '亚急性': ['亚急性', 'subacute'],
            '复发性': ['复发性', '复发', '反复', 'recurrent', 'relapse'],
            '常规': ['常规', '慢性', '常规检查', 'mild', 'chronic', 'routine'],
            '轻微': ['轻微', '轻度', 'mild', 'minor'],
            '不稳定': ['不稳定', 'unstable'],
            '稳定': ['稳定', 'stable'],
            '择期': ['择期', 'elective'],
            '预防性': ['预防性', '预防', 'preventive', 'prophylactic'],
            '筛查': ['筛查', 'screening'],
            '随访': ['随访', 'follow-up'],
            '康复': ['康复', '康复期', 'rehabilitation', 'recovery'],
            '终末期': ['终末期', '晚期', '末期', 'end-stage', 'terminal'],
            '姑息治疗': ['姑息治疗', '姑息', 'palliative'],
            '不限': ['不限', '通用', '全部', '所有', 'any', 'all', 'both']
        }

        for word in words:
            word_lower = word.lower()
            for urgency, keywords in urgency_keywords.items():
                if word_lower in [kw.lower() for kw in keywords]:
                    return urgency

        return ""
    
    async def hybrid_rank_scenarios(
        self,
        scenarios: List[Dict[str, Any]],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        top_k: int = 5,
        enable_llm: bool = False
    ) -> List[Dict[str, Any]]:
        """
        混合重排：LLM智能选择 + 规则打分融合
        
        Args:
            scenarios: 候选场景列表（来自混合检索的16条）
            patient_info: 患者基本信息
            clinical_context: 临床上下文
            top_k: 返回的场景数量
            enable_llm: 是否启用LLM选择
            
        Returns:
            混合排序后的场景列表
        """
        llm_results=None
        rule_results=None

        llm_top_k = (top_k + 1) // 2  # 向上取整
        rule_top_k = top_k // 2  # 向下取整
        if not scenarios:
            logger.warning("输入场景为空")
            return []
        if len(scenarios)<top_k:
            top_k=len(scenarios)
        # 深拷贝scenarios，防止并行处理时产生数据冲突
        # 注意：scenario对象本身不拷贝（数据库对象），只拷贝外层字典结构
        scenarios_for_llm = copy.deepcopy(scenarios)
        scenarios_for_rule = copy.deepcopy(scenarios)

        
        # 并行执行LLM和规则排序
        if enable_llm:
            logger.info("🚀 开始并行执行LLM排序和规则排序...")
            llm_task = self.llm_rank_scenarios(
                scenarios_for_llm, patient_info, clinical_context, llm_top_k
            )
            rule_task = self.rule_rank_scenarios(
                scenarios_for_rule, patient_info, clinical_context, rule_top_k
            )

            llm_results, rule_results = await asyncio.gather(
                llm_task, rule_task, return_exceptions=True
            )

            # 异常处理
            if isinstance(llm_results, Exception):
                logger.warning(f"⚠️ LLM排序失败，使用规则排序: {llm_results}")
                llm_results = []
            if isinstance(rule_results, Exception):
                logger.error(f"❌ 规则排序失败: {rule_results}")
                rule_results = []

        logger.info("🔧 仅使用规则排序")
        rule_results = await self.rule_rank_scenarios(
                scenarios, patient_info, clinical_context, top_k
            )
        
        # 去重合并逻辑
        final_scenarios = []
        seen_ids = set()
        
        # # 1. 优先选择LLM结果
        if llm_results:
            for item in llm_results:
                scenario_id = item['scenario'].id
                if scenario_id not in seen_ids:
                    final_scenarios.append(item)
                    seen_ids.add(scenario_id)
            logger.info(f"✅ LLM贡献 {len(llm_results)} 个场景")
        
        # 2. 补充规则排序结果（去重）
        if rule_results:
            for item in rule_results:
                scenario_id = item['scenario'].id
                if scenario_id not in seen_ids and len(final_scenarios) < top_k:
                    final_scenarios.append(item)
                    seen_ids.add(scenario_id)
            llm_nums=len(llm_results) if llm_results else 0
            logger.info(f"🔧 规则补充 {len(final_scenarios) -llm_nums} 个场景")
        
        # 统计信息
        llm_count = len([s for s in final_scenarios if s.get('selection_source_by_llm') == 'LLM'])
        rule_count = len([s for s in final_scenarios if s.get('selection_source_by_rule') == 'Rule'])
        
        logger.info(
            f"🎯 混合排序完成: 总数{len(final_scenarios)}, LLM({llm_count}), 规则({rule_count})"
        )
        
        return final_scenarios[:top_k]

    async def llm_rank_all_scenarios(
            self,
            all_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            strategy: RerankingStrategy,
            min_rating: int = 5,
            max_scenarios: int = 3,
            max_recommendations_per_scenario: int = 2
    ) -> List[Dict[str, Any]]:
        """
        根据策略枚举执行不同的场景和推荐项目处理逻辑
        """
        if not all_scenarios:
            logger.warning("输入场景为空")
            return []

        try:
            # 根据策略执行不同的处理逻辑
            if strategy == RerankingStrategy.NONE:
                return await self._handle_none_strategy(all_scenarios, max_scenarios)
            elif strategy == RerankingStrategy.RULE_ONLY:
                return await self._handle_rule_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.LLM_SCENARIO_ONLY:
                return await self._handle_llm_scenario_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.LLM_RECOMMENDATION_ONLY:
                return await self._handle_llm_recommendation_only_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.RULE_AND_LLM_SCENARIO:
                return await self._handle_rule_and_llm_scenario_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.RULE_AND_LLM_RECOMMENDATION:
                return await self._handle_rule_and_llm_recommendation_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.LLM_SCENARIO_AND_RECOMMENDATION:
                return await self._handle_llm_scenario_and_recommendation_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            elif strategy == RerankingStrategy.ALL:
                return await self._handle_all_strategy(
                    all_scenarios, patient_info, clinical_context,
                    min_rating, max_scenarios, max_recommendations_per_scenario
                )
            else:
                logger.warning(f"未知策略: {strategy}，使用默认处理")
                return all_scenarios[:max_scenarios]

        except Exception as e:
            logger.error(f"处理策略 {strategy} 时发生错误: {e}")
            return []

    # ========== 八种策略的具体实现 ==========

    async def _handle_none_strategy(self, all_scenarios, max_scenarios):
        """策略1: 无重排序，直接返回"""
        logger.info(f"策略1-NONE: 直接返回前{max_scenarios}个场景")
        return all_scenarios[:max_scenarios]

    async def _handle_rule_only_strategy(self, all_scenarios, patient_info, clinical_context,
                                         min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略2: 仅规则重排序"""
        logger.info(f"策略2-RULE_ONLY: 规则重排序{max_scenarios}个场景")

        # 应用规则重排序
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        rule_ranked_scenarios = await self.hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=False
        )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results( rule_ranked_scenarios,patient_info, clinical_context, max_scenarios, max_recommendations_per_scenario)

    async def _handle_llm_scenario_only_strategy(self, all_scenarios, patient_info, clinical_context,
                                                 min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略3: 仅LLM场景重排序"""
        logger.info(f"策略3-LLM_SCENARIO_ONLY: LLM重排序{max_scenarios}个场景")

        # LLM场景重排序
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        llm_ranked_scenarios = await self.llm_rank_scenarios(
            filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios
        )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results(llm_ranked_scenarios,patient_info, clinical_context, max_scenarios, max_recommendations_per_scenario)


    def select_scenarios_for_production(self, all_scenarios, max_scenarios,
                                        patient_id=None):
        """
        生产环境选择策略
        - 如果提供了患者ID，基于患者ID生成种子（保证同一患者结果一致）
        - 否则完全随机（增加多样性）
        """
        top_k_scenarios = all_scenarios

        if len(top_k_scenarios) <= max_scenarios:
            return top_k_scenarios

        if patient_id:
            # 基于患者ID生成确定性但个性化的随机
            seed = self._generate_seed_from_patient(patient_id)
            random.seed(seed)
            return random.sample(top_k_scenarios, max_scenarios)
        else:
            # 完全随机，增加结果多样性
            return random.sample(top_k_scenarios, max_scenarios)

    def _generate_seed_from_patient(self, patient_id):
        """从患者ID生成种子"""
        return hash(patient_id) % 10000
    async def _handle_llm_recommendation_only_strategy(self, all_scenarios, patient_info, clinical_context,
                                                       min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略4: 仅LLM推荐项目重排序"""
        logger.info(f"策略4-LLM_RECOMMENDATION_ONLY: 对前{max_scenarios}个场景进行LLM推荐项目重排序")

        # 先选择前max_scenarios个场景
        ranked_scenarios=all_scenarios[:max_scenarios*3]
        # 获取这些场景的推荐项目
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            ranked_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
            scenario_with_recommendations,
            filter_scenario_with_recommendations,
            max_scenarios
        )
        # 使用自适应引擎进行LLM推荐项目重排序
        recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
            final_scenario_with_recommendations, patient_info, clinical_context,
            max_recommendations_per_scenario, use_adaptive=True
        )

        return recommendations

    async def _handle_rule_and_llm_scenario_strategy(self, all_scenarios, patient_info, clinical_context,
                                                     min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略5: 规则+LLM场景重排序"""
        logger.info(f"策略5-RULE_AND_LLM_SCENARIO: 规则重排序后LLM重排序{max_scenarios}个场景")

        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )
        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]


        ranked_scenarios = await self.hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=True
        )

        # 第二步：LLM场景重排序
        # llm_ranked_scenarios = await self.llm_rank_scenarios(
        #     rule_ranked_scenarios, patient_info, clinical_context, max_scenarios
        # )

        # 获取推荐项目（基于ACR评分）

        # final_scenario_with_recommendations = self._handel_filter_scenario_with_recommendations(
        #     scenario_with_recommendations,
        #     filter_scenario_with_recommendations,
        #     max_scenarios
        # )
        return assemble_database_results(ranked_scenarios, patient_info, clinical_context,
                                         max_scenarios, max_recommendations_per_scenario)

    async def _handle_rule_and_llm_recommendation_strategy(self, all_scenarios, patient_info, clinical_context,
                                                           min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略6: 规则+LLM推荐项目重排序"""
        logger.info(f"策略6-RULE_AND_LLM_RECOMMENDATION: 规则重排序后LLM推荐项目重排序")

        # 第一步：规则重排序
        # 获取这些场景的推荐项目
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        rule_ranked_scenarios = await self.hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=False
        )



        # 第二步：LLM推荐项目重排序
        recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
            rule_ranked_scenarios, patient_info, clinical_context,
            max_recommendations_per_scenario, use_adaptive=True
        )

        return recommendations

    async def _handle_llm_scenario_and_recommendation_strategy(self, all_scenarios, patient_info, clinical_context,
                                                               min_rating, max_scenarios,
                                                               max_recommendations_per_scenario):
        """策略7: LLM场景+推荐项目重排序"""
        logger.info(f"策略7-LLM_SCENARIO_AND_RECOMMENDATION: LLM场景重排序+推荐项目重排序")
        # 先选择前max_scenarios个场景
        ranked_scenarios = all_scenarios
        # 获取所有场景的推荐项目
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            ranked_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations=[ scenario_with_recommendation for scenario_with_recommendation in scenario_with_recommendations if scenario_with_recommendation["recommendations"] ]

        # 构建提示词并检查token数量
        prompt = self._build_comprehensive_prompt_with_grading(
            filter_scenario_with_recommendations, patient_info, clinical_context,
            max_scenarios, max_recommendations_per_scenario
        )

        token_nums = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(prompt)
        threshold = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]

        if token_nums < threshold-200:
            logger.info(f"Token数量({token_nums})小于阈值({threshold})，使用单次LLM调用")
            # 单次LLM调用同时处理场景选择和推荐项目分级
            return await self._llm_recommend_scenarios(
                filter_scenario_with_recommendations, prompt, patient_info,
                max_scenarios, max_recommendations_per_scenario
            )
        else:
            logger.info(f"Token数量({token_nums})超过阈值({threshold})，分开处理场景选择和推荐项目")
            # 分开处理：先LLM场景重排序，再LLM推荐项目重排序
            # 第一步：LLM场景重排序
            llm_ranked_scenarios = await self.llm_rank_scenarios(
                filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios
            )

            # 筛选出对应的推荐数据
            scenarios_id_set = {scenario["scenario_id"] for scenario in llm_ranked_scenarios}
            filtered_scenarios_with_recommends = [
                scenario_rec for scenario_rec in filter_scenario_with_recommendations
                if scenario_rec["scenario_id"] in scenarios_id_set
            ]

            # 第二步：LLM推荐项目重排序
            recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
                filtered_scenarios_with_recommends, patient_info, clinical_context,
                max_recommendations_per_scenario, use_adaptive=True
            )

            return recommendations

    async def _handle_all_strategy(self, all_scenarios, patient_info, clinical_context,
                                   min_rating, max_scenarios, max_recommendations_per_scenario):
        """策略8: 全部启用 - 规则重排序 + LLM场景重排序 + LLM推荐项目重排序"""
        logger.info(f"策略8-ALL: 规则重排序 + LLM场景重排序 + LLM推荐项目重排序")

        # 第一步：规则重排序（宽松一些）
        # 第二步：使用策略7的逻辑处理LLM场景+推荐项目重排序
        scenario_with_recommendations = await self.get_scenarios_with_recommends(
            all_scenarios, max_scenarios, max_recommendations_per_scenario, min_rating
        )

        filter_scenario_with_recommendations = [scenario_with_recommendation for scenario_with_recommendation in
                                                scenario_with_recommendations if
                                                scenario_with_recommendation["recommendations"]]
        ranked_scenarios = await self.hybrid_rank_scenarios(
            scenarios=filter_scenario_with_recommendations,
            patient_info=patient_info,
            clinical_context=clinical_context,
            top_k=max_scenarios,
            enable_llm=True
        )

        # 构建提示词并检查token数量
        # prompt = self._build_comprehensive_prompt_with_grading(
        #     final_scenario_with_recommendations, patient_info, clinical_context,
        #     max_scenarios, max_recommendations_per_scenario
        # )
        #
        # token_nums = self.adaptive_recommendation_engine_service.estimate_tokens_with_tiktoken(prompt)
        # threshold = self.adaptive_recommendation_engine_service.strategy.threshold_config["token_threshold"]

        # if token_nums < threshold:
        #     logger.info(f"Token数量({token_nums})小于阈值({threshold})，使用单次LLM调用")
        #     # 单次LLM调用同时处理场景选择和推荐项目分级
        #     return await self._llm_recommend_scenarios(
        #         final_scenario_with_recommendations, prompt, patient_info,
        #         max_scenarios, max_recommendations_per_scenario
        #     )
        # else:
        # logger.info(f"Token数量({token_nums})超过阈值({threshold})，分开处理场景选择和推荐项目")
            # 分开处理：先LLM场景重排序，再LLM推荐项目重排序
            # 第一步：LLM场景重排序
            # llm_ranked_scenarios = await self.llm_rank_scenarios(
            #     filter_scenario_with_recommendations, patient_info, clinical_context, max_scenarios
            # )
            #
            # # 筛选出对应的推荐数据
            # scenarios_id_set = {scenario["scenario_id"] for scenario in llm_ranked_scenarios}
            # filtered_scenarios_with_recommends = [
            #     scenario_rec for scenario_rec in filter_scenario_with_recommendations
            #     if scenario_rec["scenario_id"] in scenarios_id_set
            # ]

            # 第二步：LLM推荐项目重排序
        recommendations = await self.adaptive_recommendation_engine_service.get_recommendations(
                ranked_scenarios, patient_info, clinical_context,
                max_recommendations_per_scenario, use_adaptive=True
        )

        return recommendations









    # async def _llm_evaluate_single_scenario(
    #             self,
    #             scenario_data: Dict[str, Any],
    #             patient_info: PatientInfo,
    #             clinical_context: ClinicalContext,
    #             top_k: int = 3
    #     ) -> Dict[str, Any]:
    #         """
    #         使用LLM评估单个场景，动态选择top_k个最佳推荐并计算综合评分
    #
    #         Args:
    #             scenario_data: 单个场景数据（包含场景和推荐列表）
    #             patient_info: 患者信息
    #             clinical_context: 临床上下文
    #             top_k: 需要返回的最佳推荐数量
    #
    #         Returns:
    #             包含分级推荐和综合评分的结果
    #         """
    #         scenario = scenario_data['scenario']
    #         recommendations = scenario_data.get('recommendations', [])
    #
    #         if not recommendations:
    #             logger.warning(f"场景{scenario.semantic_id}没有推荐项目")
    #             return None
    #
    #         # 动态调整top_k，确保不超过推荐项目总数
    #         actual_top_k = min(top_k, len(recommendations))
    #
    #         # 安全获取科室名称
    #         try:
    #             panel_name = scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'
    #         except Exception:
    #             panel_name = '未知'
    #
    #         # 构建推荐项目列表文本
    #         recommendation_texts = []
    #         rec_index_map = {}  # {index: rec_data}
    #
    #         for idx, rec_data in enumerate(recommendations, 1):
    #             recommendation = rec_data['recommendation']
    #             procedure = rec_data['procedure']
    #
    #             rec_text = f"""推荐项目{idx}:
    # - 检查名称: {procedure.name_zh}
    # - 检查方式: {procedure.modality or '未知'}
    # - 检查部位: {procedure.body_part or '未知'}
    # - ACR适宜性评分: {recommendation.appropriateness_rating}/9
    # - 适宜性类别: {recommendation.appropriateness_category_zh or '未知'}
    # - 是否使用对比剂: {'是' if procedure.contrast_used else '否'}
    # - 辐射等级: {procedure.radiation_level or '无'}
    # - 推荐理由: {recommendation.reasoning_zh[:100] if recommendation.reasoning_zh else '无'}
    # - 特殊考虑: {recommendation.special_considerations[:100] if recommendation.special_considerations else '无'}
    # - 妊娠安全性: {recommendation.pregnancy_safety or '未知'}
    # """
    #             recommendation_texts.append(rec_text)
    #             rec_index_map[idx] = rec_data
    #
    #         # 构建患者信息
    #         patient_text = f"""患者信息:
    # - 年龄: {patient_info.age}岁
    # - 性别: {patient_info.gender}
    # - 妊娠状态: {patient_info.pregnancy_status or '非妊娠期'}
    # - 过敏史: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
    # - 合并症: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
    # - 检查报告: {patient_info.physical_examination or '无'}
    #
    # 临床信息:
    # - 科室: {clinical_context.department}
    # - 主诉: {clinical_context.chief_complaint}
    # - 既往病史: {clinical_context.medical_history or '无'}
    # - 现病史: {clinical_context.present_illness or '无'}
    # - 主诊断结果: {clinical_context.diagnosis or '待诊断'}
    # - 症状严重程度: {clinical_context.symptom_severity or '未知'}
    # - 症状持续时间: {clinical_context.symptom_duration or '未知'}
    # """
    #
    #         # 构建场景信息
    #         scenario_text = f"""临床场景:
    # - 场景描述: {scenario.description_zh}
    # - 科室: {panel_name}
    # - 适用人群: {scenario.patient_population or '未知'}
    # - 临床背景: {scenario.clinical_context or '未知'}
    # """
    #         recommendation_text = "\n".join(recommendation_texts)
    #
    #         # 构建Prompt - 修改为动态选择top_k
    #         prompt = f"""你是一位经验丰富的临床医生。请根据以下患者信息和临床场景，从推荐项目中选择最适合的{actual_top_k}个检查。
    #
    # {patient_text}
    #
    # {scenario_text}
    #
    # 可选推荐项目：
    # {recommendation_text}
    #
    # 请完成以下任务：
    #
    # 1. **选择最佳推荐**：
    #    - 请选择最适合患者的{actual_top_k}个检查，按优先级从高到低排序
    #    - 考虑因素：ACR评分、临床需求匹配度、患者安全性、检查可行性
    #
    # 2. **综合评分** (0-100分)：
    #    - 评估该场景与患者情况的总体匹配度
    #    - 考虑因素：场景描述匹配、适用人群匹配、科室对应、推荐项目质量
    #
    # 3. **推理说明**（不超过150字）：
    #    - 简要说明选择理由和排序依据
    #    - 解释综合评分的依据
    #
    # 请直接输出JSON格式结果，这是一个例子：
    # {{
    #     "top_k_indices": [1, 3, 2],
    #     "comprehensive_score": 这里是综合的分数,
    #     "reasoning": "简短说明，不超150字"
    # }}
    #
    # 要求：
    # - 必须选择{actual_top_k}个不同的推荐项目索引，按优先级从高到低排列
    # - 综合评分必须为0-100之间的整数
    # - 推理说明必须简洁，严格不超过150个中文字符
    # - 不要输出其他解释文字，只输出JSON，确保JSON完整
    # """
    #
    #         # 调用LLM
    #         response = await self.ai_service._call_llm(prompt)
    #
    #         # 解析JSON结果
    #         import re
    #         import json
    #
    #         json_match = re.search(r'\{.*\}', response, re.DOTALL)
    #         if not json_match:
    #             logger.error(f"场景{scenario.semantic_id} LLM返回格式错误")
    #             return None
    #
    #         try:
    #             result = json.loads(json_match.group())
    #         except json.JSONDecodeError:
    #             logger.error(f"场景{scenario.semantic_id} LLM返回JSON解析错误")
    #             return None
    #
    #         # 提取结果
    #         top_k_indices = result.get('top_k_indices', [])
    #         comprehensive_score = result.get('comprehensive_score', 0)
    #         reasoning = result.get('reasoning', '')
    #
    #         # 验证索引数量和有效性
    #         if len(top_k_indices) < actual_top_k:
    #             logger.warning(f"场景{scenario.semantic_id} LLM返回的推荐数量不足{actual_top_k}个")
    #             # 如果返回数量不足，只取有效的部分
    #             valid_indices = [idx for idx in top_k_indices if idx in rec_index_map]
    #         else:
    #             valid_indices = top_k_indices[:actual_top_k]
    #
    #         if not valid_indices:
    #             logger.warning(f"场景{scenario.semantic_id} LLM未返回有效的推荐项目")
    #             return None
    #
    #         # 构建top_k推荐列表
    #         top_k_recommendations = []
    #         for idx in valid_indices:
    #             if idx in rec_index_map:
    #                 top_k_recommendations.append(rec_index_map[idx])
    #             else:
    #                 logger.warning(f"场景{scenario.semantic_id} 无效的推荐索引: {idx}")
    #
    #         # 构建返回结果 - 修改为动态的top_k结构
    #         return {
    #             'comprehensive_score': comprehensive_score,
    #             'reasoning': reasoning,
    #             'top_k_recommendations': top_k_recommendations,
    #             'recommendation_count': len(top_k_recommendations),
    #             'requested_top_k': actual_top_k,
    #             'scenario_metadata': {
    #                 'scenario_id': scenario.semantic_id,
    #                 'description': scenario.description_zh,
    #                 'llm_rank': scenario_data.get('llm_rank'),
    #                 'selection_source': scenario_data.get('selection_source_by_llm') or scenario_data.get(
    #                     'selection_source_by_rule'),
    #                 'panel': panel_name
    #             }
    #         }
    async def _llm_evaluate_single_scenario(
        self,
        scenario_data: Dict[str, Any],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        使用LLM评估单个场景，选择分级推荐并计算综合评分

        Args:
            scenario_data: 单个场景数据（包含场景和推荐列表）
            patient_info: 患者信息
            clinical_context: 临床上下文

        Returns:
            包含分级推荐和综合评分的结果
        """
        scenario = scenario_data['scenario']
        recommendations = scenario_data.get('recommendations', [])

        if not recommendations:
            logger.warning(f"场景{scenario.semantic_id}没有推荐项目")
            return None

        # 安全获取科室名称
        try:
            panel_name = scenario.panel.name_zh if hasattr(scenario, 'panel') and scenario.panel else '未知'
        except Exception:
            panel_name = '未知'

        # 构建推荐项目列表文本
        recommendation_texts = []
        rec_index_map = {}  # {index: rec_data}

        for idx, rec_data in enumerate(recommendations, 1):
            recommendation = rec_data['recommendation']
            procedure = rec_data['procedure']

            rec_text = f"""推荐项目{idx}:
- 检查名称: {procedure.name_zh}
- 检查方式: {procedure.modality or '未知'}
- 检查部位: {procedure.body_part or '未知'}
- ACR适宜性评分: {recommendation.appropriateness_rating}/9
- 适宜性类别: {recommendation.appropriateness_category_zh or '未知'}
- 是否使用对比剂: {'是' if procedure.contrast_used else '否'}
- 辐射等级: {procedure.radiation_level or '无'}
- 推荐理由: {recommendation.reasoning_zh[:100] if recommendation.reasoning_zh else '无'}
- 特殊考虑: {recommendation.special_considerations[:100] if recommendation.special_considerations else '无'}
- 妊娠安全性: {recommendation.pregnancy_safety or '未知'}
"""
            recommendation_texts.append(rec_text)
            rec_index_map[idx] = rec_data

        # 构建患者信息
        patient_text = f"""患者信息:
- 年龄: {patient_info.age}岁
- 性别: {patient_info.gender}
- 妊娠状态: {patient_info.pregnancy_status or '非妊娠期'}
- 过敏史: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
- 合并症: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
- 检查报告: {patient_info.physical_examination or '无'}

临床信息:
- 科室: {clinical_context.department}
- 主诉: {clinical_context.chief_complaint}
- 既往病史: {clinical_context.medical_history or '无'}
- 现病史: {clinical_context.present_illness or '无'}
- 主诊断结果: {clinical_context.diagnosis or '待诊断'}
- 症状严重程度: {clinical_context.symptom_severity or '未知'}
- 症状持续时间: {clinical_context.symptom_duration or '未知'}
"""

        # 构建场景信息
        scenario_text = f"""临床场景:
- 场景描述: {scenario.description_zh}
- 科室: {panel_name}
- 适用人群: {scenario.patient_population or '未知'}
- 临床背景: {scenario.clinical_context or '未知'}
"""
        recommendation_text="\n".join(recommendation_texts)
        # 构建Prompt
        prompt = f"""你是一位经验丰富的临床医生。请根据以下患者信息和临床场景，从推荐项目中选择最适合的检查。

{patient_text}

{scenario_text}

可选推荐项目：
{recommendation_text}

请完成以下任务：

1. **选择分级推荐**：
   - 极其推荐：选择1项最适合患者的检查（考虑ACR评分、安全性、临床需求）
   - 推荐：选择1项次优选的检查
   - 慎重考虑：选择1项需谨慎考虑的检查（如有风险但可能有用）

2. **综合评分** (0-100分)：
   - 评估该场景与患者情况的总体匹配度
   - 考虑因素：场景描述匹配、适用人群匹配、科室对应、推荐项目质量

3. **推理说明**（不超过150字）：
   - 简要说明选择理由
   - 解释综合评分的依据

请直接输出JSON格式结果，这是一个例子：
{{
    "highly_recommended_index": 1,
    "recommended_index": 3,
    "cautiously_considered_index": 5,
    "comprehensive_score": 85,
    "reasoning": "简短说明，不超150字"
}}

要求：
- 必须选择3个不同的推荐项目索引
- 综合评分必须为0-100之间的整数
- 推理说明必须简洁，严格不超过150个中文字符
- 不要输出其他解释文字，只输出JSON，确保JSON完整
"""

        # 调用LLM
        response = await self.ai_service._call_llm(prompt)

        # 解析JSON结果
        import re
        import json

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            logger.error(f"场景{scenario.semantic_id} LLM返回格式错误")
            return None

        result = json.loads(json_match.group())

        # 提取结果
        highly_recommended_idx = result.get('highly_recommended_index')
        recommended_idx = result.get('recommended_index')
        cautiously_idx = result.get('cautiously_considered_index')
        comprehensive_score = result.get('comprehensive_score', 0)
        reasoning = result.get('reasoning', '')

        # 验证索引
        if not all([highly_recommended_idx, recommended_idx, cautiously_idx]):
            logger.warning(f"场景{scenario.semantic_id} LLM未返回完整的推荐项目")
            return None

        # 构建返回结果
        return {
            'comprehensive_score': comprehensive_score,
            'reasoning': reasoning,
            'recommendations_by_level': {
                'highly_recommended': [rec_index_map.get(highly_recommended_idx)] if highly_recommended_idx in rec_index_map else [],
                'recommended': [rec_index_map.get(recommended_idx)] if recommended_idx in rec_index_map else [],
                'cautiously_considered': [rec_index_map.get(cautiously_idx)] if cautiously_idx in rec_index_map else []
            },
            'scenario_metadata': {
                'scenario_id': scenario.semantic_id,
                'description': scenario.description_zh,
                'llm_rank': scenario_data.get('llm_rank'),
                'selection_source': scenario_data.get('selection_source_by_llm') or scenario_data.get('selection_source_by_rule'),
                'panel': panel_name
            }
        }
    

    
    def _select_best_from_category(
        self,
        category_recommendations: List[Dict],
        patient_info: PatientInfo,
        clinical_context: ClinicalContext,
        top_n: int = 1
    ) -> List[Dict[str, Any]]:
        """
        从某个等级的推荐中选择最佳的N项
        
        选择逻辑：
        1. 过滤不安全的检查（妊娠+辐射、过敏+造影剂）
        2. 按ACR评分排序
        3. 返回top_n
        """
        if not category_recommendations:
            return []
        
        safe_recommendations = []
        
        for rec in category_recommendations:
            # 安全性检查
            is_safe = True
            
            # 妊娠妇女避免辐射
            if patient_info.pregnancy_status and '妊' in patient_info.pregnancy_status:
                if rec['radiation'] and rec['radiation'] != '无' and rec['radiation'] != '低':
                    is_safe = False
            
            # 过敏史避免造影剂
            if patient_info.allergies and '造影剂' in str(patient_info.allergies):
                if rec['contrast'] == '是':
                    is_safe = False
            
            if is_safe:
                safe_recommendations.append(rec)
        
        # 如果所有推荐都被过滤，返回原始列表
        if not safe_recommendations:
            safe_recommendations = category_recommendations
        
        # 按评分排序
        safe_recommendations.sort(key=lambda x: x['rating'], reverse=True)
        
        # 返回top_n的完整数据
        return [rec['rec_data'] for rec in safe_recommendations[:top_n]]

    async def get_scenarios_with_recommends(
            self,
            all_scenarios: List[Dict[str, Any]],
            max_scenarios: int,
            max_recommendations_per_scenario: int,
            min_rating: int = None
    ):
        semaphore = asyncio.Semaphore(8)
        # 设置单个任务的超时时间（例如30秒）
        timeout_duration = 30

        async def get_recommendations_with_semaphore(scenario_data):
            async with semaphore:
                try:
                    scenario = scenario_data['scenario']
                    buffer_multiplier = 2
                    candidate_cap = max(
                        max_recommendations_per_scenario * (max_scenarios + buffer_multiplier),
                        max_recommendations_per_scenario * 2
                    )
                    top_k = min(candidate_cap, 50)

                    # 使用超时包装
                    try:
                        recommendations = await asyncio.wait_for(
                            self.get_scenario_recommendations(
                                scenario_id=scenario.semantic_id,
                                top_k=top_k,
                                min_rating=min_rating or 5
                            ),
                            timeout=timeout_duration
                        )
                        return scenario_data, recommendations
                    except asyncio.TimeoutError:
                        logger.error(f"获取场景 {scenario.semantic_id} 推荐超时，超过 {timeout_duration} 秒")
                        return scenario_data, []

                except Exception as e:
                    logger.error(
                        f"获取场景 {scenario_data.get('scenario', {}).get('semantic_id', 'unknown')} 推荐时发生异常: {e}")
                    return scenario_data, []

        # 创建所有任务
        tasks = [get_recommendations_with_semaphore(scenario_data) for scenario_data in all_scenarios]

        # 并发执行，捕获所有异常
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果，分离正常结果和异常
        scenarios_with_recommendations = []
        successful_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                # 处理异常情况
                failed_count += 1
                logger.error(f"任务执行失败: {result}")
                continue

            scenario_data, recommendations = result
            scenario = scenario_data['scenario']

            scenarios_with_recommendations.append({
                'scenario': scenario,
                'scenario_id':scenario.id,
                'semantic_id': scenario.semantic_id,
                'scenario_description': scenario.description_zh,
                'patient_population': scenario.patient_population,
                'clinical_context': scenario.clinical_context,

                'final_score': scenario_data.get('final_score', 0),
                'semantic_score': scenario_data.get('semantic_score', 0),
                'keyword_score': scenario_data.get('jieba_score', 0),
                'rule_score': scenario_data.get('rule_score', 0),
                'llm_rank': scenario_data.get('llm_rank', None),
                'selection_source': scenario_data.get('selection_source_by_llm', 'Unknown') or scenario_data.get(
                        'selection_source_by_rule', 'Unknown'),

                'llm_reasoning': scenario_data.get('llm_reasoning', ''),
                'recommendations': recommendations,
                'recommendation_count': len(recommendations)
            })
            successful_count += 1

        total_recommendations = sum(len(s['recommendations']) for s in scenarios_with_recommendations)
        logger.info(
            f"📊 共获取 {total_recommendations} 条推荐项目（来自{successful_count}个成功场景，{failed_count}个失败场景）")

        return scenarios_with_recommendations


    async def _llm_recommend_scenarios(self, all_scenarios, prompt,patient_info,max_scenarios,
                                       max_recommendations_per_scenarios):
           # scenario_with_recommendations = await self.get_screnarios_with_recommends(all_scenarios,max_scenarios,max_recommendations_per_scenario, min_rating)
           #开始让llm根据病症做推荐
           # prompt=self._build_comprehensive_prompt_with_grading(scenario_with_recommendations, patient_info, clinical_context,max_scenarios,max_recommendations_per_scenario)
           try:
               # 单次LLM调用
               response = await self.ai_service._call_llm(prompt)

               # 解析JSON结果
               import re
               import json

               json_match = re.search(r'\{.*\}', response, re.DOTALL)
               if not json_match:
                   logger.error("LLM返回格式错误，使用降级方案")
                   return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

               try:
                   result = json.loads(json_match.group())
               except json.JSONDecodeError as e:
                   logger.error(f"JSON解析错误: {e}")
                   return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

               # 处理选中的场景和分级推荐
               selected_scenarios_data = result.get('selected_scenarios', [])
               final_results = []

               for selected_data in selected_scenarios_data:
                   scenario_index = selected_data.get('scenario_index')
                   scenario_id = selected_data.get('scenario_id')
                   grading_data = selected_data.get('recommendation_grades', {})

                   # 验证场景索引
                   if not (1 <= scenario_index <= len(all_scenarios)):
                       logger.warning(f"无效的场景索引: {scenario_index}")
                       continue

                   original_scenario_data = all_scenarios[scenario_index - 1]
                   original_recommendations = original_scenario_data.get('recommendations', [])
                   scenario = original_scenario_data['scenario']

                   # 按推荐等级组织推荐项目
                   graded_recommendations = {
                       "highly_recommended": [],
                       "recommended": [],
                       "less_recommended": []
                   }

                   # 处理各等级推荐项目
                   recommendation_levels = [
                       ('highly_recommended', '极其推荐'),
                       ('recommended', '推荐'),
                       ('less_recommended', '不太推荐')
                   ]

                   for level_key, level_zh in recommendation_levels:
                       for rec_idx in grading_data.get(level_key, []):
                           if 1 <= rec_idx <= len(original_recommendations):
                               rec_data = original_recommendations[rec_idx - 1].copy()
                               rec_data['recommendation_level'] = level_key
                               rec_data['recommendation_level_zh'] = level_zh

                               # 添加完整的检查项目信息
                               procedure = rec_data['procedure']
                               recommendation = rec_data['recommendation']

                               # 构建详细的检查项目信息
                               rec_data['procedure_details'] = {
                                   'semantic_id': procedure.semantic_id,
                                   'name_zh': procedure.name_zh,
                                   'name_en': procedure.name_en,
                                   'modality': procedure.modality,
                                   'body_part': procedure.body_part,
                                   'contrast_used': procedure.contrast_used,
                                   'radiation_level': procedure.radiation_level,
                                   'exam_duration': procedure.exam_duration,
                                   'preparation_required': procedure.preparation_required,
                                   'standard_code': procedure.standard_code,
                                   'description_zh': procedure.description_zh
                               }

                               # 构建详细的推荐信息
                               rec_data['recommendation_details'] = {
                                   'appropriateness_rating': recommendation.appropriateness_rating,
                                   'appropriateness_category_zh': recommendation.appropriateness_category_zh,
                                   'evidence_level': recommendation.evidence_level,
                                   'consensus_level': recommendation.consensus_level,
                                   'adult_radiation_dose': recommendation.adult_radiation_dose,
                                   'pediatric_radiation_dose': recommendation.pediatric_radiation_dose,
                                   'pregnancy_safety': recommendation.pregnancy_safety,
                                   'contraindications': recommendation.contraindications,
                                   'reasoning_zh': recommendation.reasoning_zh,
                                   'special_considerations': recommendation.special_considerations
                               }

                               graded_recommendations[level_key].append(rec_data)
                           else:
                               logger.warning(f"场景{scenario_index}的无效{level_zh}索引: {rec_idx}")

                   # 构建返回结果
                   final_results.append({
                       'comprehensive_score': selected_data.get('comprehensive_score', 0),
                       'scenario_reasoning': selected_data.get('scenario_reasoning', ''),
                       'grading_reasoning': selected_data.get('grading_reasoning', ''),
                       'overall_reasoning': result.get('overall_reasoning', ''),
                       'graded_recommendations': graded_recommendations,
                       'recommendation_summary': {
                           'highly_recommended_count': len(graded_recommendations['highly_recommended']),
                           'recommended_count': len(graded_recommendations['recommended']),
                           'less_recommended_count': len(graded_recommendations['less_recommended']),
                           'total_recommendations': len(original_recommendations)
                       },
                       'scenario_metadata': {
                           'scenario_id': scenario_id or scenario.semantic_id,
                           'description': scenario.description_zh,
                           'panel': scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知',
                           'patient_population': scenario.patient_population,
                           'clinical_context': scenario.clinical_context,
                           'original_index': scenario_index
                       }
                   })

               # 按综合评分排序
               final_results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

               # 记录详细的分级统计
               logger.info(f"✅ 单次LLM调用完成，选出{len(final_results)}个最佳场景")
               for idx, result in enumerate(final_results, 1):
                   summary = result['recommendation_summary']
                   metadata = result['scenario_metadata']
                   logger.info(
                       f"  场景#{idx}: {metadata['description'][:50]}... | "
                       f"评分={result['comprehensive_score']} | "
                       f"分级[极其:{summary['highly_recommended_count']}/"
                       f"推荐:{summary['recommended_count']}/"
                       f"不太:{summary['less_recommended_count']}]"
                   )

               return final_results

           except Exception as e:
            logger.error(f"❌ 综合场景分级筛选失败: {str(e)}", exc_info=True)
            return self._fallback_comprehensive_selection_with_grading(all_scenarios, max_scenarios, patient_info)

    def _fallback_comprehensive_selection_with_grading(
            self,
            all_scenarios: List[Dict[str, Any]],
            max_scenarios: int,
            patient_info: PatientInfo
    ) -> List[Dict[str, Any]]:
        """降级方案：基于完整字段信息进行智能分级"""

        scored_scenarios = []

        for scenario_data in all_scenarios:
            recommendations = scenario_data.get('recommendations', [])
            if not recommendations:
                continue

            scenario = scenario_data['scenario']

            # 智能分级：考虑ACR评分 + 安全性 + 临床匹配度
            highly_recommended = []
            recommended = []
            less_recommended = []

            for rec_data in recommendations:
                recommendation = rec_data['recommendation']
                procedure = rec_data['procedure']
                acr_rating = recommendation.appropriateness_rating

                # 安全性检查
                safety_issues = []

                # 妊娠安全性检查
                if patient_info.pregnancy_status and patient_info.pregnancy_status != '非妊娠期':
                    if recommendation.pregnancy_safety and '禁忌' in recommendation.pregnancy_safety:
                        safety_issues.append("妊娠禁忌")

                # 辐射安全性考虑
                if procedure.radiation_level and procedure.radiation_level in ['高', '中']:
                    safety_issues.append(f"辐射{procedure.radiation_level}")

                # 禁忌症检查
                if recommendation.contraindications:
                    safety_issues.append("存在禁忌症")

                # 基于ACR评分和安全问题的分级逻辑
                if acr_rating >= 7 and not safety_issues:
                    level = 'highly_recommended'
                    level_zh = '极其推荐'
                    highly_recommended.append(rec_data)
                elif acr_rating >= 4 and len(safety_issues) <= 1:
                    level = 'recommended'
                    level_zh = '推荐'
                    recommended.append(rec_data)
                else:
                    level = 'less_recommended'
                    level_zh = '不太推荐'
                    less_recommended.append(rec_data)

                # 添加分级信息到副本
                rec_data_copy = rec_data.copy()
                rec_data_copy['recommendation_level'] = level
                rec_data_copy['recommendation_level_zh'] = level_zh
                rec_data_copy['safety_issues'] = safety_issues

            # 计算综合评分（基于高推荐项目比例和ACR平均分）
            if recommendations:
                highly_ratio = len(highly_recommended) / len(recommendations)
                avg_acr = sum(rec['recommendation'].appropriateness_rating for rec in recommendations) / len(
                    recommendations)
                comprehensive_score = int((highly_ratio * 0.7 + avg_acr / 9 * 0.3) * 100)
            else:
                comprehensive_score = 0

            scored_scenarios.append({
                'comprehensive_score': comprehensive_score,
                'scenario_reasoning': '基于ACR评分和安全性的降级分级',
                'grading_reasoning': f'ACR≥7且无安全问题:极其推荐; ACR4-6且安全問題≤1:推荐; 其他:不太推荐',
                'overall_reasoning': 'LLM调用失败，使用智能降级分级方案',
                'graded_recommendations': {
                    'highly_recommended': highly_recommended,
                    'recommended': recommended,
                    'less_recommended': less_recommended
                },
                'recommendation_summary': {
                    'highly_recommended_count': len(highly_recommended),
                    'recommended_count': len(recommended),
                    'less_recommended_count': len(less_recommended),
                    'total_recommendations': len(recommendations)
                },
                'scenario_metadata': {
                    'scenario_id': scenario.semantic_id,
                    'description': scenario.description_zh,
                    'panel': getattr(scenario.panel, 'name_zh', '未知'),
                    'patient_population': scenario.patient_population,
                    'fallback_used': True
                }
            })

        # 按评分排序
        scored_scenarios.sort(key=lambda x: x['comprehensive_score'], reverse=True)
        return scored_scenarios[:max_scenarios]
















    def build_patient_context(self,patient_info: PatientInfo) -> str:
            """构建患者信息"""
            # 患者和临床信息
            patient_context = f"""
             ## 患者基本信息
             - **年龄**: {patient_info.age}岁
             - **性别**: {patient_info.gender}
             - **妊娠状态**: {patient_info.pregnancy_status or '非妊娠期'}
             - **过敏史**: {', '.join(patient_info.allergies) if patient_info.allergies else '无'}
             - **合并症**: {', '.join(patient_info.comorbidities) if patient_info.comorbidities else '无'}
             - **体格检查**: {patient_info.physical_examination or '无'}"""
            return patient_context
    def build_clinical_context(self,clinical_context: ClinicalContext) -> str:
             """构建临床信息"""
             ## 临床上下文
             clinical_context_content=f"""
             ### 临床信息
             - **就诊科室**: {clinical_context.department}
             - **主诉**: {clinical_context.chief_complaint}
             - **既往病史**: {clinical_context.medical_history or '无'}
             - **现病史**: {clinical_context.present_illness or '无'}
             - **主诊断**: {clinical_context.diagnosis or '待诊断'}
             - **症状严重程度**: {clinical_context.symptom_severity or '未知'}
             - **症状持续时间**: {clinical_context.symptom_duration or '未知'}
             """
             return clinical_context_content

    def build_scenarios_with_recommend(self,all_scenarios:List[Dict[str, Any]]):
        # 所有场景和推荐项目（利用完整字段信息）
        scenarios_text = "## 可选临床场景及推荐项目\n\n"

        for scenario_idx, scenario_data in enumerate(all_scenarios, 1):
            scenario = scenario_data['scenario']
            recommendations = scenario_data.get('recommendations', [])

            scenarios_text += f"### 场景{scenario_idx}: {scenario.description_zh}\n"
            scenarios_text += f"- **场景ID**: {scenario.semantic_id}\n"
            scenarios_text += f"- **适用科室**: {scenario.panel.name_zh if hasattr(scenario, 'panel') else '未知'}\n"
            scenarios_text += f"- **适用人群**: {scenario.patient_population or '未知'}\n"
            scenarios_text += f"- **临床背景**: {scenario.clinical_context or '无'}\n\n"

            if not recommendations:
                scenarios_text += "  暂无推荐项目\n\n"
                continue

            scenarios_text += "#### 推荐项目清单:\n"
            for rec_idx, rec_data in enumerate(recommendations, 1):
                recommendation = rec_data['recommendation']
                procedure = rec_data['procedure']

                # 检查项目基本信息
                scenarios_text += f"{rec_idx}. **{procedure.name_zh}** ({procedure.name_en})\n"

                # 检查技术细节
                tech_details = []
                if procedure.modality:
                    tech_details.append(f"检查方式: {procedure.modality}")
                if procedure.body_part:
                    tech_details.append(f"检查部位: {procedure.body_part}")
                if procedure.exam_duration:
                    tech_details.append(f"检查时长: {procedure.exam_duration}分钟")
                # if tech_details:
                #     scenarios_text += f"   - 技术细节: {', '.join(tech_details)}\n"

                # 安全性和准备信息
                safety_info = []
                if procedure.contrast_used:
                    safety_info.append("使用对比剂")
                if procedure.radiation_level:
                    safety_info.append(f"辐射等级: {procedure.radiation_level}")
                if procedure.preparation_required:
                    safety_info.append("需要准备")
                if safety_info:
                    scenarios_text += f"   - 安全信息: {', '.join(safety_info)}\n"

                # ACR推荐信息
                scenarios_text += f"   - **ACR适宜性评分**: {recommendation.appropriateness_rating}/9\n"
                if recommendation.appropriateness_category_zh:
                    scenarios_text += f"   - 适宜性类别: {recommendation.appropriateness_category_zh}\n"

                # 证据和共识
                evidence_info = []
                if recommendation.evidence_level:
                    evidence_info.append(f"证据强度: {recommendation.evidence_level}")
                # if recommendation.consensus_level:
                #     evidence_info.append(f"共识水平: {recommendation.consensus_level}")
                # if recommendation.median_rating:
                #     evidence_info.append(f"中位数评分: {recommendation.median_rating}")
                # if evidence_info:
                #     scenarios_text += f"   - 证据质量: {', '.join(evidence_info)}\n"

                # 辐射剂量信息
                dose_info = []
                if recommendation.adult_radiation_dose:
                    dose_info.append(f"成人剂量: {recommendation.adult_radiation_dose}")
                if recommendation.pediatric_radiation_dose:
                    dose_info.append(f"儿童剂量: {recommendation.pediatric_radiation_dose}")
                if dose_info:
                    scenarios_text += f"   - 辐射剂量: {', '.join(dose_info)}\n"

                # 安全性信息
                safety_info = []
                if recommendation.pregnancy_safety:
                    safety_info.append(f"妊娠安全: {recommendation.pregnancy_safety}")
                if recommendation.contraindications:
                    contra = recommendation.contraindications[:80] + "..." if len(
                        recommendation.contraindications) > 80 else recommendation.contraindications
                    safety_info.append(f"禁忌症: {contra}")
                if safety_info:
                    scenarios_text += f"   - 安全考虑: {', '.join(safety_info)}\n"

                # 推荐理由
                if recommendation.reasoning_zh:
                    reasoning = recommendation.reasoning_zh[:50] + "..." if len(
                        recommendation.reasoning_zh) > 50 else recommendation.reasoning_zh
                    scenarios_text += f"   - 推荐理由: {reasoning}\n"
                #
                # # 特殊考虑
                if recommendation.special_considerations:
                    special = recommendation.special_considerations[:80] + "..." if len(
                        recommendation.special_considerations) > 80 else recommendation.special_considerations
                    scenarios_text += f"   - 特殊考虑: {special}\n"
                #
                # # 标准编码（如有）
                # code_info = []
                # if procedure.standard_code:
                #     code_info.append(f"标准码: {procedure.standard_code}")
                # if procedure.icd10_code:
                #     code_info.append(f"ICD10: {procedure.icd10_code}")
                # if procedure.cpt_code:
                #     code_info.append(f"CPT: {procedure.cpt_code}")
                # if code_info:
                #     scenarios_text += f"   - 标准编码: {', '.join(code_info)}\n"

                scenarios_text += "\n"

            scenarios_text += "---\n\n"
        return scenarios_text
    def build_task_instruction(self,**kwargs):
        # 任务指令
        all_scenarios=kwargs.get('all_scenarios')
        max_scenarios = kwargs.get('max_scenarios')
        max_recommendations_per_scenario=kwargs.get('max_recommendations_per_scenario')
        task_instruction = f"""
            ## 任务说明

            作为经验丰富的临床医生，请根据患者信息和临床上下文，完成以下**两级智能筛选**：

            ### 第一级：场景筛选
            从{len(all_scenarios)}个临床场景中选择最相关的**{max_scenarios}个场景**，按临床优先级排序。

            ### 第二级：推荐项目三级分级评估
            对每个选中场景的所有推荐项目，进行**三级推荐等级划分**：

            - **极其推荐 (Highly Recommended)**: 评分高，证据充分，与患者情况完美匹配，安全性和诊断价值俱佳，无明显禁忌
            - **推荐 (Recommended)**: 评分中等，临床适用性良好，风险收益比合理，可能存在轻微限制
            - **不太推荐 (Less Recommended)**: 评分低，或存在安全隐患，或有明确禁忌症，或与当前临床需求匹配度不高
            ##注意
              - 每个场景的推荐项目不能超过{max_recommendations_per_scenario}个。
            ## 输出格式
            请严格按以下JSON格式输出，不要额外解释：

            ```json
            {{
                "selected_scenarios": [
                  {{
                      "scenario_index": 这里是索引id(例如：1),
                      "scenario_id": "场景语义ID",
                      "comprehensive_score": "0-100综合评分",
                      "scenario_reasoning": "场景匹配度分析",
                      "recommendation_grades": {{
                          "highly_recommended": [1, 3],
                          "recommended": [2, 4],
                          "less_recommended": [5]
                      }},
                      "grading_reasoning": "分级临床理由"
                  }},
                  {{
                      "scenario_index": 这里是索引id(例如：2),
                      "scenario_id": "场景语义ID",
                      "comprehensive_score": "0-100综合评分",
                      "scenario_reasoning": "场景匹配度分析",
                      "recommendation_grades": {{
                          "highly_recommended": [1, 3],
                          "recommended": [2, 4],
                          "less_recommended": [5]
                      }},
                      "grading_reasoning": "分级临床理由"
                  }},
              ],
                "overall_reasoning": "总体选择策略说明，不超过200字"
            }}"""
        return task_instruction



    def _build_comprehensive_prompt_with_grading(
            self,
            all_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_scenarios: int,
            max_recommendations_per_scenario: int
    ) -> str:
         patient_info_content=self.build_patient_context(patient_info)
         clinical_context_content=self.build_clinical_context(clinical_context)
         scenarios_content=self.build_scenarios_with_recommend(all_scenarios)
         task_instruction=self.build_task_instruction(all_scenarios=all_scenarios,max_scenarios=max_scenarios,max_recommendations_per_scenario=max_recommendations_per_scenario)


         return patient_info_content + "\n" + clinical_context_content + "\n" +scenarios_content+"\n"+ task_instruction

    def _handel_filter_scenario_with_recommendations(self, scenario_with_recommendations:List,
                                                     filter_scenario_with_recommendations:List,max_scenarios):

        # 新增：如果过滤后的场景数量不足，从原始场景中补充
        if len(filter_scenario_with_recommendations) < max_scenarios:
            # 从原始场景中找出不在过滤列表中的场景
            filtered_scenario_ids = {scenario["scenario_id"] for scenario in filter_scenario_with_recommendations}
            additional_scenarios = [scenario for scenario in scenario_with_recommendations
                                    if scenario["scenario_id"] not in filtered_scenario_ids]

            # 按原始排序补充到max_scenarios个
            needed_count = max_scenarios - len(filter_scenario_with_recommendations)
            additional_to_add = additional_scenarios[:needed_count]

            # 合并列表（过滤场景在前，补充场景在后）
            final_scenarios = filter_scenario_with_recommendations + additional_to_add
            logger.info(
                f"过滤场景数量({len(filter_scenario_with_recommendations)})不足，补充了{len(additional_to_add)}个场景")
        else:
            # 如果足够，直接截取前max_scenarios个
            final_scenarios = filter_scenario_with_recommendations[:max_scenarios]
            logger.info(f"过滤场景数量({len(filter_scenario_with_recommendations)})充足，截取前{max_scenarios}个")
        return final_scenarios


























