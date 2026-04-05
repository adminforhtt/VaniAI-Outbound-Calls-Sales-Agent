from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import csv
import io
import json
from app.config.database import get_db
from app.models.core import Lead, Campaign
from app.schemas.core import LeadCreate, LeadResponse
from app.services.security import get_auth_tenant

router = APIRouter()


@router.post("/", response_model=LeadResponse)
def create_lead(
    lead: LeadCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    db_lead = Lead(**lead.model_dump(), tenant_id=tenant_id)
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead


@router.get("/", response_model=List[LeadResponse])
def read_leads(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == tenant_id)
        .order_by(Lead.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return leads


@router.post("/upload")
async def upload_leads_csv(
    file: UploadFile = File(...),
    # Either attach to an existing campaign OR provide a custom description
    campaign_id: Optional[int] = None,
    # Custom description fields — used to auto-create a campaign on-the-fly
    custom_name: Optional[str] = Form(None),
    custom_script: Optional[str] = Form(None),
    custom_language: Optional[str] = Form(None),
    custom_voice: Optional[str] = Form(None),
    custom_llm_provider: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """
    Upload a CSV of leads and attach them to a campaign.
    
    You can either:
      - Pass campaign_id to attach to an existing campaign, OR
      - Pass custom_script (+ optional name/language/voice) to auto-create a campaign.
    
    CSV columns expected: name, phone, language (optional), company (optional), metadata (optional JSON)
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type — only .csv is accepted.")

    # ── RESOLVE CAMPAIGN ──────────────────────────────────────────────────────
    target_campaign_id = campaign_id

    if not target_campaign_id and custom_script:
        # Auto-create a campaign from the provided description
        name = custom_name or f"Bulk Campaign — {file.filename}"
        new_campaign = Campaign(
            name=name,
            script_template=custom_script,
            language=custom_language or "hi-IN",
            voice=custom_voice or "priya",
            llm_provider=custom_llm_provider or "groq",
            goal="Bulk outbound",
            tenant_id=tenant_id,
        )
        db.add(new_campaign)
        db.commit()
        db.refresh(new_campaign)
        target_campaign_id = new_campaign.id

    # ── PARSE CSV ─────────────────────────────────────────────────────────────
    contents = await file.read()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    inserted_leads = []
    errors = []
    for i, row in enumerate(reader, start=2):  # start=2 to account for header row
        phone = (row.get("phone") or row.get("Phone") or "").strip()
        if not phone:
            errors.append(f"Row {i}: missing phone number — skipped")
            continue

        # Parse optional metadata column
        raw_meta = row.get("metadata") or row.get("Metadata") or "{}"
        try:
            meta = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}

        lead = Lead(
            name=(row.get("name") or row.get("Name") or "Unknown").strip(),
            company=(row.get("company") or row.get("Company") or "").strip() or None,
            phone=phone,
            language=(row.get("language") or row.get("Language") or custom_language or "hi-IN").strip(),
            metadata_json=meta,
            campaign_id=target_campaign_id,
            tenant_id=tenant_id,
        )
        db.add(lead)
        inserted_leads.append(lead)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")

    result = {
        "message": f"Uploaded {len(inserted_leads)} leads successfully.",
        "count": len(inserted_leads),
        "campaign_id": target_campaign_id,
    }
    if errors:
        result["warnings"] = errors

    return result
