#!/usr/bin/env python3
"""
Build ACRAC database and vectors from CSV using SiliconFlow embeddings.

Usage examples:
  python backend/scripts/build_acrac_from_csv_siliconflow.py build --csv-file ../../ACR_data/ACR_final.csv
  python backend/scripts/build_acrac_from_csv_siliconflow.py verify

Environment variables:
  PGHOST (default: localhost)
  PGPORT (default: 5432)
  PGDATABASE (default: acrac_db)
  PGUSER (default: postgres)
  PGPASSWORD (default: password)
  SILICONFLOW_API_KEY (default: taken from --api-key if provided)
  SILICONFLOW_EMBEDDING_MODEL (default: BAAI/bge-m3)

The schema is aligned with backend ORM models: semantic_id is used as the FK
in clinical_recommendations (VARCHAR) to match runtime queries and services.


  运行方式

  - 构建（创建表+导入+向量+索引+验证）
      - python backend/scripts/build_acrac_from_csv_siliconflow.py build --csv-file ../../ACR_data/ACR_final.csv
  - 仅验证
      - python backend/scripts/build_acrac_from_csv_siliconflow.py verify
  - 可选参数
      - --api-key sk-...（若不传，读取环境变量 SILICONFLOW_API_KEY）
      - --model BAAI/bge-m3（可通过 SILICONFLOW_EMBEDDING_MODEL 配置）
      - --skip-schema（增量导入时跳过建表）

  说明：构建时对 Procedure 的“模态/部位/对比剂”基于名称做规则提取；
  - 模态/部位：允许多值，使用“|”拼接保存（例如 "CT|MRI"、"头部|胸部"）
  - 对比剂：只要出现“增强/ENHANCED/WITH IV/造影/对比”任意正向关键词，即视为 true；出现“平扫/非增强/WITHOUT”等但包含正向关键词时，仍为 true。
  - 辐射等级：严格使用CSV原始列（若存在），不做映射或二次推断；若缺失则置空。






"""

import os
import re
import sys
import argparse
import logging
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np
import requests
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load backend/.env explicitly
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if env_path.exists():
        load_dotenv(str(env_path))
except Exception:
    pass

try:
    from pgvector.psycopg2 import register_vector
    PGVECTOR_AVAILABLE = True
except Exception:
    PGVECTOR_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("acrac_builder")


def norm(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())


