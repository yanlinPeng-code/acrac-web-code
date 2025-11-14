from typing import Optional, List, Dict, Any, Tuple

from app.core.language_model.model_stats import model_stats_manager
from app.core.language_model.models import Model, ModelCapability
from app.core.language_model.registry import model_registry


class ModelManager:
    """模型管理器，负责模型的选择、验证、成本计算等操作"""
    
    def __init__(self):
        """初始化模型管理器"""
        self.registry = model_registry
    
    def get_model(self, model_id: str) -> Optional[Model]:
        """根据模型ID获取模型实例"""
        return self.registry.get(model_id)
    
    def resolve_model_id(self, model_id: str) -> str:
        """解析模型ID，将别名转换为实际的模型ID"""
        resolved = self.registry.resolve_model_id(model_id)
        if resolved:
            return resolved
        # 如果无法解析，静默返回原始model_id
        return model_id
    
    def validate_model(self, model_id: str) -> Tuple[bool, str]:
        """验证模型是否存在且可用"""
        model = self.get_model(model_id)
        
        if not model:
            return False, f"Model '{model_id}' not found"
        
        if not model.enabled:
            return False, f"Model '{model.name}' is currently disabled"
        
        return True, ""
    
    def calculate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> Optional[float]:
        """计算使用指定模型的成本"""
        model = self.get_model(model_id)
        if not model or not model.pricing:
            return None
        
        input_cost = input_tokens * model.pricing.input_cost_per_token
        output_cost = output_tokens * model.pricing.output_cost_per_token
        total_cost = input_cost + output_cost
        
        return total_cost
    
    def get_models_for_tier(self, tier: str) -> List[Model]:
        """获取指定层级的所有可用模型"""
        return self.registry.get_by_tier(tier, enabled_only=True)
    
    def get_models_with_capability(self, capability: ModelCapability) -> List[Model]:
        """获取具有指定能力的所有可用模型"""
        return self.registry.get_by_capability(capability, enabled_only=True)
    
    def select_best_model(
        self,
        tier: str,
        required_capabilities: Optional[List[ModelCapability]] = None,
        min_context_window: Optional[int] = None,
        prefer_cheaper: bool = False
    ) -> Optional[Model]:
        """根据条件选择最佳模型"""
        models = self.get_models_for_tier(tier)
        
        # 按能力筛选
        if required_capabilities:
            models = [
                m for m in models
                if all(cap in m.capabilities for cap in required_capabilities)
            ]
        
        # 按上下文窗口筛选
        if min_context_window:
            models = [m for m in models if m.context_window >= min_context_window]
        
        if not models:
            return None
        
        # 排序选择最佳模型
        if prefer_cheaper and any(m.pricing for m in models):
            models_with_pricing = [m for m in models if m.pricing]
            if models_with_pricing:
                models = sorted(
                    models_with_pricing,
                    key=lambda m: m.pricing.input_cost_per_million_tokens
                )
        else:
            models = sorted(
                models,
                key=lambda m: (-m.priority, not m.recommended)
            )
        
        return models[0] if models else None
    
    def get_default_model(self, tier: str = "free") -> Optional[Model]:
        """获取指定层级的默认模型"""
        models = self.get_models_for_tier(tier)
        
        # 优先选择推荐模型
        recommended = [m for m in models if m.recommended]
        if recommended:
            recommended = sorted(recommended, key=lambda m: -m.priority)
            return recommended[0]
        
        # 其次按优先级选择
        if models:
            models = sorted(models, key=lambda m: -m.priority)
            return models[0]
        
        return None
    
    def get_context_window(self, model_id: str, default: int = 31_000) -> int:
        """获取模型的上下文窗口大小"""
        return self.registry.get_context_window(model_id, default)
    
    def check_token_limit(
        self,
        model_id: str,
        token_count: int,
        is_input: bool = True
    ) -> Tuple[bool, int]:
        """检查token数量是否超过模型限制"""
        model = self.get_model(model_id)
        if not model:
            return False, 0
        
        if is_input:
            max_allowed = model.context_window
        else:
            max_allowed = model.max_output_tokens or model.context_window
        
        return token_count <= max_allowed, max_allowed
    
    def format_model_info(self, model_id: str) -> Dict[str, Any]:
        """格式化模型信息为字典格式"""
        model = self.get_model(model_id)
        if not model:
            return {"error": f"Model '{model_id}' not found"}
        
        return {
            "id": model.id,
            "name": model.name,
            "provider": model.provider.value,
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "capabilities": [cap.value for cap in model.capabilities],
            "pricing": {
                "input_per_million": model.pricing.input_cost_per_million_tokens,
                "output_per_million": model.pricing.output_cost_per_million_tokens,
            } if model.pricing else None,
            "enabled": model.enabled,
            "beta": model.beta,
            "tier_availability": model.tier_availability,
            "priority": model.priority,
            "recommended": model.recommended,
        }
    
    def list_available_models(
        self,
        tier: Optional[str] = None,
        include_disabled: bool = False
    ) -> List[Dict[str, Any]]:
        """列出可用的模型列表"""
        if tier:
            models = self.registry.get_by_tier(tier, enabled_only=not include_disabled)
        else:
            models = self.registry.get_all(enabled_only=not include_disabled)
        
        # 按照免费层级、优先级、名称排序
        models = sorted(
            models,
            key=lambda m: (not m.is_free_tier, -m.priority, m.name)
        )
        
        return [self.format_model_info(m.id) for m in models]
    
    def record_model_usage(self, model_id: str, input_tokens: int = 0, output_tokens: int = 0):
        """记录模型使用情况"""
        model_stats_manager.record_call(model_id, input_tokens, output_tokens)
    
    def get_model_stats(self, model_id: str):
        """获取模型使用统计"""
        return model_stats_manager.get_stats(model_id)
    
    def get_all_model_stats(self):
        """获取所有模型的使用统计"""
        return model_stats_manager.get_all_stats()


# 全局模型管理器实例
model_manager = ModelManager()

