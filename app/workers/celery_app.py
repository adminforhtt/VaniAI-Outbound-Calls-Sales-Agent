from celery import Celery
from app.config.settings import settings
import asyncio
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
    from app.agents.qualification import QualificationAgent
    from app.config.database import SessionLocal
    from app.models.core import CallLog

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


@celery_app.task(name="enrich_lead_task")
def enrich_lead_task(lead_id: int):
    """
    Background task: uses LeadEnrichmentService (Groq/OpenRouter) to research
    a lead before the call. Falls back gracefully if anything fails.
    """
    from app.config.database import SessionLocal
    from app.models.core import Lead

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.warning(f"enrich_lead_task: Lead {lead_id} not found — skipping")
            return "Lead not found"

        # Skip if already enriched
        if lead.enrichment_status == "enriched":
            logger.info(f"enrich_lead_task: Lead {lead_id} already enriched — skipping")
            return "Already enriched"

        company = lead.company or lead.name or "Unknown Company"

    finally:
        db.close()

    # Import here to avoid circular imports at module load time
    try:
        from app.services.hermes_service import LeadEnrichmentService
        service = LeadEnrichmentService(tenant_id=1)
        success = service.research_lead(
            lead_id=lead_id,
            lead_name=lead.name,
            company=company
        )
        return "Success" if success else "Failed"
    except Exception as e:
        logger.error(f"enrich_lead_task: Enrichment failed for lead {lead_id}: {e}")
        # Mark as failed so the call gate doesn't wait forever
        _mark_enrichment_failed(lead_id)
        return "Failed"


def _mark_enrichment_failed(lead_id: int):
    """Mark a lead's enrichment as failed so the call gate doesn't block."""
    from app.config.database import SessionLocal
    from app.models.core import Lead
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.enrichment_status = "failed"
            db.commit()
    except Exception as e:
        logger.error(f"_mark_enrichment_failed: {e}")
        db.rollback()
    finally:
        db.close()


@celery_app.task(name="evolve_scripts_task")
def evolve_scripts_task(campaign_id: int):
    """
    Background task: analyzes transcripts and evolves the campaign script.
    """
    from app.config.database import SessionLocal
    from app.models.core import Campaign, CallLog, Lead

    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            return "Campaign not found"

        logs = db.query(CallLog).filter(
            CallLog.lead_id.in_(
                db.query(Lead.id).filter(Lead.campaign_id == campaign.id)
            ),
            CallLog.status == "completed",
            CallLog.transcript != None
        ).order_by(CallLog.created_at.desc()).limit(10).all()

        transcripts = [log.transcript for log in logs if log.transcript]
        if not transcripts:
            return "No transcripts available"

        transcript_summary = "\n---\n".join(transcripts)
    finally:
        db.close()

    try:
        from app.services.hermes_service import LeadEnrichmentService
        service = LeadEnrichmentService(tenant_id=campaign.tenant_id if hasattr(campaign, "tenant_id") else 1)
        success = service.evolve_campaign(
            campaign_id=campaign_id,
            transcripts_summary=transcript_summary
        )
        return "Success" if success else "Failed"
    except Exception as e:
        logger.error(f"evolve_scripts_task: Failed for campaign {campaign_id}: {e}")
        return "Failed"


@celery_app.task(name="run_campaign_task")
def run_campaign_task(campaign_id: int):
    """
    Auto-dialer task: iterates through all 'pending' leads in the campaign
    and triggers a Twilio call for each.
    """
    from app.services.twilio_client import TwilioService
    from app.config.database import SessionLocal
    from app.models.core import Lead, CallLog

    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(
            Lead.campaign_id == campaign_id,
            Lead.status == "pending"
        ).all()

        dispatched = 0
        for lead in leads:
            try:
                call_sid = TwilioService.initiate_call(
                    to_number=lead.phone,
                    url=f"{settings.BASE_URL}/api/calls/voice"
                )

                call_log = CallLog(
                    call_sid=call_sid,
                    lead_id=lead.id,
                    tenant_id=lead.tenant_id if hasattr(lead, "tenant_id") else 1,
                    status="initiated"
                )
                db.add(call_log)
                lead.status = "initiated"
                db.commit()
                dispatched += 1

            except Exception as e:
                logger.error(f"run_campaign_task: Failed to dial lead {lead.id}: {e}")

        return f"Dispatched {dispatched} of {len(leads)} calls."
    finally:
        db.close()
