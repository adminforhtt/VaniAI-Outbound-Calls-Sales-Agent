from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.core import Subscription, Tenant
from app.config.settings import settings
from app.services.security import get_auth_tenant
import razorpay
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Razorpay Client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)) if settings.RAZORPAY_KEY_ID else None

PLANS = {
    "free": {"name": "Free Tier", "limit": 50, "price": 0},
    "starter": {"name": "Starter", "limit": 500, "price": 399900}, # in paise (3999 INR)
    "growth": {"name": "Growth", "limit": 2000, "price": 1199900}, # 11999 INR
    "enterprise": {"name": "Enterprise", "limit": 10000, "price": 3999900}, # 39999 INR
}

@router.get("/plans")
def get_plans():
    return PLANS

@router.get("/usage")
def get_usage(db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id, plan="free", monthly_call_limit=50)
        db.add(sub)
        db.commit()
        db.refresh(sub)
    
    return {
        "plan": sub.plan,
        "used": sub.calls_this_month,
        "limit": sub.monthly_call_limit,
        "percentage": (sub.calls_this_month / sub.monthly_call_limit) * 100 if sub.monthly_call_limit > 0 else 0
    }

@router.post("/checkout")
async def create_checkout_session(plan: str, db: Session = Depends(get_db), tenant_id: int = Depends(get_auth_tenant)):
    if plan not in PLANS or plan == "free":
        raise HTTPException(status_code=400, detail="Invalid plan selected")
    
    if not razorpay_client:
        # Mocking for development if keys aren't set
        logger.info(f"Mocking Razorpay order for plan: {plan}")
        return {"order_id": f"order_mock_{plan}", "amount": PLANS[plan]["price"], "currency": "INR", "key_id": "rzp_test_mock"}

    try:
        order = razorpay_client.order.create({
            "amount": PLANS[plan]["price"],
            "currency": "INR",
            "receipt": f"receipt_{plan}_{tenant_id}", 
            "notes": {
                "plan": plan,
                "tenant_id": tenant_id
            }
        })
        logger.info(f"Created Razorpay order: {order['id']}")
        return {
            "order_id": order["id"], 
            "amount": order["amount"], 
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID
        }
    except Exception as e:
        logger.error(f"Error creating Razorpay order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")

@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    # Logic for handling Razorpay webhooks (subscription updates)
    payload = await request.body()
    sig_header = request.headers.get("X-Razorpay-Signature")
    
    try:
        # razorpay_client.utility.verify_webhook_signature(payload, sig_header, settings.RAZORPAY_WEBHOOK_SECRET)
        pass
    except Exception as e:
        return {"error": str(e)}

    # If successful payment signature updates Subscription in DB
    return {"status": "success"}
