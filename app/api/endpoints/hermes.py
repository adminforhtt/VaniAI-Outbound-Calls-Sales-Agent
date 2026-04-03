from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.core import Lead, Campaign, CallLog, ScriptVersion
from app.services.security import get_auth_tenant
from app.workers.celery_app import enrich_lead_task
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/lead/{lead_id}/research")
def get_lead_research(lead_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    """
    Returns the enrichment data (icebreaker, summary) for a specific lead.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not owned by your company")
    
    meta = lead.metadata_json or {}
    return {
        "lead_id": lead.id,
        "name": lead.name,
        "company": lead.company,
        "enrichment_status": meta.get("enrichment_status", "pending"),
        "research_summary": meta.get("description", "No research found yet."),
        "icebreaker": meta.get("icebreaker", "No icebreaker generated yet.")
    }

@router.post("/lead/{lead_id}/research/trigger")
def trigger_lead_research(lead_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    """
    Manually triggers the Hermes Agent to research a specific lead.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not owned by your company")
    
    # Update status to pending
    meta = lead.metadata_json or {}
    meta["enrichment_status"] = "pending"
    lead.metadata_json = meta
    db.commit()

    # Trigger Celery task
    enrich_lead_task.delay(lead_id)
    
    return {"status": "success", "message": f"Research triggered for lead {lead_id}"}

@router.get("/activity-logs")
def get_hermes_activity_logs(db: Session = Depends(get_db)):
    """
    Returns a unified list of recent Hermes actions (enriched leads, evolved scripts).
    """
    # 1. Get last 5 enriched leads
    enriched_leads = db.query(Lead).filter(
        Lead.metadata_json.contains({"enrichment_status": "enriched"})
    ).order_by(Lead.id.desc()).limit(5).all()

    logs = []
    for lead in enriched_leads:
        logs.append({
            "type": "enrichment",
            "message": f"Enriched lead '{lead.name}' from {lead.company or 'unknown company'}.",
            "timestamp": "Recent",
            "status": "success"
        })

    # 2. Get last 5 call scores (from Qualification Agent)
    scored_calls = db.query(CallLog).filter(
        CallLog.outcome != None
    ).order_by(CallLog.id.desc()).limit(5).all()

    for call in scored_calls:
        score = call.score or {}
        logs.append({
            "type": "scoring",
            "message": f"Qualified call for {call.lead_id}. Interest: {score.get('interest_level', 'Unknown')}.",
            "timestamp": "Recent",
            "status": "info"
        })

    # Sort logs (mocking timestamp sort for now since we're using 'Recent')
    return logs[:10]

@router.get("/campaign/{campaign_id}/versions")
def get_campaign_script_history(campaign_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    """
    Returns the version history of scripts for a campaign, including Hermes' reasoning.
    """
    # Verify campaign ownership
    from app.models.core import Campaign
    camp = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if not camp:
         raise HTTPException(status_code=404, detail="Campaign not found")

    versions = db.query(ScriptVersion).filter(
        ScriptVersion.campaign_id == campaign_id
    ).order_by(ScriptVersion.version.desc()).all()
    
    return [
        {
            "version": v.version,
            "content": v.script_content[:150] + "...",
            "reasoning": v.reasoning,
            "created_at": v.created_at
        } for v in versions
    ]
