import asyncio
import logging
from typing import Optional, Any, Union
from fastapi import HTTPException
import requests
from app.config.config import settings
from app.core.language_model.manager import model_manager
from app.core.language_model.models import Model
from app.entity.model_entity import ModelLoadResult, DEFAULT_APP_CONFIG
from app.utils.helper.helper import convert_model_to_dict
from app.core.language_model.model_client_wrapper import (
    ChatClientSDK, ChatClientHTTP,
    EmbeddingClientSDK, EmbeddingClientHTTP,
    RerankerClientSDK, RerankerClientHTTP
)


class ModelService:
    """模型服务"""
    
    def __init__(self):
        """初始化"""
        self.model_manager = model_manager

    def get_models(self) -> list[dict[str, Any]]:
        """获取所有模型列表信息（按提供商分组）"""
        # 1. 获取所有可用模型
        all_models = self.model_manager.registry.get_all(enabled_only=True)
        
        # 2. 按提供商分组
        providers_dict = {}
        for model in all_models:
            provider_name = model.provider.value
            if provider_name not in providers_dict:
                providers_dict[provider_name] = {
                    "name": provider_name,
                    "label": provider_name.capitalize(),
                    "description": f"{provider_name.capitalize()} AI Models",
                    "models": []
                }
            providers_dict[provider_name]["models"].append(convert_model_to_dict(model))
        
        # 3. 转换为列表并排序
        providers_list = sorted(providers_dict.values(), key=lambda x: x["name"])
        return providers_list

    def get_model(self, model_id: str) -> dict[str, Any]:
        """根据模型ID获取模型详细信息"""
        # 1. 获取模型实例
        model = self.model_manager.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail=f"模型 '{model_id}' 不存在")
        
        # 2. 返回模型详细信息
        return convert_model_to_dict(model)

    def get_all_models(self) -> list[dict[str, Any]]:
        """获取所有模型（扁平化列表）"""
        return self.model_manager.list_available_models()

    async def load_model(self, model_config: dict[str, Any], is_need_sdk: bool = True) -> ModelLoadResult:
        """
        根据传递的模型配置加载模型，并返回其实例信息
        
        Args:
            model_config: 模型配置字典
            is_need_sdk: 是否使用SDK客户端 (True=使用SDK, False=使用HTTP请求)
        
        Returns:
            ModelLoadResult: 支持点语法访问的结果对象
        
        支持两种配置格式：
        1. 简单格式：{"model_id": "xxx", "parameters": {...}}
        2. 完整格式：{"chat_model": {...}, "embedding_model": {...}, "reranker_model": {...}}
        """
        try:
            # 初始化返回结果
            result = ModelLoadResult(
                is_need_sdk=is_need_sdk
            )
            
            # 判断配置格式（新格式不包含provider，直接查看是否有chat_model等字段）
            if any(k in model_config for k in ["chat_model", "embedding_model", "reranker_model"]):
                # 完整格式：处理多个模型配置
                # 从第一个模型配置中获取provider
                provider = None
                first_model_name = None
                
                # 按顺序查找第一个模型配置
                for model_key in ["chat_model", "embedding_model", "reranker_model"]:
                    if model_key in model_config:
                        first_model_name = model_config[model_key].get("name")
                        if first_model_name:
                            # 从注册表中获取模型信息
                            model_obj = self.model_manager.get_model(first_model_name)
                            if model_obj:
                                provider = model_obj.provider.value
                                logging.info(f"从模型 {first_model_name} 获取到 provider: {provider}")
                                break
                
                if not provider:
                    raise ValueError(f"无法从模型配置中获取 provider，请确保模型已在注册表中注册")
                
                result.provider = provider
                
                # 获取API凭证
                api_key, base_url = self._get_provider_credentials(provider)
                
                # 是否使用SDK (注意：is_need_sdk=True表示使用SDK，False表示使用HTTP)
                use_sdk = is_need_sdk
                
                # 处理聊天模型
                if "chat_model" in model_config and model_config["chat_model"]:
                    chat_config = model_config["chat_model"]
                    chat_result = await self._load_single_model(
                        model_name=chat_config.get("name"),
                        model_type=chat_config.get("type", "chat"),
                        provider=provider,
                        api_key=api_key,
                        base_url=base_url,
                        parameters=chat_config.get("parameters", {}),
                        use_sdk=use_sdk
                    )
                    result.models.chat_model = chat_result["model_info"]
                    result.clients.chat_client = chat_result["client"]
                
                # 处理嵌入模型
                if "embedding_model" in model_config and model_config["embedding_model"]:
                    emb_config = model_config["embedding_model"]
                    emb_result = await self._load_single_model(
                        model_name=emb_config.get("name"),
                        model_type=emb_config.get("type", "embedding"),
                        provider=provider,
                        api_key=api_key,
                        base_url=base_url,
                        parameters=emb_config.get("parameters", {}),
                        use_sdk=use_sdk
                    )
                    result.models.embedding_model = emb_result["model_info"]
                    result.clients.embedding_client = emb_result["client"]
                
                # 处理重排序模型
                if "reranker_model" in model_config and model_config["reranker_model"]:
                    rerank_config = model_config["reranker_model"]
                    rerank_result = await self._load_single_model(
                        model_name=rerank_config.get("name"),
                        model_type=rerank_config.get("type", "reranker"),
                        provider=provider,
                        api_key=api_key,
                        base_url=base_url,
                        parameters=rerank_config.get("parameters", {}),
                        use_sdk=use_sdk
                    )
                    result.models.reranker_model = rerank_result["model_info"]
                    result.clients.reranker_client = rerank_result["client"]
                
                logging.info(f"成功加载 {provider} 提供商的模型配置")
                return result
                
            else:
                # 简单格式：单模型加载（向后兼容）
                model_id = model_config.get("model_id") or model_config.get("model")
                if not model_id:
                    raise ValueError("模型配置中缺少 model_id 或 model 信息")
                
                # 验证模型是否可用
                is_valid, error_msg = self.model_manager.validate_model(model_id)
                if not is_valid:
                    raise ValueError(error_msg)
                
                # 获取模型实例
                model = self.model_manager.get_model(model_id)
                if not model:
                    raise ValueError(f"无法加载模型: {model_id}")
                
                # 构建模型客户端配置
                client_config = self._build_client_config(model, model_config)
                
                # 初始化客户端（根据 is_need_sdk 决定）
                client = None
                if is_need_sdk:
                    client = await self.get_client(model.provider.value, client_config)
                
                # 返回单模型格式
                result.model = convert_model_to_dict(model)
                result.client_config = client_config
                result.client = client
                return result
            
        except Exception as error:
            logging.error(f"加载模型失败, 错误信息: {str(error)}", exc_info=True)
            return self.load_default_model()

    def load_default_model(self) -> ModelLoadResult:
        """加载默认模型，在获取不到模型或者出错时使用默认模型进行兜底"""
        # 1. 获取默认模型（优先使用免费层级）
        model = self.model_manager.get_default_model(tier="free")
        
        # 2. 如果没有免费模型，尝试获取付费模型
        if not model:
            model = self.model_manager.get_default_model(tier="paid")
        
        # 3. 如果仍然没有，使用硬编码的兜底模型
        if not model:
            model = self.model_manager.get_model("gpt-4o-mini")
        
        if not model:
            raise HTTPException(status_code=500, detail="无法加载任何可用模型")
        
        # 4. 构建默认配置
        client_config = self._build_client_config(model, {})
        
        return ModelLoadResult(
            model=convert_model_to_dict(model),
            client_config=client_config,
            client=None,
            is_need_sdk=True  # 默认模型使用SDK
        )

    def _build_client_config(self, model: Model, custom_config: dict[str, Any]) -> dict[str, Any]:
        """构建模型客户端配置"""
        # 1. 根据提供商获取API密钥和基础URL
        provider_name = model.provider.value
        api_key, base_url = self._get_provider_credentials(provider_name)
        
        # 2. 构建基础配置
        config = {
            "model": model.id,
            "api_key": api_key,
            "base_url": base_url,
            "provider": provider_name,
        }
        
        # 3. 添加模型特定参数
        parameters = custom_config.get("parameters", {})
        if parameters:
            config.update(parameters)
        
        # 4. 添加默认参数（如果未指定）
        config.setdefault("temperature", 1)
        config.setdefault("max_tokens", model.max_output_tokens)
        
        return config

    async def _load_single_model(
        self,
        model_name: str,
        model_type: str,
        provider: str,
        api_key: str,
        base_url: str,
        parameters: dict[str, Any],
        use_sdk: bool
    ) -> dict[str, Any]:
        """
        加载单个模型
        
        Args:
            model_name: 模型名称
            model_type: 模型类型 (chat/embedding/reranker)
            provider: 提供商名称
            api_key: API密钥
            base_url: API基础URL
            parameters: 模型参数
            use_sdk: 是否使用SDK客户端
            
        Returns:
            包含模型信息和客户端的字典
        """
        # 从 model_manager 获取实际的 API 模型名称
        model_obj = self.model_manager.get_model(model_name)
        if model_obj:
            # 使用注册表中的 name 字段（实际API名称）
            api_model_name = model_obj.name
            logging.info(f"模型映射: {model_name} -> {api_model_name}")
        else:
            # 如果未找到，使用原始名称
            api_model_name = model_name
            logging.warning(f"未在注册表中找到模型 {model_name}，使用原始名称")
        
        # 构建模型配置
        config = {
            "model": api_model_name,  # 使用实际的API名称
            "api_key": api_key,
            "base_url": base_url,
            "provider": provider,
            "type": model_type,
            **parameters
        }
        
        # 初始化客户端
        client = None
        if use_sdk:
            # SDK模式：创建原始SDK客户端，然后用包装类包装
            sdk_client = await self.get_client(provider, config)
            
            if model_type == "chat":
                client = ChatClientSDK(sdk_client, api_model_name, parameters)  # 传入parameters
            elif model_type == "embedding":
                client = EmbeddingClientSDK(sdk_client, api_model_name, parameters)
            elif model_type == "reranker":
                client = RerankerClientSDK(sdk_client, api_model_name, parameters)
        else:
            # HTTP模式：创建HTTP包装客户端
            if model_type == "chat":
                client = ChatClientHTTP(provider, api_model_name, api_key, base_url, parameters)  # 传入parameters
            elif model_type == "embedding":
                client = EmbeddingClientHTTP(provider, api_model_name, api_key, base_url, parameters)
            elif model_type == "reranker":
                client = RerankerClientHTTP(provider, api_model_name, api_key, base_url, parameters)
        
        # 返回结果
        return {
            "model_info": {
                "name": model_name,  # 保留原始名称用于显示
                "api_name": api_model_name,  # 实际API名称
                "type": model_type,
                "provider": provider,
                "parameters": parameters,
                "config": config
            },
            "client": client
        }

    def _get_provider_credentials(self, provider_name: str) -> tuple[str, str]:
        """获取提供商的API凭证"""
        credentials_map = {
            "openai": (settings.OPENAI_API_KEY, getattr(settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1")),
            "siliconflow": (settings.SILICONFLOW_API_KEY, settings.SILICONFLOW_BASE_URL),
            "tongyi": (settings.DASHSCOPE_API_KEY, settings.DASHSCOPE_BASE_URL),
            "ollama": ("", settings.OLLAMA_BASE_URL),
        }
        
        if provider_name not in credentials_map:
            raise ValueError(f"不支持的模型提供者: {provider_name}")
        
        api_key, base_url = credentials_map[provider_name]
        
        # 验证必需的凭证（ollama除外）
        if provider_name != "ollama" and not api_key:
            logging.warning(f"提供商 {provider_name} 缺少API密钥")
        
        return api_key, base_url

    def get_model_by_capability(self, capability: str) -> list[dict[str, Any]]:
        """根据模型能力筛选模型"""
        from app.core.language_model.models import ModelCapability
        
        try:
            # 将字符串转换为枚举
            cap = ModelCapability(capability.lower())
            models = self.model_manager.get_models_with_capability(cap)
            return [convert_model_to_dict(model) for model in models]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的模型能力: {capability}")

    def get_model_stats(self, model_id: str) -> dict[str, Any]:
        """获取模型使用统计"""
        stats = self.model_manager.get_model_stats(model_id)
        if not stats:
            raise HTTPException(status_code=404, detail=f"未找到模型 '{model_id}' 的统计信息")
        return stats

    def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> dict[str, Any]:
        """计算模型使用成本"""
        cost = self.model_manager.calculate_cost(model_id, input_tokens, output_tokens)
        if cost is None:
            raise HTTPException(status_code=404, detail=f"模型 '{model_id}' 没有定价信息")
        
        return {
            "model_id": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": cost,
            "currency": "USD"
        }

    async def get_client(self, provider: str, config: dict[str, Any]) -> Any:
        """
        根据提供商初始化对应的SDK客户端
        
        Args:
            provider: 模型提供商名称 (openai/ollama/tongyi/siliconflow)
            config: 客户端配置信息
            
        Returns:
            初始化好的SDK客户端实例
        """
        try:
            if provider == "openai":
                # 导入 OpenAI SDK
                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("api_key"),
                    base_url=config.get("base_url")

                )
                logging.info(f"OpenAI 客户端初始化成功")
                return client
                
            elif provider == "ollama":
                # 导入 Ollama SDK
                try:
                    from ollama import Client
                    client = Client(
                        host=config.get("base_url", settings.OLLAMA_BASE_URL)
                    )

                    logging.info(f"Ollama 客户端初始化成功")
                    return client
                except ImportError:
                    logging.warning("ollama SDK 未安装，请执行: pip install ollama")
                    raise ValueError("ollama SDK 未安装")
                    
            elif provider == "tongyi" or provider == "dashscope":
                # 通义千问兼容 OpenAI SDK
                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("api_key", settings.DASHSCOPE_API_KEY),
                    base_url=config.get("base_url", settings.DASHSCOPE_BASE_URL)
                )
                logging.info(f"通义千问客户端初始化成功")
                return client
                
            elif provider == "siliconflow":
                # SiliconFlow 兼容 OpenAI SDK
                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("api_key", settings.SILICONFLOW_API_KEY),
                    base_url=config.get("base_url", settings.SILICONFLOW_BASE_URL)
                )
                logging.info(f"SiliconFlow 客户端初始化成功")
                return client
                
            else:
                raise ValueError(f"不支持的提供商: {provider}")
                
        except Exception as e:
            logging.error(f"初始化 {provider} 客户端失败: {str(e)}")
            raise

    async def call_model_http(self, endpoint: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        """
        通过HTTP请求调用模型API
        
        Args:
            endpoint: API端点URL
            payload: 请求负载
            headers: 请求头
            
        Returns:
            API响应结果
        """
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"HTTP请求失败: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise HTTPException(status_code=response.status_code, detail=error_msg)
                
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTP请求异常: {str(e)}")
            raise HTTPException(status_code=500, detail=f"HTTP请求异常: {str(e)}")

    async def _generate_embedding_http(self, text: str, provider: str, model_name: str) -> Optional[list[float]]:
        """
        使用HTTP请求生成embedding（参考test_clinical_scenarios_embedding.py）
        
        Args:
            text: 要embedding的文本
            provider: 提供商名称
            model_name: 模型名称
            
        Returns:
            embedding向量或None
        """
        try:
            # 获取API配置
            api_key, base_url = self._get_provider_credentials(provider)
            
            # 构建请求
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            endpoint = f"{base_url}/embeddings"
            payload = {
                "model": model_name,
                "input": text,
                "encoding_format": "float"
            }
            
            result = await self.call_model_http(endpoint, payload, headers)
            
            if result and 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            else:
                logging.error(f"embedding响应格式异常: {result}")
                return None
                
        except Exception as e:
            logging.error(f"生成embedding失败: {str(e)}")
            return None

    async def _chat_completion_http(self, messages: list[dict], provider: str, model_name: str, **kwargs) -> Optional[dict]:
        """
        使用HTTP请求调用聊天模型
        
        Args:
            messages: 消息列表
            provider: 提供商名称
            model_name: 模型名称
            **kwargs: 其他参数（temperature, max_tokens等）
            
        Returns:
            API响应结果
        """
        try:
            # 获取API配置
            api_key, base_url = self._get_provider_credentials(provider)
            
            # 构建请求
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            endpoint = f"{base_url}/chat/completions"
            payload = {
                "model": model_name,
                "messages": messages,
                **kwargs  # 包含 temperature, max_tokens 等参数
            }
            
            result = await self.call_model_http(endpoint, payload, headers)
            return result
                
        except Exception as e:
            logging.error(f"聊天模型调用失败: {str(e)}")
            return None



if __name__ == '__main__':
    async def main():
        service = ModelService()
        res=await service.load_model(
               DEFAULT_APP_CONFIG["model_config"],
               is_need_sdk= True
        )
        emeb_llm:EmbeddingClientSDK=res.clients.embedding_client
        re=await emeb_llm.embedding(
               text="你好",
               #维度
             dimensions= 1024,


        )
        print(len( re))
    asyncio.run(main())


# ============================================================================
# 使用示例
# ============================================================================
"""
示例1: 使用完整配置格式（同时加载多个模型）- SDK模式

async def example_full_config():
    service = ModelService()
    
    # 使用model_entity.py中的配置格式
    result = await service.load_model(
        model_config={
            "provider": "siliconflow",
            
            "chat_model": {
                "type": "chat",
                "name": "qwen2.5-32b-instruct",
                "parameters": {
                    "temperature": 0.5,
                    "top_p": 0.85,
                    "frequency_penalty": 0.2,
                    "presence_penalty": 0.2,
                    "max_tokens": 8192,
                }
            },
            
            "embedding_model": {
                "type": "embedding",
                "name": "bge-m3",
                "parameters": {
                    "dimension": 1024,
                    "embedding_ctx_length": 8192,
                }
            },
            
            "reranker_model": {
                "type": "reranker",
                "name": "bge-reranker-v2-m3",
                "parameters": {}
            }
        },
        is_need_sdk=True  # 使用SDK模式
        
    )
    
    # 使用点语法访问！
    print(f"提供商: {result.provider}")
    print(f"是否使用SDK: {result.is_need_sdk}")
    print(f"模型列表: {result.models.keys()}")
    print(f"客户端列表: {result.clients.keys()}")
    
    # 直接使用点语法访问客户端！
    chat_client = result.clients.chat_client
    embedding_client = result.clients.embedding_client
    reranker_client = result.clients.reranker_client
    
    # 使用聊天模型
    response = chat_client.chat.completions.create(
        model=result.models.chat_model["name"],
        messages=[{"role": "user", "content": "你好"}]
    )
    print(response.choices[0].message.content)


示例2: 使用HTTP请求方式

async def example_http_mode():
    service = ModelService()
    
    result = await service.load_model(
        model_config={
            "provider": "siliconflow",
            
            "chat_model": {
                "type": "chat",
                "name": "qwen2.5-32b-instruct",
                "parameters": {
                    "temperature": 0.8,
                    "max_tokens": 2000
                }
            }
        },
        is_need_sdk=False  # 使用HTTP请求模式
    )
    
    # 点语法访问
    print(f"提供商: {result.provider}")
    print(f"chat_client为None: {result.clients.chat_client is None}")
    
    # HTTP模式下，client为None，需要使用HTTP方法
    response = await service.chat_completion_http(
        messages=[{"role": "user", "content": "介绍一下AI"}],
        provider=result.provider,
        model_name=result.models.chat_model["name"],
        temperature=0.8,
        max_tokens=2000
    )
    print(response['choices'][0]['message']['content'])


示例3: 生成Embedding（HTTP方式）

async def example_embedding_http():
    service = ModelService()
    
    result = await service.load_model(
        model_config={
            "provider": "siliconflow",
            
            "embedding_model": {
                "type": "embedding",
                "name": "bge-m3",
                "parameters": {
                    "dimension": 1024
                }
            }
        },
        is_need_sdk=False  # 使用HTTP请求模式
    )
    
    # 点语法访问
    embedding = await service.generate_embedding_http(
        text="这是一段需要向量化的文本",
        provider=result.provider,
        model_name=result.models.embedding_model["name"]
    )
    print(f"Embedding维度: {len(embedding)}")


示例4: 向后兼容的简单格式

async def example_simple_format():
    service = ModelService()
    
    # 旧的简单配置格式仍然可用
    result = await service.load_model(
        model_config={
            "model_id": "gpt-4o-mini",
            "parameters": {
                "temperature": 0.7,
                "max_tokens": 2000
            }
        },
        is_need_sdk=True  # 使用SDK模式
    )
    
    # 点语法访问
    client = result.client
    response = client.chat.completions.create(
        model=result.client_config["model"],
        messages=[{"role": "user", "content": "你好"}]
    )
    print(response.choices[0].message.content)


示例5: 从 DEFAULT_APP_CONFIG 加载

from app.entity.model_entity import DEFAULT_APP_CONFIG

async def example_from_default_config():
    service = ModelService()
    
    # 直接使用默认配置 (SDK模式)
    result = await service.load_model(
        model_config=DEFAULT_APP_CONFIG["model_config"],
        is_need_sdk=True
    )
    
    # 点语法访问！
    print(f"提供商: {result.provider}")
    print(f"加载的模型: {result.models.keys()}")
    print(f"客户端: {result.clients.keys()}")
    
    # 也可以转换为字典格式
    result_dict = result.to_dict()
    print(f"字典格式: {result_dict.keys()}")
    
    # 或者继续使用点语法
    chat_client = result.clients.chat_client
    embedding_client = result.clients.embedding_client
"""
