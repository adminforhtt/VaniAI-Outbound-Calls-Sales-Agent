from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime

class TenantBase(BaseModel):
    name: str

class TenantResponse(TenantBase):
    id: int
    api_key: Optional[str] = None
    total_minutes_used: float
    total_leads_processed: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class CampaignBase(BaseModel):
    name: str
    script_template: str
    language: str
    llm_provider: str = "groq"
    voice: str = "priya"
    goal: Optional[str] = None

class CampaignCreate(CampaignBase):
    pass

class CampaignResponse(CampaignBase):
    id: int
    tenant_id: Optional[int] = None
    active: bool = True
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class LeadBase(BaseModel):
    name: str
    company: Optional[str] = None
    phone: str
    language: str = "hi-IN"
    metadata_json: Optional[Dict[str, Any]] = {}
    campaign_id: Optional[int] = None

class LeadCreate(LeadBase):
    pass

class LeadResponse(LeadBase):
    id: int
    tenant_id: Optional[int] = None
    status: str = "pending"
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ReportResponse(BaseModel):
    lead_id: int
    phone: str
    call_status: str
    transcript: Optional[str] = None
    outcome: Optional[str] = None
    score: Optional[Dict[str, Any]] = None
    duration: int
    cost: float

class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str
    company_name: str

class UserResponse(UserBase):
    id: int
    tenant_id: int
    role: str
    model_config = ConfigDict(from_attributes=True)
