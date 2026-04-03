from celery import Celery
from app.config.settings import settings
import asyncio
from app.agents.qualification import QualificationAgent
from app.services.hermes_service import HermesOrchestrator
from app.config.database import SessionLocal
from app.models.core import CallLog, Lead, Campaign, ScriptVersion
import logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    "outbound_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

@celery_app.task(name="score_lead_task")
def score_lead_task(call_sid: str, transcript: str):
    """
    Background task to score the lead after the call completes.
    """
    agent = QualificationAgent()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    score_data = loop.run_until_complete(agent.score_lead(transcript))

    # Save to database
    db = SessionLocal()
    try:
        call_log = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
        if call_log:
            call_log.outcome = score_data.get("interest_level")
            call_log.score = score_data
            db.commit()
    except Exception as e:
        print(f"Error saving score: {e}")
        db.rollback()
    finally:
        db.close()
    
    return score_data

@celery_app.task(name="enrich_lead_task")
def enrich_lead_task(lead_id: int):
    """
    Background Task: Uses Nous Research Hermes Agent to research a lead before calling.
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return "Lead not found"
        
        # Use our new Hermes Orchestrator (Nous Research framework)
        orchestrator = HermesOrchestrator(tenant_id=lead.tenant_id if hasattr(lead, 'tenant_id') else 1)
        success = orchestrator.research_lead(
            lead_id=lead_id, 
            lead_name=lead.name, 
            company=lead.company or lead.name
        )
        return "Success" if success else "Failed"
    finally:
        db.close()

@celery_app.task(name="evolve_scripts_task")
def evolve_scripts_task(campaign_id: int):
    """
    Background task to analyze transcripts and evolve scripts for all active campaigns.
    """
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            return "Campaign not found"
        
        # Fetch recent completed transcripts summary for Hermes
        logs = db.query(CallLog).filter(
            CallLog.lead_id.in_(db.query(Lead.id).filter(Lead.campaign_id == campaign.id)),
            CallLog.status == "completed",
            CallLog.transcript != None
        ).order_by(CallLog.created_at.desc()).limit(10).all()
        
        transcripts = [log.transcript for log in logs if log.transcript]
        if not transcripts:
            return "No transcripts available"

        transcript_summary = "\n---\n".join(transcripts)
        
        # Use Hermes Orchestrator
        orchestrator = HermesOrchestrator(tenant_id=campaign.tenant_id if hasattr(campaign, 'tenant_id') else 1)
        success = orchestrator.evolve_campaign(
            campaign_id=campaign_id,
            transcripts_summary=transcript_summary
        )
        
        return "Success" if success else "Failed"
    finally:
        db.close()

@celery_app.task(name="run_campaign_task")
def run_campaign_task(campaign_id: int):
    """
    Auto-dialer task: Iterates through all 'pending' leads in the campaign and triggers initiate_call.
    """
    from app.services.twilio_client import TwilioService
    from app.config.settings import settings
    
    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(
            Lead.campaign_id == campaign_id,
            Lead.status == "pending"
        ).all()
        
        for lead in leads:
            try:
                # 1. Trigger enrichment first (if not done)
                # We do this synchronously here or queue it as another task
                # To be fast, we trigger the call and let the voice webhook handle the rest
                
                call_sid = TwilioService.initiate_call(
                    to_number=lead.phone,
                    url=f"{settings.BASE_URL}/api/calls/voice"
                )
                
                # Create log
                call_log = CallLog(
                    call_sid=call_sid, 
                    lead_id=lead.id, 
                    tenant_id=lead.tenant_id if hasattr(lead, 'tenant_id') else 1, 
                    status="initiated"
                )
                db.add(call_log)
                
                # Mark lead as initiated so it's not dialed again
                lead.status = "initiated"
                db.commit()
                
            except Exception as e:
                logger.error(f"Failed to dial lead {lead.id}: {e}")
                
        return f"Dispatched {len(leads)} calls."
    finally:
        db.close()
