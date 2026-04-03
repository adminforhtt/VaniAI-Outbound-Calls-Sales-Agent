from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # billing tracking
    total_minutes_used = Column(Float, default=0.0)
    total_leads_processed = Column(Integer, default=0)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="viewer") # admin, manager, viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String, index=True)
    script_template = Column(Text, nullable=False)
    language = Column(String, default="hi-IN")
    llm_provider = Column(String, default="groq")
    voice = Column(String, default="priya")
    goal = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String)
    phone = Column(String, index=True)
    language = Column(String, default="hi-IN")
    metadata_json = Column(JSON, default={})
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    status = Column(String, default="pending") 
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    call_sid = Column(String, unique=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    duration = Column(Integer, default=0)
    status = Column(String)
    recording_url = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    outcome = Column(String, nullable=True)
    score = Column(JSON, nullable=True)
    cost = Column(Float, default=0.0) # usage billing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
