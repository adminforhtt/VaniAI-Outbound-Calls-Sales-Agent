# app/worker/tasks.py

import logging
from celery import Task
from kombu.exceptions import OperationalError

from app.worker.celery_app import celery_app
from app.services.hermes_service import hermes_enrich  # Note: instruction said hermes_agent but current is hermes_service

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
        result = hermes_enrich(lead_id=lead_id, campaign_id=campaign_id)

        if not result:
            raise ValueError(f"Hermes returned empty result for lead {lead_id}")

        # Update lead status in DB
        from app.models.core import db
        from app.models.core import Lead
        from sqlalchemy.orm import Session
        import contextlib

        # Try to use existing db session dependency
        try:
            from app.db.session import get_db
            session = next(get_db())
        except ImportError:
            # Fallback
            from app.models.core import SessionLocal
            session = SessionLocal()

        try:
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.enrichment_status = "completed"
                lead.enrichment_data = result
                session.commit()
        finally:
            session.close()

        logger.info(f"[enrich_lead] ✅ Completed for lead_id={lead_id}")
        return {"status": "success", "lead_id": lead_id, "data": result}

    except (OperationalError, ConnectionError, TimeoutError) as e:
        # These are retriable — Celery autoretry handles them
        raise

    except Exception as e:
        logger.exception(f"[enrich_lead] Non-retriable error for lead {lead_id}: {e}")
        # Update lead as failed in DB
        try:
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
        raise  # Mark task as failed in Celery result backend


@celery_app.task(
    base=BaseVaniTask,
    bind=True,
    name="vani_ai.health_check",
    queue="default",
)
def celery_health_check(self) -> dict:
    """Lightweight task to verify Celery worker is alive. Called by /health endpoint."""
    return {"status": "alive", "worker_id": self.request.hostname}
