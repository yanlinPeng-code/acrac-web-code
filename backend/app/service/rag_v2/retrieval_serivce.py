import asyncio

import time
from typing import Optional, Dict, Any, List

from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext, SearchStrategy
from app.service.rag_v2.base import Base
from app.service.rag_v2.retrieval.keyword_retrieval import KeywordRetrieval
from app.service.rag_v2.retrieval.vector_retrieval import VectorRetrieval

from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)

class RetrievalService(Base):

    def __init__(self):
        super().__init__()
        self.keyword_retrieval=KeywordRetrieval()
        self.vector_retrieval=VectorRetrieval()
    async def retrieve_clinical_scenarios(
            self,
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            search_strategy: Optional[SearchStrategy] = None,
            top_k: int = 16,
            similarity_threshold: float = 0.6,  # 相似度阈值
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
        # if standard_query:
        #     logger.info("命中已经标准化query")
        #     standardized_query=standard_query
        # 生成缓存键（基于患者信息和临床上下文）
        # cache_key = await self._generate_cache_key(patient_info, clinical_context)
        #
        # #尝试从Redis获取缓存的标准化查询
        # cached_query = await self._get_cached_standardized_query(cache_key)
        #
        # if cached_query:
        #     logger.info(f"从缓存获取标准化查询: {cached_query}")
        #     standardized_query = cached_query
        # else:
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
        logger.info("未命中标准化query,正在生成....")
        if patient_info.gender in self.gender_mapping["男性"]:
            standardized_query = f"{patient_info.age}岁,{patient_info.gender},{clinical_context.chief_complaint}"
        else:
            standardized_query = f"{patient_info.age}岁,{patient_info.gender},{patient_info.pregnancy_status},{clinical_context.chief_complaint}"
        # ========== 阶段2: 并行检索（使用asyncio.gather） ==========
        top_p = top_k  # 中间候选集大小

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
            self.keyword_retrieval.aretrieval(
                standardized_query,
                medical_dict,
                top_p=top_p,
                top_k=top_k
            ),
            # 2b. 语义向量检索
            self.vector_retrieval.aretrieval(
                standardized_query,
                patient_info,
                clinical_context,
                # embedding_model,
                top_p=top_p,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            ),
            # 3.基于langchain封装的vector_store作最大边沿检索
            self.vector_retrieval.aretrieval_mmr(
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
        merged_results = self._merge_and_score_v3(
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
