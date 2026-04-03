from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.config.database import get_db
from app.models.core import Campaign
from app.schemas.core import CampaignCreate, CampaignResponse

router = APIRouter()

@router.post("/", response_model=CampaignResponse)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    db_campaign = Campaign(**campaign.model_dump())
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign

@router.get("/", response_model=List[CampaignResponse])
def get_campaigns(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).offset(skip).limit(limit).all()
    return campaigns

@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign
