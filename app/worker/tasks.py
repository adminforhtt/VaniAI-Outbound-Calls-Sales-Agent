# app/worker/tasks.py

import logging
from celery import Task
from kombu.exceptions import OperationalError

from app.worker.celery_app import celery_app
from app.services.hermes_service import LeadEnrichmentService

logger = logging.getLogger(__name__)


class BaseVaniTask(Task):
    """
    Base class for all Vani AI tasks.
    Provides:
    - Automatic retry on Redis/connection errors
    - Structured logging on failure
    - On-failure callback hook
    """
    abstract = True
    max_retries = 5
    default_retry_delay = 5  # seconds between retries

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            f"[{self.name}] Permanent failure after {self.max_retries} retries. "
            f"Task ID: {task_id}. Error: {exc}",
            exc_info=True
        )
        # Override in subclass to send alerts, update DB, etc.

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(
            f"[{self.name}] Retrying (attempt {self.request.retries + 1}"
            f"/{self.max_retries}). Error: {exc}"
        )


@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="enrich_lead_task",  # Standard name used by API
    queue="enrichment",
    autoretry_for=(OperationalError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 5, "countdown": 5},
    time_limit=300,
    soft_time_limit=240,
)
def enrich_lead_task(self, lead_id: int) -> str:
    """
    Enrich a lead via Hermes agent.
    """
    logger.info(f"[enrich_lead] Starting enrichment. lead_id={lead_id}")
    try:
        from app.models.core import Lead
        try:
            from app.db.session import get_db
            session = next(get_db())
        except ImportError:
            from app.models.core import SessionLocal
            session = SessionLocal()
            
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return "Lead not found"
            
        tenant_id = getattr(lead, "tenant_id", 1)
        name = lead.name or "Unknown"
        company = lead.company or name
        session.close()

        service = LeadEnrichmentService(tenant_id=tenant_id)
        success = service.research_lead(lead_id=lead_id, lead_name=name, company=company)
        return "Success" if success else "Failed"

    except (OperationalError, ConnectionError, TimeoutError):
        raise
    except Exception as e:
        logger.exception(f"[enrich_lead] Error for lead {lead_id}: {e}")
        return "Failed"


@celery_app.task(name="score_lead_task")
def score_lead_task(call_sid: str, transcript: str):
    from app.agents.qualification import QualificationAgent
    from app.config.database import SessionLocal
    from app.models.core import CallLog
    import asyncio

    agent = QualificationAgent()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    score_data = loop.run_until_complete(agent.score_lead(transcript))
    db = SessionLocal()
    try:
        call_log = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
        if call_log:
            call_log.outcome = score_data.get("interest_level")
            call_log.score = score_data
            db.commit()
    except Exception as e:
        logger.error(f"Error saving score for {call_sid}: {e}")
        db.rollback()
    finally:
        db.close()
    return score_data


@celery_app.task(name="evolve_scripts_task")
def evolve_scripts_task(campaign_id: int):
    from app.config.database import SessionLocal
    from app.models.core import Campaign, CallLog, Lead
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign: return "Campaign not found"
        logs = db.query(CallLog).filter(
            CallLog.lead_id.in_(db.query(Lead.id).filter(Lead.campaign_id == campaign_id)),
            CallLog.status == "completed",
            CallLog.transcript != None
        ).order_by(CallLog.created_at.desc()).limit(10).all()
        transcripts = [log.transcript for log in logs if log.transcript]
        if not transcripts: return "No transcripts available"
        ts_summary = "\n---\n".join(transcripts)
    finally:
        db.close()
    try:
        from app.services.hermes_service import LeadEnrichmentService
        service = LeadEnrichmentService(tenant_id=campaign.tenant_id if hasattr(campaign, "tenant_id") else 1)
        success = service.evolve_campaign(campaign_id=campaign_id, transcripts_summary=ts_summary)
        return "Success" if success else "Failed"
    except Exception as e:
        logger.error(f"evolve_scripts_task: {e}")
        return "Failed"


@celery_app.task(name="run_campaign_task")
def run_campaign_task(campaign_id: int):
    logger.info(f"Starting bulk dial for campaign {campaign_id}")
    from app.config.database import SessionLocal
    from app.models.core import Lead, CallLog
    from app.services.twilio_client import TwilioService
    from app.config.settings import settings
    import time
    
    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(Lead.campaign_id == campaign_id, Lead.status == 'pending').all()
        base_url = settings.BASE_URL.rstrip('/')
        for lead in leads:
            try:
                call_sid = TwilioService.initiate_call(to_number=lead.phone, url=f"{base_url}/api/calls/voice")
                lead.status = "initiated"
                db.add(CallLog(call_sid=call_sid, lead_id=lead.id, tenant_id=lead.tenant_id, status="initiated"))
                db.commit()
            except Exception as e:
                logger.error(f"Failed to dial {lead.phone}: {e}")
                lead.status = "failed"
                db.commit()
            time.sleep(1) # pacing
        return f"Dialed {len(leads)} leads"
    finally:
        db.close()
