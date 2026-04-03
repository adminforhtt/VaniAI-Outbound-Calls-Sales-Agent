import logging
from sqlalchemy.orm import Session
from app.models.core import Tenant, CallLog

logger = logging.getLogger(__name__)

class BillingService:
    PRICE_PER_MINUTE = 0.05
    PRICE_PER_LEAD = 0.10

    @staticmethod
    def calculate_call_cost(duration_seconds: int) -> float:
        minutes = (duration_seconds + 59) // 60
        return minutes * BillingService.PRICE_PER_MINUTE

    @staticmethod
    def finalize_call_billing(db: Session, call_log: CallLog, tenant: Tenant):
        cost = BillingService.calculate_call_cost(call_log.duration)
        call_log.cost = cost
        tenant.total_minutes_used += ((call_log.duration + 59) // 60)
        tenant.total_leads_processed += 1
        
        logger.info(f"Billed Tenant {tenant.name} - ${cost} for Call {call_log.call_sid}")
        db.commit()
