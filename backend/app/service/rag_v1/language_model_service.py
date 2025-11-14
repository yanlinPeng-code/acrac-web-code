import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Union
from fastapi import HTTPException
from app.config.config import settings

from app.core.language_model.entities.model_entity import BaseLanguageModel, BaseEmbeddingModel
from app.core.language_model.language_model_manager import LanguageModelManager
from app.utils.helper.helper import convert_model_to_dict


class LanguageModelService:
    """语言模型服务"""
    #该模型服务是基于yaml配置的，加载速度较慢
    def __init__(self):
        """初始化"""
        self.language_model_manager=LanguageModelManager()

    def get_language_models(self) -> list[dict[str, Any]]:
        """获取LLMOps项目中的所有模型列表信息"""
        # 1.调用语言模型管理器获取提供商列表
        providers = self.language_model_manager.get_providers()

        # 2.构建语言模型列表，循环读取数据
        language_models = []
        for provider in providers:
            # 3.获取提供商实体和模型实体列表
            provider_entity = provider.provider_entity
            model_entities = provider.get_model_entities()

            # 4.构建响应字典结构
            language_model = {
                "name": provider_entity.name,
                "position": provider.position,
                "label": provider_entity.label,
                "icon": provider_entity.icon,
                "description": provider_entity.description,
                "background": provider_entity.background,
                "support_model_types": provider_entity.supported_model_types,
                "models": convert_model_to_dict(model_entities),
            }
            language_models.append(language_model)

        return language_models

    def get_language_model(self, provider_name: str, model_name: str) -> dict[str, Any]:
        """根据传递的提供者名字+模型名字获取模型详细信息"""
        # 1.获取提供者+模型实体信息
        provider = self.language_model_manager.get_provider(provider_name)
        if not provider:
            raise HTTPException(status_code=500,detail="该服务提供者不存在")

        # 2.获取模型实体
        model_entity = provider.get_model_entity(model_name)
        if not model_entity:
            raise HTTPException(status_code=500,detail="该模型不存在")

        return convert_model_to_dict(model_entity)

    def get_language_model_icon(self, provider_name: str) -> tuple[bytes, str]:
        """根据传递的提供者名字获取提供商对应的图标信息"""
        # 1.获取提供者信息
        provider = self.language_model_manager.get_provider(provider_name)
        if not provider:
            raise HTTPException(status_code=500,detail="该服务提供者不存在")

        # 2.获取项目的根路径信息
        root_path = Path(__file__).parents[3]

        # 3.拼接得到提供者所在的文件夹
        provider_path = os.path.join(
            root_path,
            "app", "src","core", "language_model", "providers", provider_name,
        )

        # 4.拼接得到icon对应的路径
        icon_path = os.path.join(provider_path, "_asset", provider.provider_entity.icon)

        # 5.检测icon是否存在
        if not os.path.exists(icon_path):
            raise HTTPException(status_code=500,detail=f"该模型提供者_asset下未提供图标")

        # 6.读取icon的类型
        mimetype, _ = mimetypes.guess_type(icon_path)
        mimetype = mimetype or "application/octet-stream"

        # 7.读取icon的字节数据
        with open(icon_path, "rb") as f:
            byte_data = f.read()
            return byte_data, mimetype

    async def load_language_model(self, model_config: dict[str, Any]) -> dict[str, Any] | Union[BaseLanguageModel, BaseEmbeddingModel]:
        """根据传递的模型配置加载大语言模型，并返回其实例"""
        try:
            # 初始化返回结果（避免变量未定义错误）
            model_instances = {
                "chat_model": None,
                "embedding_model": None,
                "reranker_model": None
            }

            # 1. 提取 provider 并动态获取 API 密钥和基础 URL（增强扩展性）
            provider_name = model_config.get("provider", "")
            if not provider_name:
                raise ValueError("模型配置中缺少 provider 信息")
            if provider_name=="openai":
                api_key = settings.OPENAI_API_KEY
                base_url = settings.OPENAI_API_BASE_URL
            elif provider_name=="siliconflow":
                api_key = settings.SILICONFLOW_API_KEY
                base_url = settings.SILICONFLOW_BASE_URL
            else:
                raise ValueError("不支持的模型提供者")


            # 2. 提取各类模型配置
            chat_model_cfg = model_config.get("chat_model", {})
            embedding_model_cfg = model_config.get("embedding_model", {})
            reranker_model_cfg = model_config.get("reranker_model", {})



            # 4. 分别实例化各类模型（只处理有配置的模型）
            if chat_model_cfg:
                model_instances["chat_model"] = self._instantiate_model(chat_model_cfg, provider_name, api_key, base_url)
            if embedding_model_cfg:
                model_instances["embedding_model"] = self._instantiate_model(embedding_model_cfg, provider_name, api_key, base_url)
            if reranker_model_cfg:
                model_instances["reranker_model"] = self._instantiate_model(reranker_model_cfg, provider_name,api_key, base_url)

            # 过滤未配置的模型（可选，根据业务需求决定是否保留 None）
            return {k: v for k, v in model_instances.items() if v is not None}

        except Exception as error:
            logging.error(f"获取模型失败, 错误信息: {str(error)}", exc_info=True)
            return self.load_default_language_model()

    def load_default_language_model(self) -> BaseLanguageModel:
        """加载默认的大语言模型，在模型管理器中获取不到模型或者出错时使用默认模型进行兜底"""
        # 1.获取openai服务提供者与模型类
        provider = self.language_model_manager.get_provider("openai")
        model_entity = provider.get_model_entity("gpt-4o-mini")
        model_class = provider.get_model_class(model_entity.model_type)

        # bug:原先写法使用的是LangChain封装的LLM类，需要替换成自定义封装的类，否则会识别到模型不存在features
        # return ChatOpenAI(model="gpt-4o-mini", temperature=1, max_tokens=8192)

        # 2.实例化模型并返回
        return model_class(
            **model_entity.attributes,
            temperature=1,
            max_tokens=8192,
            features=model_entity.features,
            metadata=model_entity.metadata,
        )

    def _instantiate_model(self,model_cfg: dict, provider_name: str, api_key: str, base_url: str) -> Any:
        """实例化单个模型的通用方法"""
        model_name = model_cfg.get("name", "")
        parameters = model_cfg.get("parameters", {})
        if not model_name:
            raise ValueError("模型配置中缺少 model 名称")

        provider = self.language_model_manager.get_provider(provider_name)
        model_entity = provider.get_model_entity(model_name)
        model_class = provider.get_model_class(model_entity.model_type)

        return model_class(
                    api_key=api_key,
                    base_url=base_url,
                    **model_entity.attributes, **parameters,
                    features=model_entity.features,
                    metadata=model_entity.metadata,
            )