class SiliconFlowEmbedder:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, endpoint: Optional[str] = None, allow_random: bool = False):
        # Prefer Ollama base if provided; otherwise SiliconFlow
        base = endpoint or os.getenv("OLLAMA_BASE_URL") or os.getenv("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1"
        self.endpoint = base.rstrip("/")
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        self.model = model or os.getenv("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3")
        self.allow_random = allow_random
        prefers_ollama = ("11434" in self.endpoint) or ("ollama" in self.endpoint.lower())
        if (not prefers_ollama) and (not self.api_key) and (not self.allow_random):
            raise RuntimeError("SILICONFLOW_API_KEY not set. Set OLLAMA_BASE_URL to use local /v1/embeddings, or set ALLOW_RANDOM_EMBEDDINGS=true (not recommended).")
        if (not prefers_ollama) and (not self.api_key) and self.allow_random:
            logger.warning("SILICONFLOW_API_KEY not set. Embeddings will fallback to random vectors (ALLOW_RANDOM_EMBEDDINGS=true)")

    def embed_texts(self, texts: List[str], batch_size: int = 32, timeout: int = 60) -> List[List[float]]:
        if not texts:
            return []
        prefers_ollama = ("11434" in self.endpoint) or ("ollama" in self.endpoint.lower())
        headers = {"Content-Type": "application/json"}
        if (not prefers_ollama) and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        results: List[List[float]] = []
        url = f"{self.endpoint}/embeddings"

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            payload = {"model": self.model, "input": chunk}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
                if resp.status_code != 200:
                    raise RuntimeError(f"SiliconFlow embeddings error {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                # OpenAI-compatible schema: {data: [{embedding:[...]}...]}
                if not isinstance(data, dict) or "data" not in data:
                    raise RuntimeError(f"Unexpected embeddings response schema: {data.keys()}")
                for item in data["data"]:
                    results.append(item["embedding"])  # type: ignore[index]
            except Exception as e:
                logger.error(f"Embedding request failed, fallback to random for current batch: {e}")
                # Fallback preserves downstream flow; dimension guessed from first success or 1024
                dim = len(results[0]) if results else 1024
                results.extend([np.random.rand(dim).tolist() for _ in chunk])

        return results


class ACRACBuilder:
    def __init__(self, db_config: Optional[Dict[str, str]] = None, api_key: Optional[str] = None, model: Optional[str] = None, allow_random: bool = False, embedding_dim: Optional[int] = None):
        self.db_config = db_config or {
            "host": os.getenv("PGHOST", "localhost"),
            "port": os.getenv("PGPORT", "5432"),
            "database": os.getenv("PGDATABASE", "acrac_db"),
            "user": os.getenv("PGUSER", "postgres"),
            "password": os.getenv("PGPASSWORD", "password"),
        }
        self.conn = None
        self.cursor = None

        self.embedder = SiliconFlowEmbedder(api_key=api_key, model=model, allow_random=allow_random)
        # determined on first embed or provided via args/env
        try:
            self.embedding_dim: Optional[int] = int(embedding_dim) if embedding_dim is not None else (int(os.getenv("EMBEDDING_DIM")) if os.getenv("EMBEDDING_DIM") else None)
        except Exception:
            self.embedding_dim = embedding_dim

        self.stats = {
            "panels_created": 0,
            "topics_created": 0,
            "scenarios_created": 0,
            "procedures_created": 0,
            "recommendations_created": 0,
            "vectors_generated": 0,
            "errors": [],
        }

        self.id_counters = {"panel": 0, "topic": 0, "scenario": 0, "procedure": 0, "recommendation": 0}
        self.cache = {"panels": {}, "topics": {}, "scenarios": {}, "procedures": {}}  # name_key -> semantic_id

    # ------------- DB helpers -------------
    def connect(self) -> bool:
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            # Smoke-test the connection first
            self.cursor.execute("SELECT 1")
            self.cursor.fetchone()
            # 尝试注册 pgvector 适配器；若扩展尚未创建，则记录警告但不中断
            if PGVECTOR_AVAILABLE:
                try:
                    register_vector(self.conn)
                except Exception as ve:
                    logger.warning(
                        "pgvector extension not available yet during connect(): %s", ve
                    )
            return True
        except Exception as e:
            logger.error(f"DB connect failed: {e}")
            return False

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    # ------------- Schema -------------
    def create_schema(self) -> bool:
        try:
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            if PGVECTOR_AVAILABLE:
                try:
                    register_vector(self.conn)
                except Exception as ve:
                    logger.warning(f"register_vector failed after enabling vector extension: {ve}")
            # Drop in dependency order
            self.cursor.execute("DROP TABLE IF EXISTS vector_search_logs CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS data_update_history CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS clinical_recommendations CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS procedure_dictionary CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS clinical_scenarios CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS topics CASCADE;")
            self.cursor.execute("DROP TABLE IF EXISTS panels CASCADE;")

            # Embedding dimension: use provided/detected value; fallback to 1024
            dim = self.embedding_dim or 1024

            self.cursor.execute(
                f"""
                CREATE TABLE panels (
                    id SERIAL PRIMARY KEY,
                    semantic_id VARCHAR(20) UNIQUE NOT NULL,
                    name_en VARCHAR(255) NOT NULL,
                    name_zh VARCHAR(255) NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding VECTOR({dim})
                );
                """
            )

            self.cursor.execute(
                f"""
                CREATE TABLE topics (
                    id SERIAL PRIMARY KEY,
                    semantic_id VARCHAR(20) UNIQUE NOT NULL,
                    panel_id INTEGER REFERENCES panels(id) ON DELETE CASCADE,
                    name_en VARCHAR(500) NOT NULL,
                    name_zh VARCHAR(500) NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding VECTOR({dim})
                );
                """
            )

            self.cursor.execute(
                f"""
                CREATE TABLE clinical_scenarios (
                    id SERIAL PRIMARY KEY,
                    semantic_id VARCHAR(20) UNIQUE NOT NULL,
                    panel_id INTEGER REFERENCES panels(id) ON DELETE CASCADE,
                    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
                    description_en TEXT NOT NULL,
                    description_zh TEXT NOT NULL,
                    clinical_context TEXT,
                    patient_population VARCHAR(100),
                    risk_level VARCHAR(50),
                    age_group VARCHAR(50),
                    gender VARCHAR(20),
                    pregnancy_status VARCHAR(50),
                    urgency_level VARCHAR(50),
                    symptom_category VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding VECTOR({dim})
                );
                """
            )

            self.cursor.execute(
                f"""
                CREATE TABLE procedure_dictionary (
                    id SERIAL PRIMARY KEY,
                    semantic_id VARCHAR(20) UNIQUE NOT NULL,
                    name_en VARCHAR(500) NOT NULL,
                    name_zh VARCHAR(500) NOT NULL,
                    modality VARCHAR(50),
                    body_part VARCHAR(100),
                    contrast_used BOOLEAN DEFAULT FALSE,
                    radiation_level VARCHAR(50),
                    exam_duration INTEGER,
                    preparation_required BOOLEAN DEFAULT FALSE,
                    standard_code VARCHAR(50),
                    icd10_code VARCHAR(20),
                    cpt_code VARCHAR(20),
                    description_en TEXT,
                    description_zh TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding VECTOR({dim})
                );
                """
            )

            self.cursor.execute(
                f"""
                CREATE TABLE clinical_recommendations (
                    id SERIAL PRIMARY KEY,
                    semantic_id VARCHAR(50) UNIQUE NOT NULL,
                    scenario_id VARCHAR(20) REFERENCES clinical_scenarios(semantic_id) ON DELETE CASCADE,
                    procedure_id VARCHAR(20) REFERENCES procedure_dictionary(semantic_id) ON DELETE CASCADE,
                    appropriateness_rating INTEGER,
                    appropriateness_category VARCHAR(100),
                    appropriateness_category_zh VARCHAR(100),
                    reasoning_en TEXT,
                    reasoning_zh TEXT,
                    evidence_level VARCHAR(50),
                    median_rating FLOAT,
                    rating_variance FLOAT,
                    consensus_level VARCHAR(50),
                    adult_radiation_dose VARCHAR(50),
                    pediatric_radiation_dose VARCHAR(50),
                    contraindications TEXT,
                    special_considerations TEXT,
                    pregnancy_safety VARCHAR(50),
                    is_generated BOOLEAN DEFAULT FALSE,
                    confidence_score FLOAT DEFAULT 1.0,
                    last_reviewed_date DATE,
                    reviewer_id INTEGER,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding VECTOR({dim}),
                    UNIQUE(scenario_id, procedure_id)
                );
                """
            )

            self.cursor.execute(
                f"""
                CREATE TABLE vector_search_logs (
                    id SERIAL PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    query_type VARCHAR(50),
                    search_vector VECTOR({dim}),
                    results_count INTEGER,
                    search_time_ms INTEGER,
                    user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            self.cursor.execute(
                """
                CREATE TABLE data_update_history (
                    id SERIAL PRIMARY KEY,
                    table_name VARCHAR(50) NOT NULL,
                    record_id VARCHAR(50) NOT NULL,
                    operation VARCHAR(20) NOT NULL,
                    old_data JSONB,
                    new_data JSONB,
                    user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Basic indexes
            index_sqls = [
                "CREATE INDEX idx_panels_semantic_id ON panels (semantic_id);",
                "CREATE INDEX idx_topics_semantic_id ON topics (semantic_id);",
                "CREATE INDEX idx_topics_panel_id ON topics (panel_id);",
                "CREATE INDEX idx_scenarios_semantic_id ON clinical_scenarios (semantic_id);",
                "CREATE INDEX idx_scenarios_panel_topic ON clinical_scenarios (panel_id, topic_id);",
                "CREATE INDEX idx_procedures_semantic_id ON procedure_dictionary (semantic_id);",
                "CREATE INDEX idx_procedures_modality ON procedure_dictionary (modality);",
                "CREATE INDEX idx_recommendations_semantic_id ON clinical_recommendations (semantic_id);",
                "CREATE INDEX idx_recommendations_scenario ON clinical_recommendations (scenario_id);",
                "CREATE INDEX idx_recommendations_procedure ON clinical_recommendations (procedure_id);",
                "CREATE INDEX idx_recommendations_rating ON clinical_recommendations (appropriateness_rating);",
                "CREATE UNIQUE INDEX idx_panels_name_unique ON panels (name_en, name_zh);",
                "CREATE UNIQUE INDEX idx_topics_name_unique ON topics (panel_id, name_en, name_zh);",
                "CREATE UNIQUE INDEX idx_scenarios_desc_unique ON clinical_scenarios (topic_id, description_en, description_zh);",
                "CREATE UNIQUE INDEX idx_procedures_name_unique ON procedure_dictionary (name_en, name_zh);",
            ]
            for sql in index_sqls:
                try:
                    self.cursor.execute(sql)
                except Exception as e:
                    logger.warning(f"Index creation warning: {e}")

            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Create schema failed: {e}")
            self.conn.rollback()
            return False

    def create_vector_indexes(self) -> bool:
        try:
            # Increase memory for index build to reduce failures on larger lists
            # Use a conservative value that typically fits local setups. Users can tune as needed.
            try:
                self.cursor.execute("SET maintenance_work_mem = '256MB';")
            except Exception as e:
                logger.warning(f"SET maintenance_work_mem failed: {e}")

            # 仅为 clinical_scenarios 创建向量索引
            logger.info("仅为 clinical_scenarios 创建向量索引...")
            try:
                sql = (
                    "CREATE INDEX IF NOT EXISTS idx_scenarios_embedding ON clinical_scenarios "
                    "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
                )
                self.cursor.execute(sql)
                self.conn.commit()
                logger.info("clinical_scenarios 向量索引创建成功")
            except Exception as e:
                logger.warning(f"Vector index creation warning on clinical_scenarios: {e}")
                self.conn.rollback()

            try:
                self.cursor.execute("ANALYZE clinical_scenarios;")
                self.cursor.execute("SET ivfflat.probes = 10;")
                self.conn.commit()
            except Exception as e:
                logger.warning(f"Post-index analyze/probes setup warning: {e}")
                self.conn.rollback()
            return True
        except Exception as e:
            logger.error(f"Create vector indexes failed: {e}")
            self.conn.rollback()
            return False

    # ------------- CSV loading -------------
    def load_csv(self, csv_path: str) -> pd.DataFrame:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        # 粗略检测文件BOM, 优先尝试匹配编码
        enc_candidates: List[str] = []
        try:
            with open(csv_path, 'rb') as fh:
                head = fh.read(4)
            if head.startswith(b"\xff\xfe"):
                enc_candidates.extend(["utf-16", "utf-16-le"])
            elif head.startswith(b"\xfe\xff"):
                enc_candidates.extend(["utf-16", "utf-16-be"])
            elif head.startswith(b"\xef\xbb\xbf"):
                enc_candidates.append("utf-8-sig")
        except Exception:
            pass

        # 默认候选编码列表（附带BOM优先项）
        enc_candidates += ["utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-8", "gbk", "gb2312"]

        tried = set()
        last_err: Optional[Exception] = None
        for enc in enc_candidates:
            key = enc.lower()
            if key in tried:
                continue
            tried.add(key)
            for sep in ["\t", ",", ";"]:
                try:
                    df = pd.read_csv(csv_path, encoding=enc, sep=sep, engine='python')
                    if len(df.columns) >= 8:  # 至少应有基础列
                        logger.info(f"CSV read success with encoding={enc} sep='{sep}' rows={len(df)} cols={len(df.columns)}")
                        return df.fillna("")
                except Exception as e:
                    last_err = e
                    continue
        raise ValueError(f"Failed to read CSV, last error: {last_err}")

    def preprocess(self, df: pd.DataFrame):
        # 列名辅助匹配
        def find_col(candidates: List[str]) -> Optional[str]:
            cols_lower = {c.lower(): c for c in df.columns}
            for cand in candidates:
                if cand.lower() in cols_lower:
                    return cols_lower[cand.lower()]
            for k, orig in cols_lower.items():
                if any(cand.lower() in k for cand in candidates):
                    return orig
            return None

        # 统一列名映射（兼容中英文列头）
        column_aliases = {
            'Panel': ['Panel', '学科', '科室'],
            'Panel Translation': ['Panel Translation', '学科翻译', '科室翻译', '科室英文', '学科(英)'],
            'Topic': ['Topic', '主题'],
            'Topic Translation': ['Topic Translation', '主题翻译', '主题英文'],
            'Variant': ['Variant', '临床场景', '场景'],
            'Variant Translation': ['Variant Translation', '临床场景翻译', '场景英文'],
            'Procedure': ['Procedure', '标准检查名称', '检查项目', '推荐检查'],
            'Standardized': ['Standardized', '标准化名称', '标准检查名称', '标准化推荐'],
            'Appropriateness Category': ['Appropriateness Category', '适应性', '类别'],
            'Appropriateness Category Translation': ['Appropriateness Category Translation', '适应性翻译', '适应性英文'],
            'Rating': ['Rating', '评分'],
            'Median': ['Median', '中位数'],
            'Recommendation': ['Recommendation', '推荐理由', '推荐意见'],
            'Recommendation Translation': ['Recommendation Translation', '推荐理由翻译', '推荐意见英文'],
            'SOE': ['SOE', '证据强度', '证据'],
            'Adult RRL': ['Adult RRL', 'Adult Radiation Dose', '成人辐射', '成人RRL'],
            'Peds RRL': ['Peds RRL', '儿童辐射', 'Pediatric RRL'],
        }

        rename_map: Dict[str, str] = {}
        for canon, candidates in column_aliases.items():
            col = find_col(candidates)
            if col and col not in rename_map:
                rename_map[col] = canon

        if rename_map:
            df = df.rename(columns=rename_map)

        # 必需列兜底处理
        if 'Panel' not in df.columns:
            raise ValueError("Missing required column: Panel (e.g. 学科/科室)")
        if 'Panel Translation' not in df.columns:
            df['Panel Translation'] = df['Panel']
        if 'Topic' not in df.columns:
            raise ValueError("Missing required column: Topic (e.g. 主题)")
        if 'Topic Translation' not in df.columns:
            df['Topic Translation'] = df['Topic']
        if 'Variant' not in df.columns:
            raise ValueError("Missing required column: Variant (e.g. 临床场景)")
        if 'Variant Translation' not in df.columns:
            df['Variant Translation'] = df['Variant']
        if 'Procedure' not in df.columns:
            raise ValueError("Missing required column: Procedure (e.g. 标准检查名称)")
        if 'Standardized' not in df.columns:
            df['Standardized'] = df['Procedure']
        if 'Appropriateness Category' not in df.columns:
            df['Appropriateness Category'] = ''
        if 'Appropriateness Category Translation' not in df.columns:
            df['Appropriateness Category Translation'] = df['Appropriateness Category']
        if 'Rating' not in df.columns:
            df['Rating'] = ''
        if 'Median' not in df.columns:
            df['Median'] = ''
        if 'Recommendation' not in df.columns:
            df['Recommendation'] = df['Recommendation Translation'] if 'Recommendation Translation' in df.columns else ''
        if 'Recommendation Translation' not in df.columns:
            df['Recommendation Translation'] = df['Recommendation']
        if 'SOE' not in df.columns:
            df['SOE'] = ''
        if 'Adult RRL' not in df.columns:
            df['Adult RRL'] = ''
        if 'Peds RRL' not in df.columns:
            df['Peds RRL'] = ''

        # 仅辐射等级严格使用CSV；其余字段按规则提取（允许多值）
        radiation_level_col = find_col(["Radiation Level", "RRL Level", "辐射等级", "Adult RRL Level", "Adult Radiation Level"])  # 原样入库（若存在）

        panels: Dict[str, Dict[str, str]] = {}
        topics: Dict[str, Dict[str, str]] = {}
        scenarios: Dict[str, Dict[str, Any]] = {}
        # 按proc_key聚合属性，避免跨行冲突
        procedures: Dict[str, Dict[str, Any]] = {}
        recommendations: List[Dict[str, Any]] = []

        def extract_modalities_and_parts(text: str) -> Tuple[set, set]:
            t = (text or "").upper()
            modality_map = {
                'CT': ['CT'],
                'MRI': ['MR', 'MRI'],
                'US': ['US', 'ULTRASOUND', '超声'],
                'XR': ['XR', 'X-RAY', 'X RAY', 'X光', 'X 线', 'DR', 'CR'],
                'NM': ['NM', 'PET', 'SPECT', '核医'],
                'MG': ['MG', 'MAMMO', '乳腺'],
                'ANGIO': ['DSA', 'ANGIO', '血管造影']
            }
            body_parts = {
                '头部': ['HEAD', 'BRAIN', 'SKULL', '颅', '脑', '头'],
                '颈部': ['NECK', 'CERVICAL', '颈', '颈椎'],
                '胸部': ['CHEST', 'THORAX', 'LUNG', 'CARDIAC', '心', '胸', '肺'],
                '腹部': ['ABDOMEN', 'ABDOMINAL', 'LIVER', 'KIDNEY', '肝', '肾', '腹'],
                '盆腔': ['PELVIS', 'PELVIC', 'BLADDER', 'PROSTATE', '盆', '膀胱', '前列腺'],
                '脊柱': ['SPINE', 'SPINAL', 'VERTEBRA', '脊', '椎'],
                '四肢': ['EXTREMITY', 'ARM', 'LEG', 'LIMB', '肢', '臂', '腿'],
                '乳腺': ['BREAST', 'MAMMARY', '乳腺', '乳房'],
                '血管': ['VASCULAR', 'ARTERY', 'VEIN', '血管', '动脉', '静脉']
            }
            ms, parts = set(), set()
            for m, kws in modality_map.items():
                if any(k in t for k in kws):
                    ms.add(m)
            for name, kws in body_parts.items():
                if any(k in t for k in kws):
                    parts.add(name)
            return ms, parts

        def parse_contrast(text_zh: str, text_en: str) -> Optional[bool]:
            # 规则：只要出现正向关键词即为真；否则若出现明确否定且无正向，则为假；否则None
            t_en = (text_en or '').upper()
            t_zh = str(text_zh or '')
            pos_en = ['WITH CONTRAST', 'W/ CONTRAST', 'WITH IV', 'W/IV', 'CONTRAST-ENHANCED', 'POSTCONTRAST', 'ENHANCED', 'CE']
            pos_zh = ['增强', '造影', '对比']
            neg_en = ['WITHOUT', 'W/O', 'NO CONTRAST', 'NONCONTRAST', 'UNENHANCED', 'PLAIN', 'NON-ENHANCED']
            neg_zh = ['非增强', '平扫', '无对比']
            has_pos = any(k in t_en for k in pos_en) or any(k in t_zh for k in pos_zh)
            if has_pos:
                return True
            has_neg = any(k in t_en for k in neg_en) or any(k in t_zh for k in neg_zh)
            if has_neg:
                return False
            return None

        def infer_pregnancy_and_urgency(desc_en: str, desc_zh: str) -> Tuple[Optional[str], Optional[str]]:
            t_en = (desc_en or '').upper()
            t_zh = str(desc_zh or '')
            preg_keywords = ['孕', '妊娠', '孕妇', '怀孕', '围产期', '产后', 'pREGNAN', 'PREGNANCY']
            urgent_keywords = ['急诊', '急性', '突发', '雷击样', '霹雳样', '急迫', 'EMERGENCY', 'URGENT', 'ACUTE']
            pregnancy_status = '妊娠/围产' if (any(k in t_zh for k in preg_keywords) or any('PREGNANC' in t_en for _ in [0])) else None
            urgency_level = '急诊' if (any(k in t_zh for k in urgent_keywords) or any(k in t_en for k in ['EMERGENCY', 'URGENT', 'ACUTE'])) else None
            return pregnancy_status, urgency_level

        for _, row in df.iterrows():
            panel_key = f"{norm(row['Panel'])}|||{norm(row['Panel Translation'])}"
            if panel_key not in panels:
                panels[panel_key] = {"name_en": row['Panel'], "name_zh": row['Panel Translation']}

            topic_key = f"{panel_key}|||{norm(row['Topic'])}|||{norm(row['Topic Translation'])}"
            if topic_key not in topics:
                topics[topic_key] = {"panel_key": panel_key, "name_en": row['Topic'], "name_zh": row['Topic Translation']}

            scenario_key = f"{topic_key}|||{norm(row['Variant'])}|||{norm(row['Variant Translation'])}"
            if scenario_key not in scenarios:
                preg, urg = infer_pregnancy_and_urgency(row['Variant'], row['Variant Translation'])
                scenarios[scenario_key] = {
                    "panel_key": panel_key,
                    "topic_key": topic_key,
                    "description_en": row['Variant'],
                    "description_zh": row['Variant Translation'],
                    "pregnancy_status": preg,
                    "urgency_level": urg,
                }

            proc_key = f"{norm(row['Procedure'])}|||{norm(row['Standardized'])}"
            if proc_key not in procedures:
                procedures[proc_key] = {
                    "name_en": row['Procedure'],
                    "name_zh": row['Standardized'],
                    # 值集合，后续汇总（允许多值）
                    "_modalities": set(),
                    "_body_parts": set(),
                    "_contrast_flags": set(),
                    "_radiation_levels": set(),
                }
            # 规则提取（从名称中提取，允许多值）
            ms, parts = extract_modalities_and_parts(f"{row['Procedure']} {row['Standardized']}")
            procedures[proc_key]["_modalities"].update(ms)
            procedures[proc_key]["_body_parts"].update(parts)
            # 对比剂（正向关键词优先）
            cv = parse_contrast(row.get('Standardized', ''), row.get('Procedure', ''))
            if cv is not None:
                procedures[proc_key]["_contrast_flags"].add(cv)
            # 辐射等级：仅CSV原始列
            if radiation_level_col:
                rv = row.get(radiation_level_col)
                if isinstance(rv, str) and rv.strip():
                    procedures[proc_key]["_radiation_levels"].add(str(rv).strip())

            # 优先使用CSV中的中文证据强度翻译列（若存在）
            evidence_col = None
            for cand in ["SOE Translation", "SOE_CN", "Evidence Translation", "证据强度(翻译)"]:
                if cand in df.columns:
                    evidence_col = cand
                    break
            ev_val = row.get(evidence_col) if evidence_col else row.get('SOE')

            recommendations.append({
                "scenario_key": scenario_key,
                "procedure_key": proc_key,
                "appropriateness_rating": self._safe_int(row.get('Rating')),
                "appropriateness_category": row.get('Appropriateness Category', ''),
                "appropriateness_category_zh": row.get('Appropriateness Category Translation', ''),
                "reasoning_en": row.get('Recommendation', ''),
                "reasoning_zh": row.get('Recommendation Translation', ''),
                "evidence_level": ev_val or '',
                "median_rating": self._safe_float(row.get('Median')),
                "adult_radiation_dose": row.get('Adult RRL', ''),
                "pediatric_radiation_dose": row.get('Peds RRL', ''),
                "is_generated": self._safe_bool(row.get('Generated')),
            })

        # 汇总同一procedure的属性：若多值冲突则置为None，避免误判
        def join_or_none(values: set) -> Optional[str]:
            vals = [str(v).strip() for v in values if str(v).strip()]
            if not vals:
                return None
            # 去重并保持可读
            uniq = sorted(set(vals))
            return "|".join(uniq)

        procedures_out: List[Dict[str, Any]] = []
        for p in procedures.values():
            # 对比剂合并：若存在True则为True；否则若存在False则False；否则None
            contrast_flag = True if True in p["_contrast_flags"] else (False if False in p["_contrast_flags"] else None)
            out = {
                "name_en": p["name_en"],
                "name_zh": p["name_zh"],
                "modality": join_or_none(p["_modalities"]),
                "body_part": join_or_none(p["_body_parts"]),
                "contrast_used": contrast_flag,
                "radiation_level": join_or_none(p["_radiation_levels"]),
            }
            procedures_out.append(out)

        return {
            "panels": list(panels.values()),
            "topics": list(topics.values()),
            "scenarios": list(scenarios.values()),
            "procedures": procedures_out,
            "recommendations": recommendations,
        }

    # ------------- Build steps -------------
    def build_panels(self, items: List[Dict[str, str]]):
        if not items:
            return
        rows = []
        for it in items:
            self.id_counters["panel"] += 1
            sid = f"P{self.id_counters['panel']:04d}"
            rows.append((sid, it['name_en'], it['name_zh'], True))
            key = f"{norm(it['name_en'])}|||{norm(it['name_zh'])}"
            self.cache['panels'][key] = sid
        sql = """
            INSERT INTO panels (semantic_id, name_en, name_zh, is_active)
            VALUES %s
            ON CONFLICT (name_en, name_zh)
            DO UPDATE SET semantic_id = EXCLUDED.semantic_id, updated_at = CURRENT_TIMESTAMP
            RETURNING id, semantic_id;
        """
        execute_values(self.cursor, sql, rows, fetch=True)
        self.conn.commit()
        self.stats['panels_created'] += len(items)

    def build_topics(self, items: List[Dict[str, str]]):
        for it in items:
            panel_sid = self.cache['panels'][it['panel_key']]
            self.cursor.execute("SELECT id FROM panels WHERE semantic_id = %s", (panel_sid,))
            panel_id = self.cursor.fetchone()[0]
            self.id_counters['topic'] += 1
            sid = f"T{self.id_counters['topic']:04d}"
            self.cursor.execute(
                """
                INSERT INTO topics (semantic_id, panel_id, name_en, name_zh, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (sid, panel_id, it['name_en'], it['name_zh'], True),
            )
            topic_key = f"{it['panel_key']}|||{norm(it['name_en'])}|||{norm(it['name_zh'])}"
            self.cache['topics'][topic_key] = sid
            self.stats['topics_created'] += 1
        self.conn.commit()

    def build_scenarios(self, items: List[Dict[str, Any]]):
        for it in items:
            panel_sid = self.cache['panels'][it['panel_key']]
            topic_sid = self.cache['topics'][it['topic_key']]
            self.cursor.execute("SELECT id FROM panels WHERE semantic_id = %s", (panel_sid,))
            panel_id = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT id FROM topics WHERE semantic_id = %s", (topic_sid,))
            topic_id = self.cursor.fetchone()[0]
            self.id_counters['scenario'] += 1
            sid = f"S{self.id_counters['scenario']:04d}"
            self.cursor.execute(
                """
                INSERT INTO clinical_scenarios
                (semantic_id, panel_id, topic_id, description_en, description_zh, pregnancy_status, urgency_level, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (sid, panel_id, topic_id, it['description_en'], it['description_zh'], it.get('pregnancy_status'), it.get('urgency_level'), True),
            )
            scenario_key = f"{it['topic_key']}|||{norm(it['description_en'])}|||{norm(it['description_zh'])}"
            self.cache['scenarios'][scenario_key] = sid
            self.stats['scenarios_created'] += 1
        self.conn.commit()

    def build_procedures(self, items: List[Dict[str, Any]]):
        for it in items:
            self.id_counters['procedure'] += 1
            sid = f"PR{self.id_counters['procedure']:04d}"
            modality = it.get('modality')
            body_part = it.get('body_part')
            contrast_used = it.get('contrast_used')
            radiation_level = it.get('radiation_level')  # 仅CSV提供
            self.cursor.execute(
                """
                INSERT INTO procedure_dictionary
                (semantic_id, name_en, name_zh, modality, body_part, contrast_used, radiation_level, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    sid,
                    it['name_en'],
                    it['name_zh'],
                    modality,
                    body_part,
                    contrast_used,
                    radiation_level,
                    True,
                ),
            )
            pkey = f"{norm(it['name_en'])}|||{norm(it['name_zh'])}"
            self.cache['procedures'][pkey] = sid
            self.stats['procedures_created'] += 1
        self.conn.commit()

    def build_recommendations(self, items: List[Dict[str, Any]]):
        rows = []
        for it in items:
            s_sid = self.cache['scenarios'].get(it['scenario_key'])
            p_sid = self.cache['procedures'].get(it['procedure_key'])
            if not s_sid or not p_sid:
                continue
            self.id_counters['recommendation'] += 1
            sid = f"CR{self.id_counters['recommendation']:06d}"
            preg = self._assess_pregnancy_safety(it.get('adult_radiation_dose', ''), it.get('reasoning_zh', ''))
            rows.append(
                (
                    sid,
                    s_sid,
                    p_sid,
                    it.get('appropriateness_rating'),
                    it.get('appropriateness_category'),
                    it.get('appropriateness_category_zh'),
                    it.get('reasoning_en'),
                    it.get('reasoning_zh'),
                    it.get('evidence_level'),
                    it.get('median_rating'),
                    it.get('adult_radiation_dose'),
                    it.get('pediatric_radiation_dose'),
                    preg,
                    it.get('is_generated', False),
                    1.0,
                    True,
                )
            )
        if rows:
            sql = """
                INSERT INTO clinical_recommendations
                (semantic_id, scenario_id, procedure_id, appropriateness_rating, appropriateness_category,
                 appropriateness_category_zh, reasoning_en, reasoning_zh, evidence_level, median_rating,
                 adult_radiation_dose, pediatric_radiation_dose, pregnancy_safety, is_generated, confidence_score, is_active)
                VALUES %s
                ON CONFLICT (scenario_id, procedure_id) DO NOTHING;
            """
            execute_values(self.cursor, sql, rows, page_size=1000)
            self.conn.commit()
        self.stats['recommendations_created'] += len(rows)

    # ------------- Embeddings -------------
    def _update_embeddings(self, table: str, id_col: str, text_build_fn, batch: int = 64):
        self.cursor.execute(f"SELECT id FROM {table};")
        ids = [r[0] for r in self.cursor.fetchall()]
        if not ids:
            return
        texts: List[str] = []
        idx_map: List[int] = []
        for pk in ids:
            txt = text_build_fn(pk)
            texts.append(txt)
            idx_map.append(pk)
        embs = self.embedder.embed_texts(texts, batch_size=batch)
        if embs and self.embedding_dim is None:
            self.embedding_dim = len(embs[0])
        # 批量更新向量
        for i, (emb, pk) in enumerate(zip(embs, idx_map)):
            self.cursor.execute(f"UPDATE {table} SET embedding = %s WHERE id = %s;", (emb, pk))
            if i % 100 == 0:  # 每100条提交一次
                self.conn.commit()
        self.conn.commit()
        self.stats['vectors_generated'] += len(embs)

    def generate_all_embeddings(self):
        # 暂时只为 clinical_scenarios 生成 embedding
        # 其他表(panels, topics, procedures, recommendations)暂不生成向量
        logger.info("仅为 clinical_scenarios 生成 embedding，其他表暂时跳过...")
        
        # scenarios (仅包含 panel, topic 和 description_zh,其他结构化信息通过规则过滤)
        def scenario_text(pk: int) -> str:
            self.cursor.execute(
                """
                SELECT s.description_zh, p.name_zh, t.name_zh
                FROM clinical_scenarios s
                JOIN topics t ON s.topic_id = t.id
                JOIN panels p ON s.panel_id = p.id
                WHERE s.id = %s
                """,
                (pk,),
            )
            (d_zh, p_zh, t_zh) = self.cursor.fetchone()
            # 简化的 embedding 文本:仅核心语义信息
            return f"科室: {p_zh} | 主题: {t_zh} | 临床场景: {d_zh}"

        self._update_embeddings("clinical_scenarios", "id", scenario_text)
        logger.info(f"已为 {self.stats['vectors_generated']} 个临床场景生成向量")

    # ------------- Inference helpers -------------
    def _infer_procedure_attributes(self, text: str) -> Dict[str, Any]:
        t = (text or "").upper()
        modality_map = {
            'CT': ['CT'],
            'MRI': ['MR', 'MRI'],
            'US': ['US', 'ULTRASOUND', '超声'],
            'XR': ['XR', 'X-RAY', 'X RAY', 'X光'],
            'NM': ['NM', 'PET', 'SPECT', '核医'],
            'MG': ['MG', 'MAMMO', '乳腺'],
        }
        modality = 'OTHER'
        for m, kws in modality_map.items():
            if any(k in t for k in kws):
                modality = m
                break
        body_parts = {
            '头部': ['HEAD', 'BRAIN', 'SKULL', '头', '脑', '颅'],
            '颈部': ['NECK', 'CERVICAL', '颈', '颈椎'],
            '胸部': ['CHEST', 'THORAX', 'LUNG', 'CARDIAC', '胸', '肺', '心脏'],
            '腹部': ['ABDOMEN', 'ABDOMINAL', 'LIVER', 'KIDNEY', '腹', '肝', '肾'],
            '盆腔': ['PELVIS', 'PELVIC', 'BLADDER', 'PROSTATE', '盆', '膀胱', '前列腺'],
            '脊柱': ['SPINE', 'SPINAL', 'VERTEBRA', '脊', '椎'],
            '四肢': ['EXTREMITY', 'ARM', 'LEG', 'LIMB', '肢', '臂', '腿'],
            '乳腺': ['BREAST', 'MAMMARY', '乳腺', '乳房'],
            '血管': ['VASCULAR', 'ARTERY', 'VEIN', '血管', '动脉', '静脉'],
        }
        part = '其他'
        for k, kws in body_parts.items():
            if any(w in t for w in kws):
                part = k
                break
        # 更精确地识别是否使用对比剂：先匹配“非增强/平扫”等否定关键词，再匹配肯定关键词
        neg_en = ['WITHOUT', 'W/O', 'NO CONTRAST', 'NONCONTRAST', 'NON-CONTRAST', 'UNENHANCED', 'NON ENHANCED', 'NON-ENHANCED', 'PLAIN', 'NATIVE']
        neg_zh = ['平扫', '非增强', '无对比', '不增强', '未增强', '不注射对比剂', '未注射对比剂', '不使用对比剂']
        pos_en = ['WITH CONTRAST', 'W/ CONTRAST', 'WITH IV', 'W/IV', 'CONTRAST-ENHANCED', 'POSTCONTRAST', 'POST-CONTRAST', 'ENHANCED', 'ENHANCEMENT', 'CE']
        pos_zh = ['增强扫描', '对比增强', '增强', '造影', '强化']
        has_neg = any(k in t for k in neg_en) or any(k in (text or '') for k in neg_zh)
        has_pos = any(k in t for k in pos_en) or any(k in (text or '') for k in pos_zh)
        contrast_used = False if has_neg else (True if has_pos else False)
        radiation_level = '无' if modality in ['US', 'MRI'] else ('低' if modality in ['XR', 'MG'] else ('中' if modality in ['CT'] else ('高' if modality == 'NM' else '未知')))
        return {"modality": modality, "body_part": part, "contrast_used": contrast_used, "radiation_level": radiation_level}

    def _assess_pregnancy_safety(self, radiation_dose: str, reasoning: str) -> str:
        text = f"{radiation_dose} {reasoning}".lower()
        if any(k in text for k in ['contraindicated', 'not recommended', '禁忌', '不推荐', '不建议']):
            return '禁忌'
        if any(k in text for k in ['safe', 'appropriate', '安全', '适宜']):
            return '安全'
        if any(k in text for k in ['caution', 'consider', '谨慎', '考虑']):
            return '谨慎使用'
        return '未评估'

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            return int(float(value)) if value is not None and str(value).strip() else None
        except Exception:
            return None

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            return float(value) if value is not None and str(value).strip() else None
        except Exception:
            return None

    @staticmethod
    def _safe_bool(value) -> bool:
        if value is None:
            return False
        s = str(value).strip().lower()
        return s in ["true", "1", "yes", "y", "t"]

    # ------------- Verify -------------
    def verify(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        tables = ['panels', 'topics', 'clinical_scenarios', 'procedure_dictionary', 'clinical_recommendations']
        for t in tables:
            self.cursor.execute(f"SELECT COUNT(*) FROM {t};")
            info[f"{t}_count"] = self.cursor.fetchone()[0]
            self.cursor.execute(f"SELECT COUNT(embedding) FROM {t};")
            with_emb = self.cursor.fetchone()[0]
            info[f"{t}_embedding_coverage"] = with_emb
        self.cursor.execute(
            """
            SELECT COUNT(*) FROM clinical_recommendations cr
            WHERE cr.scenario_id NOT IN (SELECT semantic_id FROM clinical_scenarios)
               OR cr.procedure_id NOT IN (SELECT semantic_id FROM procedure_dictionary);
            """
        )
        info['orphaned_recommendations'] = self.cursor.fetchone()[0]
        return info


def main():
    parser = argparse.ArgumentParser(description="Build/verify ACRAC DB with SiliconFlow embeddings")
    parser.add_argument("action", choices=["build", "verify", "rebuild"], help="Action to perform")
    parser.add_argument("--csv-file", default="../../ACR_data/ACR_final.csv", help="Path to CSV data file")
    parser.add_argument("--api-key", default="", help="SiliconFlow API key (optional; otherwise use env SILICONFLOW_API_KEY)")
    parser.add_argument("--model", default="BAAI/bge-m3", help="SiliconFlow embedding model id")
    parser.add_argument("--skip-schema", action="store_true", help="Skip schema creation (for incremental runs)")
    parser.add_argument("--allow-random", action="store_true", help="Allow random embeddings if API key missing (not recommended)")
    parser.add_argument("--embedding-dim", type=int, default=None, help="Embedding vector dimension; if omitted, uses EMBEDDING_DIM env or detects from model")
    args = parser.parse_args()

    # If passed explicitly, set env as well
    if args.api_key:
        os.environ.setdefault("SILICONFLOW_API_KEY", args.api_key)
    os.environ.setdefault("SILICONFLOW_EMBEDDING_MODEL", args.model)

    builder = ACRACBuilder(
        api_key=args.api_key or os.getenv("SILICONFLOW_API_KEY"),
        model=args.model,
        allow_random=args.allow_random or os.getenv("ALLOW_RANDOM_EMBEDDINGS","false").lower()=="true",
        embedding_dim=args.embedding_dim
    )
    if not builder.connect():
        return 1
    try:
        if args.action in ["build", "rebuild"]:
            if not args.skip_schema:
                # Detect embedding dimension if not specified
                if builder.embedding_dim is None:
                    try:
                        probe = builder.embedder.embed_texts(["dimension_probe"]) or []
                        if probe and isinstance(probe[0], list):
                            builder.embedding_dim = len(probe[0])
                            os.environ.setdefault("EMBEDDING_DIM", str(builder.embedding_dim))
                            logger.info(f"Detected embedding dimension: {builder.embedding_dim}")
                    except Exception as de:
                        logger.warning(f"Embedding dimension detection failed, fallback to 1024: {de}")
                logger.info(f"Creating schema (dim={builder.embedding_dim or 1024})...")
                if not builder.create_schema():
                    return 1
            logger.info("Loading CSV...")
            df = builder.load_csv(args.csv_file)
            logger.info("Preprocessing...")
            data = builder.preprocess(df)
            logger.info("Building panels...")
            builder.build_panels(data['panels'])
            logger.info("Building topics...")
            builder.build_topics(data['topics'])
            logger.info("Building scenarios...")
            builder.build_scenarios(data['scenarios'])
            logger.info("Building procedures...")
            builder.build_procedures(data['procedures'])
            logger.info("Building recommendations...")
            builder.build_recommendations(data['recommendations'])
            logger.info("Generating embeddings via SiliconFlow...")
            builder.generate_all_embeddings()
            logger.info("Creating vector indexes...")
            builder.create_vector_indexes()
            logger.info("Verifying build...")
            info = builder.verify()
            logger.info(f"Build verification: {info}")
        elif args.action == "verify":
            info = builder.verify()
            logger.info(f"Verification: {info}")
    finally:
        builder.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
