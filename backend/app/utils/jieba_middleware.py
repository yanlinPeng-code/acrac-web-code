"""
医学词典加载工具
支持从外部文件加载医学术语到jieba
"""
import jieba
from pathlib import Path
from typing import List, Set, Optional

from fastapi import FastAPI

class jiebaLoader:
    """医学词典加载器"""
    
    def __init__(self, app: FastAPI,dict_dir: Optional[str] = None,):
        """
        初始化词典加载器
        
        Args:
            dict_dir: 词典文件目录，默认为项目根目录下的dict文件夹
        """
        self.app = app
        if dict_dir is None:
            # 默认词典目录：项目根目录/dict
            project_root = Path(__file__).parent.parent.parent
            self.dict_dir = project_root / "dict"


        else:
            self.dict_dir = Path(dict_dir)
        
        self.loaded_terms: Set[str] = set()
        self.dict_files = {
            'diseases': 'medical_diseases.txt',      # 疾病名称
            'symptoms': 'medical_symptoms.txt',      # 症状体征
            "complications":"medical_complications.txt",#合并症
            "alias":"medical_alias.txt",
            "status":"medical_status.txt",
            'examinations': 'medical_examinations.txt',  # 检查项目
            'treatments': 'medical_treatments.txt',   # 治疗方法
            'anatomy': 'medical_anatomy.txt',        # 解剖位置
            'drugs': 'medical_drugs.txt'             # 药物名称
        }
        self.init_jieba()
    def init_jieba(self):
        """初始化词典加载器"""
        self.load_all_dicts()
        # print(self.get_loaded_terms())
        print(len(self.get_loaded_terms()))
        self.app.state.medical_dict = self.get_loaded_terms()
    
    def load_all_dicts(self) -> int:
        """
        加载所有可用的医学词典
        
        Returns:
            加载的术语总数
        """
        total_loaded = 0
        
        for dict_type, filename in self.dict_files.items():
            file_path = self.dict_dir / filename
            if file_path.exists():
                count = self.load_dict_file(str(file_path))
                print(f"✅ 已加载 {dict_type} 词典: {count} 个术语")
                total_loaded += count
            else:
                print(f"⚠️  词典文件不存在: {filename}")
        
        print(f"\n📚 总计加载 {total_loaded} 个医学术语")
        return total_loaded
    
    def load_dict_file(self, file_path: str, freq: int = 10000, tag: str = 'medical') -> int:
        """
        从文件加载医学词典
        
        Args:
            file_path: 词典文件路径
            freq: 词频（越高优先级越高）
            tag: 词性标签
        
        Returns:
            加载的术语数量
        
        文件格式：
        - 每行一个词
        - 支持注释（#开头的行）
        - 支持空行
        """
        count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # 去除首尾空白
                    term = line.strip()
                    
                    # 跳过空行和注释
                    if not term or term.startswith('#'):
                        continue
                    
                    # 添加到jieba词典
                    jieba.add_word(term, freq=freq, tag=tag)
                    self.loaded_terms.add(term)
                    count += 1

            return count
        
        except Exception as e:
            print(f"❌ 加载词典文件失败 {file_path}: {e}")
            return 0
    
    def load_custom_dict(self, terms: List[str], freq: int = 10000, tag: str = 'medical'):
        """
        加载自定义词汇列表
        
        Args:
            terms: 术语列表
            freq: 词频
            tag: 词性标签
        """
        for term in terms:
            if term and term.strip():
                jieba.add_word(term.strip(), freq=freq, tag=tag)
                self.loaded_terms.add(term.strip())
        
        print(f"✅ 已加载 {len(terms)} 个自定义术语")
    
    def get_loaded_terms(self) -> List[str]:
        """获取已加载的所有术语"""
        return list(self.loaded_terms)
    


# # ========== 全局单例 ==========
# _dict_loader: Optional[MedicalDictLoader] = None
# _medical_dict_loaded: bool = False  # 全局标志：标记词典是否已加载
#
#
# def get_dict_loader() -> MedicalDictLoader:
#     """获取全局词典加载器单例"""
#     global _dict_loader
#     if _dict_loader is None:
#         _dict_loader = MedicalDictLoader()
#     return _dict_loader
#
#
# def init_medical_dict():
#     """
#     初始化医学词典（在应用启动时调用）
#
#     建议在FastAPI的startup事件中调用：
#
#     @app.on_event("startup")
#     async def startup_event():
#         from app.service.rag_v1.dict_loader import init_medical_dict
#         init_medical_dict()
#     """
#     global _medical_dict_loaded
#
#     # 如果已经加载过，直接返回
#     if _medical_dict_loaded:
#         return 0
#
#     try:
#         loader = get_dict_loader()
#         total = loader.load_all_dicts()
#         _medical_dict_loaded = True
#         return total
#     except Exception as e:
#         print(f"⚠️  医学词典加载失败: {e}")
#         _medical_dict_loaded = True  # 标记为已尝试加载，避免重复尝试
#         return 0
#
#
# def is_dict_loaded() -> bool:
#     """检查词典是否已加载"""
#     global _medical_dict_loaded
#     return _medical_dict_loaded

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    dict_dir = project_root / "dict"
    print(dict_dir)