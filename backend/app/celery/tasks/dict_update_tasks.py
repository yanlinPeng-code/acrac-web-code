"""
医学词典更新的Celery异步任务
用于将LLM发现的新医学术语持久化到词典文件
"""
from pathlib import Path
from typing import List, Dict
from app.utils.logger.simple_logger import get_logger
from app.config.celery_app import celery_app

logger = get_logger(__name__)


def persist_new_medical_terms(new_terms: List[str], category: str = "symptoms"):
    """
    将新发现的医学术语持久化到词典文件
    
    这是一个同步函数，会被Celery任务包装
    
    Args:
        new_terms: 新发现的医学术语列表
        category: 词典分类（symptoms, diseases等）
    
    Returns:
        成功添加的术语数量
    """
    try:
        # 获取词典文件路径
        project_root = Path(__file__).parent.parent.parent
        dict_file_map = {
            'symptoms': 'medical_symptoms.txt',
            'diseases': 'medical_diseases.txt',
            'treatments': 'medical_treatments.txt',
            'examinations': 'medical_examinations.txt',
            'anatomy': 'medical_anatomy.txt',
            'drugs': 'medical_drugs.txt'
        }
        
        filename = dict_file_map.get(category, 'medical_symptoms.txt')
        file_path = project_root / "dict" / filename
        
        # 确保文件存在
        if not file_path.exists():
            logger.warning(f"词典文件不存在: {file_path}，将创建新文件")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        # 读取现有词汇（去重）
        existing_terms = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                term = line.strip()
                if term and not term.startswith('#'):
                    existing_terms.add(term)
        
        # 过滤掉已存在的词汇
        truly_new_terms = [term for term in new_terms if term not in existing_terms]
        
        if not truly_new_terms:
            logger.info("所有术语已存在于词典中，无需更新")
            return 0
        
        # 追加新词汇到文件末尾
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write('\n# === LLM动态发现的术语 ===\n')
            for term in truly_new_terms:
                f.write(f'{term}\n')
        
        logger.info(f"✅ 成功将 {len(truly_new_terms)} 个新术语追加到 {filename}")
        return len(truly_new_terms)
        
    except Exception as e:
        logger.error(f"❌ 持久化医学术语失败: {e}")
        return 0


@celery_app.task(name="dict_update.persist_new_medical_terms", bind=True, max_retries=3)
def persist_new_medical_terms_async(self, new_terms: List[str], category: str = "symptoms"):
    """
    Celery异步任务：持久化新医学术语
    
    Args:
        new_terms: 新发现的医学术语列表
        category: 词典分类
    
    Returns:
        成功添加的术语数量
    """
    try:
        logger.info(f"🔄 Celery任务开始：持久化 {len(new_terms)} 个新术语到 {category} 词典")
        result = persist_new_medical_terms(new_terms, category)
        logger.info(f"✅ Celery任务完成：成功添加 {result} 个术语")
        return result
    except Exception as exc:
        logger.error(f"❌ Celery任务失败: {exc}")
        # 重试机制：指数退避，最多重试3次
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="dict_update.batch_persist_by_category", bind=True)
def batch_persist_by_category_async(self, new_terms: List[str]) -> Dict[str, int]:
    """
    Celery异步任务：批量持久化，自动分类
    
    Args:
        new_terms: 新发现的医学术语列表
    
    Returns:
        各类别成功添加的术语数量
    """
    try:
        logger.info(f"🔄 Celery任务开始：批量持久化 {len(new_terms)} 个新术语")
        results = batch_persist_by_category(new_terms)
        total = sum(results.values())
        logger.info(f"✅ Celery任务完成：总计添加 {total} 个术语，详情: {results}")
        return results
    except Exception as exc:
        logger.error(f"❌ Celery任务失败: {exc}")
        raise


def classify_medical_term(term: str) -> str:
    """
    智能分类医学术语到对应的词典类别
    
    Args:
        term: 医学术语
    
    Returns:
        词典类别（symptoms/diseases等）
    """
    # 疾病关键字
    disease_keywords = ['病', '炎', '癌', '瘤', '综合征', '症', '梗死', '栓塞', '衰竭', '结核']
    # 症状关键字
    symptom_keywords = ['痛', '热', '咳', '吐', '泻', '肿', '胀', '晕', '麻', '痒', '出血', '困难']
    # 检查关键字
    exam_keywords = ['CT', 'MRI', 'X线', '超声', '心电图', '造影', '镜', '检查', '血常规']
    # 治疗关键字
    treatment_keywords = ['术', '治疗', '手术', '化疗', '放疗', '移植']
    
    # 优先匹配疾病
    if any(kw in term for kw in disease_keywords):
        return 'diseases'
    # 其次匹配症状
    elif any(kw in term for kw in symptom_keywords):
        return 'symptoms'
    # 检查项目
    elif any(kw in term for kw in exam_keywords):
        return 'examinations'
    # 治疗方法
    elif any(kw in term for kw in treatment_keywords):
        return 'treatments'
    # 默认归类为症状
    else:
        return 'symptoms'


def batch_persist_by_category(new_terms: List[str]) -> Dict[str, int]:
    """
    批量持久化，自动分类到不同词典文件
    
    Args:
        new_terms: 新发现的医学术语列表
    
    Returns:
        各类别成功添加的术语数量
    """
    from collections import defaultdict
    
    # 按类别分组
    categorized_terms = defaultdict(list)
    for term in new_terms:
        category = classify_medical_term(term)
        categorized_terms[category].append(term)
    
    # 分别持久化
    results = {}
    for category, terms in categorized_terms.items():
        count = persist_new_medical_terms(terms, category)
        results[category] = count
        logger.info(f"类别 {category}: 添加 {count} 个术语")
    
    return results
