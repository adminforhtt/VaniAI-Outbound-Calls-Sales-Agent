from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io
import json
from app.config.database import get_db
from app.models.core import Lead, Campaign
from app.schemas.core import LeadCreate, LeadResponse

router = APIRouter()

@router.post("/", response_model=LeadResponse)
def create_lead(lead: LeadCreate, db: Session = Depends(get_db)):
    db_lead = Lead(**lead.model_dump())
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead

@router.get("/", response_model=List[LeadResponse])
def read_leads(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    leads = db.query(Lead).offset(skip).limit(limit).all()
    return leads

@router.post("/upload")
async def upload_leads_csv(file: UploadFile = File(...), campaign_id: int = None, db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only CSV allowed.")
    
    contents = await file.read()
    reader = csv.DictReader(io.StringIO(contents.decode("utf-8")))
    
    inserted_leads = []
    for row in reader:
        # Expected CSV columns: name, phone, language, metadata
        lead = Lead(
            name=row.get("name"),
            phone=row.get("phone"),
            language=row.get("language", "en-IN"),
            metadata_json=json.loads(row.get("metadata", "{}")),
            campaign_id=campaign_id
        )
        db.add(lead)
        inserted_leads.append(lead)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
        
    return {"message": f"Successfully uploaded {len(inserted_leads)} leads."}
