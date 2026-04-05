from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.core import Lead, Campaign, CallLog, ScriptVersion
from app.services.security import get_auth_tenant
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/lead/{lead_id}/research")
def get_lead_research(
    lead_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """Returns the enrichment data (icebreaker, summary) for a specific lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    meta = lead.metadata_json or {}
    return {
        "lead_id": lead.id,
        "name": lead.name,
        "company": lead.company,
        "enrichment_status": lead.enrichment_status,
        "research_summary": meta.get("summary") or meta.get("description", "No research found yet."),
        "icebreaker": meta.get("icebreaker", "No icebreaker generated yet."),
        "pain_points": meta.get("pain_points", []),
        "pitch_angle": meta.get("pitch_angle", ""),
        "recent_activity": meta.get("recent_activity") or meta.get("recent_news", ""),
    }


@router.post("/lead/{lead_id}/research/trigger")
def trigger_lead_research(
    lead_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """Manually triggers lead enrichment for a specific lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Reset status so we re-run enrichment
    lead.enrichment_status = "pending"
    meta = lead.metadata_json or {}
    meta["enrichment_status"] = "pending"
    lead.metadata_json = meta
    db.commit()

    from app.worker.tasks import enrich_lead_task
    enrich_lead_task.delay(lead_id)

    return {"status": "success", "message": f"Research triggered for lead {lead_id}"}


@router.get("/activity-logs")
def get_hermes_activity_logs(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """Returns a unified list of recent enrichment and scoring activity."""
    logs = []

    # Recent enriched leads
    enriched_leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == tenant_id, Lead.enrichment_status == "enriched")
        .order_by(Lead.enriched_at.desc().nullslast(), Lead.id.desc())
        .limit(5)
        .all()
    )
    for lead in enriched_leads:
        meta = lead.metadata_json or {}
        logs.append({
            "type": "enrichment",
            "message": f"Enriched '{lead.name}' from {lead.company or 'unknown company'}. Icebreaker ready.",
            "timestamp": str(lead.enriched_at) if lead.enriched_at else "Recent",
            "status": "success",
        })

    # Recent scored calls
    scored_calls = (
        db.query(CallLog)
        .filter(CallLog.tenant_id == tenant_id, CallLog.outcome != None)
        .order_by(CallLog.id.desc())
        .limit(5)
        .all()
    )
    for call in scored_calls:
        score = call.score or {}
        logs.append({
            "type": "scoring",
            "message": f"Call scored for lead #{call.lead_id}. Interest: {score.get('interest_level', 'Unknown')}. Score: {score.get('score', '?')}/100.",
            "timestamp": str(call.completed_at) if call.completed_at else "Recent",
            "status": "info",
        })

    # Recent script evolutions
    versions = (
        db.query(ScriptVersion)
        .join(Campaign, ScriptVersion.campaign_id == Campaign.id)
        .filter(Campaign.tenant_id == tenant_id)
        .order_by(ScriptVersion.created_at.desc())
        .limit(3)
        .all()
    )
    for v in versions:
        if v.reasoning:
            logs.append({
                "type": "evolution",
                "message": f"Script v{v.version} evolved for campaign #{v.campaign_id}. Reason: {v.reasoning[:80]}...",
                "timestamp": str(v.created_at) if v.created_at else "Recent",
                "status": "success",
            })

    # Sort by most recent first (string sort works for ISO timestamps)
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs[:12]


@router.get("/campaign/{campaign_id}/versions")
def get_campaign_script_history(
    campaign_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """Returns the version history of scripts for a campaign."""
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.tenant_id == tenant_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    versions = (
        db.query(ScriptVersion)
        .filter(ScriptVersion.campaign_id == campaign_id)
        .order_by(ScriptVersion.version.desc())
        .all()
    )

    return [
        {
            "version": v.version,
            "content": v.script_content[:200] + "..." if len(v.script_content or "") > 200 else v.script_content,
            "reasoning": v.reasoning or "Initial deployment.",
            "created_at": str(v.created_at) if v.created_at else None,
        }
        for v in versions
    ]


@router.post("/campaign/{campaign_id}/evolve")
def evolve_campaign_script(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """Triggers script evolution analysis for a campaign (background task)."""
    camp = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.tenant_id == tenant_id
    ).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.worker.tasks import evolve_scripts_task
    task = evolve_scripts_task.delay(campaign_id)

    return {
        "status": "success",
        "task_id": task.id,
        "message": f"Script evolution started for campaign '{camp.name}'. Results in ~30–60 seconds.",
    }
