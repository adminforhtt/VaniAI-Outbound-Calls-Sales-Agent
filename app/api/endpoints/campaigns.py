from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.config.database import get_db
from app.models.core import Campaign
from app.schemas.core import CampaignCreate, CampaignResponse
from app.services.security import get_auth_tenant

router = APIRouter()

@router.post("/", response_model=CampaignResponse)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    db_campaign = Campaign(**campaign.model_dump(), tenant_id=tenant_id)
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign

@router.get("/", response_model=List[CampaignResponse])
def get_campaigns(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    campaigns = db.query(Campaign).filter(Campaign.tenant_id == tenant_id).offset(skip).limit(limit).all()
    return campaigns

@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@router.post("/{campaign_id}/launch")
def launch_campaign(campaign_id: int, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    from app.workers.celery_app import run_campaign_task
    task = run_campaign_task.delay(campaign_id)
    return {"status": "success", "task_id": task.id, "message": "Campaign launch initiated."}
