import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.core import CallLog, Lead, Campaign

logger = logging.getLogger(__name__)

class AnalyticsService:
    @staticmethod
    def get_campaign_funnel(db: Session, tenant_id: int, campaign_id: int):
        total_leads = db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.campaign_id == campaign_id).count()
        called_leads = db.query(CallLog).join(Lead).filter(Lead.tenant_id == tenant_id, Lead.campaign_id == campaign_id).count()
        
        # Example calculation for outcomes
        interested = db.query(CallLog).join(Lead).filter(
            Lead.tenant_id == tenant_id, 
            Lead.campaign_id == campaign_id,
            CallLog.outcome == "High"  # depends on your AI agent scoring output
        ).count()

        return {
            "total_leads": total_leads,
            "calls_made": called_leads,
            "interested_leads": interested,
            "conversion_rate": (interested / called_leads * 100) if called_leads > 0 else 0
        }

    @staticmethod
    async def generate_ai_insights(db: Session, tenant_id: int, campaign_id: int):
        from app.services.llm import LLMService
        # Gather sample failing transcripts to analyze
        failed_calls = db.query(CallLog).join(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.campaign_id == campaign_id,
            CallLog.outcome == "Not Interested"
        ).order_by(CallLog.created_at.desc()).limit(5).all()
        
        if not failed_calls:
            return {"insight": "Not enough data to generate insights yet."}

        transcripts_bundle = "\n---\n".join([c.transcript for c in failed_calls if c.transcript])
        
        system_prompt = """You are a campaign analytics AI. Analyze these failed call transcripts and provide insights.
Generate:
1. Why leads are dropping
2. Best script improvements
3. Optimal call timing (if data implies, or general advice)
Return as simple structured text."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transcripts:\n{transcripts_bundle}"}
        ]
        
        response = await LLMService.generate_response(messages, provider="openrouter")
        return {"insight": response}
