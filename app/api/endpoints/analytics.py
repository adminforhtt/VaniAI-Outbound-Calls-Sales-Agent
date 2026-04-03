from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.security import get_current_user
from app.services.analytics import AnalyticsService

router = APIRouter()

@router.get("/campaign/{campaign_id}/funnel")
def get_funnel(campaign_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]
    return AnalyticsService.get_campaign_funnel(db, tenant_id, campaign_id)

@router.get("/campaign/{campaign_id}/insights")
async def get_insights(campaign_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]
    return await AnalyticsService.generate_ai_insights(db, tenant_id, campaign_id)