# if __name__ == '__main__':
#
#     service=LanguageModelService()
#     # print(service.get_language_models())
#     llm=service.load_language_model(
#         {
#             "provider": "siliconflow",
#             "model": "bge-m3",
#         }
#     )



    # llm=ChatQwen(
    #     model="qwen-max",
    #     api_key=settings.DASHSCOPE_API_KEY,
    #     base_url=settings.DASHSCOPE_BASE_URL,
    #     temperature=1,
    #     max_tokens=8192,
    #     streaming=True,
    #     extra_body={
    #         "enable_thinking": True,
    #     }
    # )
    # # llm=ChatOpenAI(
    # #
    # #     api_key=settings.DASHSCOPE_API_KEY,
    # #     base_url=settings.DASHSCOPE_BASE_URL,
    # #     temperature=1,
    # #     max_tokens=8192,
    # #     streaming=True,
    # #     extra_body={
    # #         "enable_thinking": True,
    # #     }
    # # )
    # llm=service.load_language_model({
    # "provider": "tongyi",
    # "model": "qwen3-vl-plus",
    # "parameters": {
    #     "streaming": True,
    #     "extra_body": {
    #         "enable_thinking": True,
    #     }
    # }})
    # for chunk in llm.stream("请写一个关于机器学习的文章，请使用中文。") :
    #     print(chunk)

