import asyncio
import hashlib
import json
import math
from typing import Optional, List, Dict

from sqlalchemy.orm import selectinload
from sqlmodel import select, and_, or_

from app.config.redis_config import redis_manager
from app.model import ClinicalScenario
from app.service.rag_v2.ai_service import AiService
from app.service.rag_v2.retrieval.base_retrieval import BaseRetrieval
from app.utils.logger.simple_logger import get_logger

logger=get_logger(__name__)
class KeywordRetrieval(BaseRetrieval):


      def __init__(self):
          super().__init__()
          self.ai_service=AiService()
          self.redis_client=redis_manager


      async def aretrieval(self,
                           query_text: str,
                           medical_dict: Optional[List] = None,
                           top_p: int = 50,
                           top_k: int = 10):
          """
                  jieba分词 + 模糊匹配检索（高并发优化：使用独立 session）
                  """
          # 暂时不使用
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
                  'source': "jieba"
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

      def _jieba_tokenize(self, text: str, medical_dict: list, new_item: list = None) -> List[str]:
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
                        "f", "ns", "ad", "q", 'u', 's', 'vd', 'r', 'xc', 't',
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

          all_words = set(builtin_medical_terms)
          for suggest in all_words:
              jieba.suggest_freq(suggest, True)
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

