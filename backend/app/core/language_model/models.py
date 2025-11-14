from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ModelProvider(Enum):
    """
    模型提供商枚举类
    定义了系统支持的各种AI模型提供商
    """
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    MOONSHOT = "moonshot"
    OLLAMA = "ollama"
    TONGYI = "tongyi"
    SILICONFLOW = "siliconflow"


class ModelCapability(Enum):
    """
    模型能力枚举类
    定义了AI模型可能具备的各种功能能力
    """
    CHAT = "chat"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    CODE_INTERPRETER = "code_interpreter"
    WEB_SEARCH = "web_search"
    THINKING = "thinking"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


@dataclass
class ModelPricing:
    """
    模型定价信息类
    存储模型的输入和输出token成本信息
    """
    input_cost_per_million_tokens: float
    output_cost_per_million_tokens: float
    
    @property
    def input_cost_per_token(self) -> float:
        """计算每个输入token的成本"""
        return self.input_cost_per_million_tokens / 1_000_000
    
    @property
    def output_cost_per_token(self) -> float:
        """计算每个输出token的成本"""
        return self.output_cost_per_million_tokens / 1_000_000


@dataclass
class Model:
    """
    AI模型配置类
    定义了一个AI模型的所有属性和行为
    """
    id: str                                      # 模型ID
    name: str                                    # 模型名称
    provider: ModelProvider                      # 模型提供商
    aliases: List[str] = field(default_factory=list)  # 模型别名列表
    context_window: int = 128_000                # 上下文窗口大小（token数）
    max_output_tokens: Optional[int] = None      # 最大输出token数
    capabilities: List[ModelCapability] = field(default_factory=list)  # 模型能力列表
    pricing: Optional[ModelPricing] = None       # 模型定价信息
    enabled: bool = True                         # 是否启用
    beta: bool = False                           # 是否为测试版
    tier_availability: List[str] = field(default_factory=lambda: ["paid"])  # 可用层级
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    priority: int = 0                            # 优先级
    recommended: bool = False                    # 是否推荐
    
    def __post_init__(self):
        """
        初始化后处理
        设置默认的最大输出token数和确保聊天能力存在
        """
        if self.max_output_tokens is None:
            self.max_output_tokens = min(self.context_window // 4, 32_000)
        
        if ModelCapability.CHAT not in self.capabilities:
            self.capabilities.insert(0, ModelCapability.CHAT)
    
    @property
    def full_id(self) -> str:
        """
        获取完整模型ID
        如果ID中已包含斜杠则直接返回，否则添加提供商前缀
        """
        if "/" in self.id:
            return self.id
        return f"{self.provider.value}/{self.id}"
    
    @property
    def supports_thinking(self) -> bool:
        """检查模型是否支持思考功能"""
        return ModelCapability.THINKING in self.capabilities
    
    @property
    def supports_functions(self) -> bool:
        """检查模型是否支持函数调用功能"""
        return ModelCapability.FUNCTION_CALLING in self.capabilities
    
    @property
    def supports_vision(self) -> bool:
        """检查模型是否支持视觉识别功能"""
        return ModelCapability.VISION in self.capabilities
    
    @property
    def is_free_tier(self) -> bool:
        """检查模型是否在免费层级可用"""
        return "free" in self.tier_availability