from dataclasses import dataclass, field
from typing import Optional, Any

DEFAULT_APP_CONFIG = {
    "model_config": {

        # 聊天模型配置（独立键，明确区分类型）
        "chat_model": {
            "type": "chat",  # 模型类型：聊天
            "name": "qwen2.5-32b-instruct",  # 模型具体名称
            "parameters": {  # 聊天生成参数
                "temperature": 0.5,  # 控制输出随机性（0-1，值越低越确定）
                "top_p": 0.85,  # 核采样（筛选累积概率达85%的token）
                "frequency_penalty": 0.2,  # 降低高频词重复（值越高惩罚越强）
                "presence_penalty": 0.2,  # 降低已出现主题的重复（鼓励新内容）
                "max_tokens": 8192,  # 最大生成token数量
            }
        },

        # # 嵌入模型配置（与聊天模型并列，逻辑清晰）
        # "embedding_model": {
        #     "type": "embedding",  # 模型类型：嵌入
        #     "name": "qwen3-embedding-4b",  # 模型具体名称
        #     "parameters": {  # 嵌入参数
        #         "dimensions": 2560,  # 嵌入向量维度（修正为单数，符合常规命名）
        #     }
        # },
        # "reranker_model":{
        #     "type": "reranker",
        #     "name": "bge-reranker-v2-m3",
        #     "parameters": {}
        # }


    }
}


@dataclass
class ModelInfo:
    """模型信息类，支持点语法访问"""
    chat_model: Optional[dict[str, Any]] = None
    embedding_model: Optional[dict[str, Any]] = None
    reranker_model: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            k: v for k, v in {
                "chat_model": self.chat_model,
                "embedding_model": self.embedding_model,
                "reranker_model": self.reranker_model,
            }.items() if v is not None
        }

    def keys(self):
        """返回所有非空的模型键"""
        return [k for k, v in self.to_dict().items() if v is not None]


@dataclass
class ClientInfo:
    """客户端信息类，支持点语法访问"""
    chat_client: Optional[Any] = None
    embedding_client: Optional[Any] = None
    reranker_client: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            k: v for k, v in {
                "chat_client": self.chat_client,
                "embedding_client": self.embedding_client,
                "reranker_client": self.reranker_client,
            }.items() if v is not None
        }

    def keys(self):
        """返回所有非空的客户端键"""
        return [k for k, v in self.to_dict().items() if v is not None]


@dataclass
class ModelLoadResult:
    """模型加载结果类，支持点语法访问"""
    models: ModelInfo = field(default_factory=ModelInfo)
    clients: ClientInfo = field(default_factory=ClientInfo)
    provider: Optional[str] = None
    is_need_sdk: bool = True

    # 单模型格式兼容
    model: Optional[dict[str, Any]] = None
    client_config: Optional[dict[str, Any]] = None
    client: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "models": self.models.to_dict(),
            "clients": self.clients.to_dict(),
            "provider": self.provider,
            "is_need_sdk": self.is_need_sdk,
            "model": self.model,
            "client_config": self.client_config,
            "client": self.client,
        }