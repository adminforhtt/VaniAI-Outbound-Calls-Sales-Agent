from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.config.database import get_db
from app.models.core import Lead, CallLog
from app.schemas.core import ReportResponse
from app.services.security import get_auth_tenant

router = APIRouter()

@router.get("/summary/{lead_id}", response_model=ReportResponse)
def get_lead_summary(lead_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or unauthorized")
        
    call_log = db.query(CallLog).filter(CallLog.lead_id == lead_id).order_by(CallLog.created_at.desc()).first()
    if not call_log:
        raise HTTPException(status_code=404, detail="No call found for lead")
        
    return ReportResponse(
        lead_id=lead.id,
        phone=lead.phone,
        call_status=call_log.status,
        transcript=call_log.transcript,
        outcome=call_log.outcome,
        score=call_log.score,
        duration=call_log.duration,
        cost=call_log.cost
    )
