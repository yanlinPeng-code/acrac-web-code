from abc import ABC

import dashscope
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import async_db_manager

from app.service.rag_v2.ai_service import AiService


class Base(ABC):
    def __init__(self,
                 ):
        self.ai_service = AiService()
        self.tokenizer = dashscope.get_tokenizer("qwen-7b-chat")
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
                'any', 'all', 'both', 'either', '通用', 'common', 'general', "成人", "成年人"
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