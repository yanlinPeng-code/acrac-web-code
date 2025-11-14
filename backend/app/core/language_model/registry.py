from typing import Dict, List, Optional
from .models import Model, ModelProvider, ModelCapability, ModelPricing


class ModelRegistry:
    """
    模型注册表类，用于管理所有AI模型的注册、查询和配置。
    
    该类维护了一个模型字典和别名字典，提供了多种方法来获取和操作模型，
    包括按层级、提供商、功能等分类查询模型。
    """
    
    def __init__(self):
        """初始化模型注册表，创建空的模型和别名字典，并初始化预定义模型"""
        self._models: Dict[str, Model] = {}
        self._aliases: Dict[str, str] = {}
        # self.initialize_models()
    
    def initialize_models(self):
        """
        初始化并注册所有预定义的AI模型。
        """
        # 注册 OpenAI GPT-4o
        # self.register(Model(
        #     id="openai/gpt-4o",
        #     name="GPT-4o",
        #     provider=ModelProvider.OPENAI,
        #     aliases=["gpt-4o", "GPT-4o"],
        #     context_window=128_000,
        #     capabilities=[
        #         ModelCapability.CHAT,
        #         ModelCapability.FUNCTION_CALLING,
        #         ModelCapability.VISION,
        #     ],
        #     pricing=ModelPricing(
        #         input_cost_per_million_tokens=5.00,
        #         output_cost_per_million_tokens=15.00
        #     ),
        #     tier_availability=["paid"],
        #     priority=100,
        #     recommended=True,
        #     enabled=True
        # ))

        self.register(Model(
            id="qwen2.5-32b-instruct",
            name="Qwen/Qwen2.5-32B-Instruct",  # 实际API调用名称
            provider=ModelProvider.SILICONFLOW,
            aliases=["qwen2.5-32b-instruct", "通义千问2.5-32b"],
            context_window=128_000,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FUNCTION_CALLING,
            ]
            ,
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.05,
                output_cost_per_million_tokens=0.20
            ),
            tier_availability=["paid"],
            priority=100,
            enabled=True
        )
        )
        
        # 注册 OpenAI GPT-4o-mini
        # self.register(Model(
        #     id="openai/gpt-4o-mini",
        #     name="GPT-4o mini",
        #     provider=ModelProvider.OPENAI,
        #     aliases=["gpt-4o-mini", "GPT-4o mini"],
        #     context_window=128_000,
        #     capabilities=[
        #         ModelCapability.CHAT,
        #         ModelCapability.FUNCTION_CALLING,
        #         ModelCapability.VISION,
        #     ],
        #     pricing=ModelPricing(
        #         input_cost_per_million_tokens=0.15,
        #         output_cost_per_million_tokens=0.60
        #     ),
        #     tier_availability=["free", "paid"],
        #     priority=90,
        #     enabled=True
        # ))
        
        # 注册 Claude 3.5 Sonnet
        # self.register(Model(
        #     id="anthropic/claude-3-5-sonnet-latest",
        #     name="Claude 3.5 Sonnet",
        #     provider=ModelProvider.ANTHROPIC,
        #     aliases=["claude-3-5-sonnet", "Claude 3.5 Sonnet"],
        #     context_window=200_000,
        #     capabilities=[
        #         ModelCapability.CHAT,
        #         ModelCapability.FUNCTION_CALLING,
        #         ModelCapability.VISION,
        #     ],
        #     pricing=ModelPricing(
        #         input_cost_per_million_tokens=3.00,
        #         output_cost_per_million_tokens=15.00
        #     ),
        #     tier_availability=["paid"],
        #     priority=95,
        #     enabled=True
        # ))
        
        # 注册 DeepSeek Chat
        # self.register(Model(
        #     id="deepseek/deepseek-chat",
        #     name="DeepSeek Chat",
        #     provider=ModelProvider.DEEPSEEK,
        #     aliases=["deepseek-chat", "DeepSeek Chat"],
        #     context_window=128_000,
        #     capabilities=[
        #         ModelCapability.CHAT,
        #         ModelCapability.FUNCTION_CALLING
        #     ],
        #     pricing=ModelPricing(
        #         input_cost_per_million_tokens=0.38,
        #         output_cost_per_million_tokens=0.89
        #     ),
        #     tier_availability=["free", "paid"],
        #     priority=80,
        #     enabled=True
        # ))
        
        # 注册 Moonshot Kimi
        # self.register(Model(
        #     id="moonshot/kimi",
        #     name="Kimi",
        #     provider=ModelProvider.MOONSHOT,
        #     aliases=["kimi", "Kimi"],
        #     context_window=200_000,
        #     capabilities=[
        #         ModelCapability.CHAT,
        #         ModelCapability.VISION,
        #     ],
        #     pricing=ModelPricing(
        #         input_cost_per_million_tokens=1.00,
        #         output_cost_per_million_tokens=3.00
        #     ),
        #     tier_availability=["free", "paid"],
        #     priority=85,
        #     enabled=True
        # ))
        
        # 注册 SiliconFlow BGE-M3 Embedding模型
        self.register(Model(
            id="qwen3-embedding-4b",
            name="Qwen/Qwen3-Embedding-4B",  # 实际API调用名称
            provider=ModelProvider.SILICONFLOW,
            aliases=["qwen3-embedding-4b"],
            context_window=8192,
            capabilities=[
                ModelCapability.EMBEDDING,
            ],
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.00,
                output_cost_per_million_tokens=0.00
            ),
            tier_availability=["free", "paid"],
            priority=90,
            enabled=True
        ))
        
        # 注册 SiliconFlow BGE-Reranker-v2-M3 重排序模型
        self.register(Model(
            id="bge-reranker-v2-m3",
            name="BAAI/bge-reranker-v2-m3",  # 实际API调用名称
            provider=ModelProvider.SILICONFLOW,
            aliases=["bge-reranker-v2-m3", "BGE-Reranker-v2-M3"],
            context_window=8192,
            capabilities=[
                ModelCapability.RERANKER,
            ],
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.00,
                output_cost_per_million_tokens=0.00
            ),
            tier_availability=["free", "paid"],
            priority=90,
            enabled=True
        ))
    
    def register(self, model: Model) -> None:
        """
        注册一个新的模型到注册表中
        
        Args:
            model (Model): 要注册的模型对象
        """
        self._models[model.id] = model
        for alias in model.aliases:
            self._aliases[alias] = model.id
    
    def get(self, model_id: str) -> Optional[Model]:
        """
        根据模型ID或别名获取模型对象
        
        Args:
            model_id (str): 模型ID或别名
            
        Returns:
            Optional[Model]: 找到的模型对象，如果未找到则返回None
        """
        if model_id in self._models:
            return self._models[model_id]
        
        if model_id in self._aliases:
            actual_id = self._aliases[model_id]
            return self._models.get(actual_id)
        
        return None
    
    def get_all(self, enabled_only: bool = True) -> List[Model]:
        """
        获取所有模型列表
        
        Args:
            enabled_only (bool): 是否只返回启用的模型，默认为True
            
        Returns:
            List[Model]: 模型列表
        """
        models = list(self._models.values())
        if enabled_only:
            models = [m for m in models if m.enabled]
        return models
    
    def get_by_tier(self, tier: str, enabled_only: bool = True) -> List[Model]:
        """
        根据层级获取模型列表
        
        Args:
            tier (str): 层级名称 ("free" 或 "paid")
            enabled_only (bool): 是否只返回启用的模型，默认为True
            
        Returns:
            List[Model]: 符合条件的模型列表
        """
        models = self.get_all(enabled_only)
        return [m for m in models if tier in m.tier_availability]
    
    def get_by_provider(self, provider: ModelProvider, enabled_only: bool = True) -> List[Model]:
        """
        根据提供商获取模型列表
        
        Args:
            provider (ModelProvider): 模型提供商
            enabled_only (bool): 是否只返回启用的模型，默认为True
            
        Returns:
            List[Model]: 符合条件的模型列表
        """
        models = self.get_all(enabled_only)
        return [m for m in models if m.provider == provider]
    
    def get_by_capability(self, capability: ModelCapability, enabled_only: bool = True) -> List[Model]:
        """
        根据功能获取模型列表
        
        Args:
            capability (ModelCapability): 模型功能
            enabled_only (bool): 是否只返回启用的模型，默认为True
            
        Returns:
            List[Model]: 具有指定功能的模型列表
        """
        models = self.get_all(enabled_only)
        return [m for m in models if capability in m.capabilities]
    
    def resolve_model_id(self, model_id: str) -> Optional[str]:
        """
        解析模型ID或别名，返回实际的模型ID
        
        Args:
            model_id (str): 模型ID或别名
            
        Returns:
            Optional[str]: 实际的模型ID，如果未找到则返回None
        """
        model = self.get(model_id)
        return model.id if model else None
    
    def get_aliases(self, model_id: str) -> List[str]:
        """
        获取指定模型的所有别名
        
        Args:
            model_id (str): 模型ID
            
        Returns:
            List[str]: 模型的所有别名列表
        """
        model = self.get(model_id)
        return model.aliases if model else []


# 创建全局模型注册表实例
model_registry = ModelRegistry()