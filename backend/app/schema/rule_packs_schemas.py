
class RulesPacksRequest(BaseModel):
    content: Dict[str, Any] = Field(..., description="完整规则包JSON对象，包含 packs 列表")

class RulesPacksResponse(BaseModel):
    content: Dict[str, Any]
