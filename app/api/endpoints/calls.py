from fastapi import APIRouter, Request, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response, PlainTextResponse
from sqlalchemy.orm import Session
import logging
import asyncio
import time
from pydantic import BaseModel
from app.config.database import get_db
from app.models.core import Lead, CallLog, Campaign, Subscription
from app.services.twilio_client import TwilioService
from app.config.settings import settings
from app.services.redis_store import redis_client
from app.services.conversation_manager import ConversationManager
from app.services.security import get_auth_tenant
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

HERMES_WAIT_TIMEOUT = 1  # Instant dial for test calls/gate

def classify_interest(transcript: str) -> str:
    """Simple heuristic to figure out lead interest based on full transcript."""
    transcript_lower = transcript.lower()
    if "yes " in transcript_lower or "interested" in transcript_lower or "ho" in transcript_lower or "हाँ" in transcript_lower:
        return "high"
    elif "not interested" in transcript_lower or "no " in transcript_lower or "nahi" in transcript_lower or "नहीं" in transcript_lower:
        return "low"
    else:
        return "medium"

def suggest_next_step(interest: str) -> str:
    if interest == "high":
        return "follow_up"
    elif interest == "medium":
        return "nurture"
    else:
        return "drop"

def wait_for_hermes(lead_id: int, db: Session, timeout: int = HERMES_WAIT_TIMEOUT) -> bool:
    """
    Polls the database for up to `timeout` seconds waiting for enrichment to finish.
    Returns immediately (True = proceed) if enrichment is 'enriched' or 'failed'.
    Call always proceeds — we never block longer than timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return False
        db.refresh(lead)
        if lead.enrichment_status == "enriched":
            logger.info(f"HERMES_GATE: Lead {lead_id} enriched in {time.time() - start:.1f}s — proceeding")
            return True
        if lead.enrichment_status == "failed":
            logger.warning(f"HERMES_GATE: Lead {lead_id} enrichment failed — proceeding with generic script")
            return False
        time.sleep(0.5)
    logger.warning(f"HERMES_GATE: Lead {lead_id} timed out after {timeout}s — proceeding with generic script")
    return False

def check_subscription_limit(db: Session, tenant_id: int):
    """Checks if a tenant has remaining calls for the month."""
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        # Auto-create free tier for new tenants
        sub = Subscription(tenant_id=tenant_id, plan="free", monthly_call_limit=50)
        db.add(sub)
        db.commit()
    
    if sub.calls_this_month >= sub.monthly_call_limit:
        return False, sub
    
    sub.calls_this_month += 1
    db.commit()
    return True, sub

@router.post("/initiate")
def initiate_call(lead_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # 1. Billing Gate
    allowed, sub = check_subscription_limit(db, lead.tenant_id)
    if not allowed:
        raise HTTPException(status_code=402, detail=f"Monthly call limit reached ({sub.monthly_call_limit}). Please upgrade.")

    # 2. Trigger Enrichment if not already done (non-blocking — call always proceeds)
    if lead.enrichment_status == "pending":
        try:
            from app.worker.tasks import enrich_lead_task
            enrich_lead_task.delay(lead.id)
            wait_for_hermes(lead.id, db)
        except Exception as e:
            logger.warning(f"Enrichment skipped (Celery/Redis unavailable): {e}")

    base_url = settings.BASE_URL.rstrip('/')
    try:
        call_sid = TwilioService.initiate_call(
            to_number=lead.phone,
            url=f"{base_url}/api/calls/voice"
        )
    except Exception as e:
        logger.error(f"Twilio initiation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Twilio Error: {str(e)}")

    call_log = CallLog(call_sid=call_sid, lead_id=lead_id, tenant_id=lead.tenant_id, status="initiated")
    db.add(call_log)
    db.commit()

    return {"message": "Call initiated", "call_sid": call_sid}

class TestCallRequest(BaseModel):
    phone_number: str
    script: str
    llm_provider: str = "openrouter" # openrouter or groq
    voice: str = "priya" # priya or male etc
    language: str = "hi-IN"

@router.post("/test-call")
def initiate_test_call(request: TestCallRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    
    # Check limit
    allowed, sub = check_subscription_limit(db, tenant_id)
    if not allowed:
        raise HTTPException(status_code=402, detail=f"Monthly call limit reached ({sub.monthly_call_limit}). Please upgrade.")

    # Create a dummy lead and campaign to track this test call
    campaign = db.query(Campaign).filter(Campaign.name == "Quick Test Campaign", Campaign.tenant_id == tenant_id).first()
    if not campaign:
        campaign = Campaign(
            name="Quick Test Campaign", 
            tenant_id=tenant_id,
            script_template=request.script,
            llm_provider=request.llm_provider,
            voice=request.voice,
            language=request.language
        )
        db.add(campaign)
        db.commit()
    else:
        campaign.script_template = request.script
        campaign.llm_provider = request.llm_provider
        campaign.voice = request.voice
        campaign.language = request.language
        db.commit()

    # Create lead for tracking
    lead = Lead(name="Test User", phone=request.phone_number, tenant_id=tenant_id, campaign_id=campaign.id, status="pending")
    db.add(lead)
    db.commit()
    
    # Trigger enrichment asynchronously via FastAPI background task 
    # to completely eliminate the risk of Celery/Redis blocking the main API thread
    def _trigger_enrichment(lead_id):
        try:
            from app.worker.tasks import enrich_lead_task
            enrich_lead_task.delay(lead_id)
        except Exception as e:
            logger.warning(f"Background enrichment failed: {e}")
            
    background_tasks.add_task(_trigger_enrichment, lead.id)

    base_url = settings.BASE_URL.rstrip('/')
    try:
        call_sid = TwilioService.initiate_call(
            to_number=lead.phone,
            url=f"{base_url}/api/calls/voice"
        )
    except Exception as e:
        logger.error(f"Twilio initiation failed: {e}")
        # Mark as failed
        lead.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=f"Twilio Error: {str(e)}")

    call_log = CallLog(call_sid=call_sid, lead_id=lead.id, tenant_id=tenant_id, status="initiated")
    db.add(call_log)
    db.commit()

    return {"message": "Test call initiated", "call_sid": call_sid, "lead_id": lead.id}

@router.post("/voice")
async def voice_webhook(request: Request):
    """
    Twilio posts here when a call connects. We respond with TwiML to start a WebSocket stream.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    # Initialize session and state
    await redis_client.save_session(call_sid, {"history": [], "state": "INIT"})

    base_url = settings.BASE_URL.rstrip('/')
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + f"/api/calls/stream/{call_sid}"
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="{ws_url}" />
        </Connect>
    </Response>
    """
    return Response(content=twiml, media_type="application/xml")

@router.websocket("/stream/{call_sid}")
async def call_stream(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for call {call_sid}")
    
    manager = ConversationManager(websocket, call_sid)
    try:
        # Start the real-time asynchronous streaming loops
        await manager.start()
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call {call_sid}")
    except Exception as e:
        logger.error(f"Error in websocket stream: {e}")

@router.post("/recording")
async def recording_webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    recording_url = form_data.get("RecordingUrl")
    
    call_log = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
    if call_log:
        call_log.recording_url = recording_url
        db.commit()

    return {"status": "ok"}

@router.post("/status")
async def status_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    status = form_data.get("CallStatus")
    duration = form_data.get("CallDuration", 0)
    
    call_log = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
    if call_log:
        call_log.status = status
        call_log.duration = int(duration)
        db.commit()

        if status == "completed":
            # fetch full transcript from redis
            history = await redis_client.get_history(call_sid)
            transcript = "\n".join([f"{str(msg['role']).capitalize()}: {msg['content']}" for msg in history])
            call_log.transcript = transcript
            db.commit()
            
            # Predict outcome mathematically
            interest = classify_interest(transcript)
            next_action = suggest_next_step(interest)
            
            call_outcome = {
                "call_sid": call_sid,
                "lead_id": call_log.lead_id,
                "status": status,
                "duration": int(duration),
                "transcript": transcript,
                "lead_interest": interest,
                "next_action": next_action,
                "timestamp": str(datetime.utcnow())
            }
            logger.info(f"CALL_OUTCOME: {call_outcome}")
            
            # FUTURE-PROOFING: Store transcript in lead metadata for Hermes learning loop
            if call_log.lead_id:
                lead = db.query(Lead).filter(Lead.id == call_log.lead_id).first()
                if lead:
                    meta = lead.metadata_json or {}
                    meta["last_transcript"] = transcript[:2000]  # Cap at 2000 chars
                    meta["last_call_status"] = status
                    meta["last_call_duration"] = int(duration)
                    meta["lead_interest"] = interest
                    meta["next_action"] = next_action
                    lead.metadata_json = meta
                    db.commit()
                    logger.info(f"FUTURE_HOOK: Stored transcript for lead {lead.id} ({len(transcript)} chars)")
            
            # Queue background task for qualification (non-fatal if Celery is down)
            try:
                from app.worker.tasks import score_lead_task
                background_tasks.add_task(score_lead_task.delay, call_sid, transcript)
            except Exception as e:
                logger.warning(f"Lead scoring skipped (Celery/Redis unavailable): {e}")
            
    return {"status": "ok"}

@router.get("/{call_sid}/transcript/download")
async def download_transcript(call_sid: str, db: Session = Depends(get_db)):
    call_log = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
    if not call_log or not call_log.transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
        
    return PlainTextResponse(
        content=call_log.transcript,
        headers={"Content-Disposition": f"attachment; filename=transcript_{call_sid}.txt"}
    )

