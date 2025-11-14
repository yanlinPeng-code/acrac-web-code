class RulesConfigRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用规则引擎")
    audit_only: bool = Field(True, description="仅审计不执行修订/过滤")

class RulesConfigResponse(BaseModel):
    enabled: bool
    audit_only: bool
    loaded_packs: int