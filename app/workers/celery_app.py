from celery import Celery
from app.config.settings import settings
import asyncio
from app.agents.qualification import QualificationAgent
from app.config.database import SessionLocal
from app.models.core import CallLog

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
    # Run async function in sync context
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
