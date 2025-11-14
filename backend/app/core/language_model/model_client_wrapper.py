#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型客户端包装类
提供统一的SDK和HTTP调用接口
"""

import logging
import requests
from typing import Optional, Any, List
from fastapi import HTTPException


class ChatClientSDK:
    """聊天客户端SDK模式包装类"""
    
    def __init__(self, sdk_client: Any, model_name: str, default_params: dict = None):
        self._sdk_client = sdk_client
        self._model_name = model_name
        self._default_params = default_params or {}  # 保存默认参数
    
    async def achat(self, messages: List[dict], **kwargs):
        """
        聊天方法（SDK模式）
        
        Args:
            messages: 消息列表
            **kwargs: 其他参数（temperature, max_tokens等），会覆盖默认参数
        
        Returns:
            聊天响应对象
        """
        # 合并默认参数和传入参数（传入参数优先级更高）
        params = {**self._default_params, **kwargs}
        
        return self._sdk_client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            **params
        )


class ChatClientHTTP:
    """聊天客户端HTTP模式包装类"""
    
    def __init__(self, provider: str, model_name: str, api_key: str, base_url: str, default_params: dict = None):
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._default_params = default_params or {}  # 保存默认参数
    
    async def chat_completion_http(self, messages: List[dict], **kwargs):
        """
        聊天补全方法（HTTP模式）
        
        Args:
            messages: 消息列表
            **kwargs: 其他参数（temperature, max_tokens等），会覆盖默认参数
        
        Returns:
            API响应结果
        """
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }
            
            endpoint = f"{self._base_url}/chat/completions"
            
            # 合并默认参数和传入参数（传入参数优先级更高）
            params = {**self._default_params, **kwargs}
            
            payload = {
                "model": self._model_name,
                "messages": messages,
                **params
            }
            
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"HTTP请求失败: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise HTTPException(status_code=response.status_code, detail=error_msg)
                
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTP请求异常: {str(e)}")
            raise HTTPException(status_code=500, detail=f"HTTP请求异常: {str(e)}")


class EmbeddingClientSDK:
    """嵌入客户端SDK模式包装类"""
    
    def __init__(self, sdk_client: Any, model_name: str, default_params: dict = None):
        self._sdk_client = sdk_client
        self._model_name = model_name
        self._default_params = default_params or {}  # 保存默认参数
    
    async def aembedding(self, text: str, **kwargs) -> List[float]:
        """
        嵌入方法（SDK模式）
        
        Args:
            text: 要嵌入的文本
            **kwargs: 其他参数，会覆盖默认参数
        
        Returns:
            嵌入向量
        """
        # 合并默认参数和传入参数（传入参数优先级更高）
        params = {**self._default_params, **kwargs}
        
        response = self._sdk_client.embeddings.create(
            model=self._model_name,
            input=text,
            **params
        )
        return response.data[0].embedding


class EmbeddingClientHTTP:
    """嵌入客户端HTTP模式包装类"""
    
    def __init__(self, provider: str, model_name: str, api_key: str, base_url: str, default_params: dict = None):
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._default_params = default_params or {}  # 保存默认参数
    
    async def generate_embedding_http(self, text: str, **kwargs) -> Optional[List[float]]:
        """
        生成嵌入方法（HTTP模式）
        
        Args:
            text: 要嵌入的文本
            **kwargs: 其他参数，会覆盖默认参数
        
        Returns:
            嵌入向量或None
        """
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }
            
            endpoint = f"{self._base_url}/embeddings"
            
            # 合并默认参数和传入参数（传入参数优先级更高）
            params = {**self._default_params, **kwargs}
            
            payload = {
                "model": self._model_name,
                "input": text,
                "encoding_format": "float",
                **params
            }
            
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result and 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['embedding']
                else:
                    logging.error(f"embedding响应格式异常: {result}")
                    return None
            else:
                error_msg = f"HTTP请求失败: {response.status_code} - {response.text}"
                logging.error(error_msg)
                return None
                
        except Exception as e:
            logging.error(f"生成embedding失败: {str(e)}")
            return None


class RerankerClientSDK:
    """重排序客户端SDK模式包装类"""
    
    def __init__(self, sdk_client: Any, model_name: str, default_params: dict = None):
        self._sdk_client = sdk_client
        self._model_name = model_name
        self._default_params = default_params or {}  # 保存默认参数
    
    async def rerank(self, query: str, documents: List[str], **kwargs):
        """
        重排序方法（SDK模式）
        
        Args:
            query: 查询文本
            documents: 文档列表
            **kwargs: 其他参数，会覆盖默认参数
        
        Returns:
            重排序结果
        """
        if self._sdk_client and hasattr(self._sdk_client, 'rerank'):
            # 合并默认参数和传入参数（传入参数优先级更高）
            params = {**self._default_params, **kwargs}
            
            return self._sdk_client.rerank(
                model=self._model_name,
                query=query,
                documents=documents,
                **params
            )
        else:
            raise NotImplementedError(f"SDK客户端不支持rerank方法")


class RerankerClientHTTP:
    """重排序客户端HTTP模式包装类"""
    
    def __init__(self, provider: str, model_name: str, api_key: str, base_url: str, default_params: dict = None):
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._default_params = default_params or {}  # 保存默认参数
    
    async def rerank_http(self, query: str, documents: List[str], **kwargs):
        """
        重排序方法（HTTP模式）
        
        Args:
            query: 查询文本
            documents: 文档列表
            **kwargs: 其他参数，会覆盖默认参数
        
        Returns:
            重排序结果
        """
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }
            
            endpoint = f"{self._base_url}/rerank"
            
            # 合并默认参数和传入参数（传入参数优先级更高）
            params = {**self._default_params, **kwargs}
            
            payload = {
                "model": self._model_name,
                "query": query,
                "documents": documents,
                **params
            }
            
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = f"HTTP请求失败: {response.status_code} - {response.text}"
                logging.error(error_msg)
                raise HTTPException(status_code=response.status_code, detail=error_msg)
                
        except Exception as e:
            logging.error(f"重排序调用失败: {str(e)}")
            raise
