from fastapi import APIRouter, Request, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response, PlainTextResponse
from sqlalchemy.orm import Session
import logging
import asyncio
from pydantic import BaseModel
from app.config.database import get_db
from app.models.core import Lead, CallLog
from app.services.twilio_client import TwilioService
from app.config.settings import settings
from app.services.redis_store import redis_client
from app.services.conversation_manager import ConversationManager
from app.workers.celery_app import score_lead_task

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/initiate")
def initiate_call(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"error": "Lead not found"}

    call_sid = TwilioService.initiate_call(
        to_number=lead.phone,
        url=f"{settings.BASE_URL}/api/calls/voice"
    )

    call_log = CallLog(call_sid=call_sid, lead_id=lead_id, status="initiated")
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
def initiate_test_call(request: TestCallRequest, db: Session = Depends(get_db)):
    # Create a dummy lead and campaign to track this test call
    from app.models.core import Campaign
    # Ensure a test campaign exists
    campaign = db.query(Campaign).filter(Campaign.name == "Quick Test Campaign").first()
    if not campaign:
        campaign = Campaign(
            name="Quick Test Campaign", 
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

    lead = Lead(name="Test User", phone=request.phone_number, campaign_id=campaign.id, status="pending")
    db.add(lead)
    db.commit()

    call_sid = TwilioService.initiate_call(
        to_number=lead.phone,
        url=f"{settings.BASE_URL}/api/calls/voice"
    )

    call_log = CallLog(call_sid=call_sid, lead_id=lead.id, status="initiated")
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

    ws_url = settings.BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + f"/api/calls/stream/{call_sid}"
    
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
            
            # Queue background task for qualification
            background_tasks.add_task(score_lead_task.delay, call_sid, transcript)
            
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

