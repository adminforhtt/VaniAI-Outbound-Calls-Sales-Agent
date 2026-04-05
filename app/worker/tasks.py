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
    name="vani_ai.enrich_lead",
    queue="enrichment",
    # Auto-retry these specific exception types immediately
    autoretry_for=(OperationalError, ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 5, "countdown": 5},
    # Task-level timeout — kill task if it runs > 5 minutes
    time_limit=300,
    soft_time_limit=240,  # sends SIGTERM at 4min, SIGKILL at 5min
)
def enrich_lead_task(self, lead_id: str, campaign_id: str) -> dict:
    """
    Enrich a lead via Hermes agent.
    Retries up to 5 times on connection/timeout errors.
    Updates lead record in DB on success.
    """
    logger.info(f"[enrich_lead] Starting enrichment. lead_id={lead_id}, campaign_id={campaign_id}")

    try:
        from app.models.core import Lead
        
        # Build session
        try:
            from app.db.session import get_db
            session = next(get_db())
        except ImportError:
            from app.models.core import SessionLocal
            session = SessionLocal()
            
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found in DB")
            
        tenant_id = getattr(lead, "tenant_id", 1)
        name = lead.name or "Unknown"
        meta = lead.metadata_json or {}
        company = meta.get("company", "Unknown Company")
        
        session.close()

        # Instantiate LeadEnrichmentService
        service = LeadEnrichmentService(tenant_id=tenant_id)
        
        # Run enrichment (this writes to DB implicitly via save_lead_research)
        success = service.research_lead(lead_id=lead_id, lead_name=name, company=company)

        if not success:
            raise ValueError(f"Hermes failed to generate research for lead {lead_id}")

        logger.info(f"[enrich_lead] ✅ Completed for lead_id={lead_id}")
        return {"status": "success", "lead_id": lead_id}

    except (OperationalError, ConnectionError, TimeoutError) as e:
        # These are retriable — Celery autoretry handles them
        raise

    except Exception as e:
        logger.exception(f"[enrich_lead] Non-retriable error for lead {lead_id}: {e}")
        # Mark as failed in DB
        try:
            from app.models.core import Lead
            try:
                from app.db.session import get_db
                session = next(get_db())
            except ImportError:
                from app.models.core import SessionLocal
                session = SessionLocal()
                
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.enrichment_status = "failed"
                lead.enrichment_error = str(e)
                session.commit()
            session.close()
        except Exception as db_e:
            logger.error(f"[enrich_lead] Also failed to update DB: {db_e}")
        raise


@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="vani_ai.health_check",
    queue="default",
)
def celery_health_check(self) -> dict:
    return {"status": "alive", "worker_id": self.request.hostname}

@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="vani_ai.run_campaign_task",
    queue="default"
)
def run_campaign_task(self, campaign_id: int):
    logger.info(f"Starting bulk dial for campaign {campaign_id}")
    try:
        from app.db.session import get_db
        session = next(get_db())
    except ImportError:
        from app.models.core import SessionLocal
        session = SessionLocal()

    from app.models.core import Lead, CallLog
    from app.services.twilio_client import TwilioService
    from app.config.settings import settings
    import time
    
    leads = session.query(Lead).filter(Lead.campaign_id == campaign_id, Lead.status == 'pending').all()
    base_url = settings.BASE_URL.rstrip('/')
    url = f"{base_url}/api/calls/voice"

    for lead in leads:
        try:
            call_sid = TwilioService.initiate_call(to_number=lead.phone, url=url)
            lead.status = "initiated"
            call_log = CallLog(call_sid=call_sid, lead_id=lead.id, tenant_id=lead.tenant_id, status="initiated")
            session.add(call_log)
        except Exception as e:
            logger.error(f"Failed to dial {lead.phone}: {e}")
            lead.status = "failed"
        session.commit()
        time.sleep(1) # pacing
        
    session.close()
    return {"status": "success", "campaign": campaign_id, "leads_dialed": len(leads)}
