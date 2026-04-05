from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.core import Subscription
from app.config.settings import settings
from app.services.security import get_auth_tenant
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Lazily initialize Razorpay client so missing keys don't crash the app
_razorpay_client = None

def _get_razorpay():
    global _razorpay_client
    if _razorpay_client is None and settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
        try:
            import razorpay
            _razorpay_client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            logger.info("Razorpay client initialized")
        except ImportError:
            logger.warning("razorpay package not installed — billing will run in mock mode")
    return _razorpay_client


PLANS = {
    "free":       {"name": "Free Tier",   "limit": 50,    "price": 0},
    "starter":    {"name": "Starter",     "limit": 500,   "price": 399900},   # ₹3,999 in paise
    "growth":     {"name": "Growth",      "limit": 2000,  "price": 1199900},  # ₹11,999 in paise
    "enterprise": {"name": "Enterprise",  "limit": 10000, "price": 3999900},  # ₹39,999 in paise
}

PLAN_LIMITS = {
    "free": 50,
    "starter": 500,
    "growth": 2000,
    "enterprise": 10000,
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
        "percentage": (sub.calls_this_month / sub.monthly_call_limit) * 100
        if sub.monthly_call_limit > 0 else 0,
    }


@router.post("/checkout")
async def create_checkout_session(
    plan: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    if plan not in PLANS or plan == "free":
        raise HTTPException(status_code=400, detail="Invalid plan selected")

    rzp = _get_razorpay()
    if not rzp:
        # Development mock — returns a fake order so the frontend can still render
        logger.info(f"Razorpay not configured — mocking order for plan: {plan}")
        return {
            "order_id": f"order_mock_{plan}_{tenant_id}",
            "amount": PLANS[plan]["price"],
            "currency": "INR",
            "key_id": "rzp_test_mock",
        }

    try:
        order = rzp.order.create({
            "amount": PLANS[plan]["price"],
            "currency": "INR",
            "receipt": f"vani_{plan}_{tenant_id}",
            "notes": {"plan": plan, "tenant_id": str(tenant_id)},
        })
        logger.info(f"Razorpay order created: {order['id']} for tenant {tenant_id}")
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
        }
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")


@router.post("/verify-payment")
async def verify_payment(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_auth_tenant),
):
    """
    Called by the frontend after Razorpay checkout succeeds.
    Verifies the payment signature and upgrades the subscription plan.
    """
    body = await request.json()
    razorpay_payment_id = body.get("razorpay_payment_id", "")
    razorpay_order_id = body.get("razorpay_order_id", "")
    razorpay_signature = body.get("razorpay_signature", "")
    plan = body.get("plan", "")

    if not plan or plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan in payment verification")

    rzp = _get_razorpay()

    if rzp and razorpay_signature:
        # Verify the payment signature for security
        try:
            params = {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
            rzp.utility.verify_payment_signature(params)
        except Exception as e:
            logger.error(f"Razorpay signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Payment signature verification failed")

    # Upgrade the subscription
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)

    sub.plan = plan
    sub.monthly_call_limit = PLAN_LIMITS.get(plan, 50)
    sub.razorpay_order_id = razorpay_order_id
    sub.razorpay_payment_id = razorpay_payment_id
    db.commit()

    logger.info(f"Subscription upgraded: tenant {tenant_id} → {plan}")
    return {"status": "success", "plan": plan, "limit": sub.monthly_call_limit}


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Razorpay server-to-server webhook for payment events.
    Verifies the webhook signature before processing.
    """
    payload = await request.body()
    sig_header = request.headers.get("X-Razorpay-Signature", "")

    rzp = _get_razorpay()
    if rzp and settings.RAZORPAY_WEBHOOK_SECRET and sig_header:
        try:
            rzp.utility.verify_webhook_signature(
                payload.decode("utf-8"),
                sig_header,
                settings.RAZORPAY_WEBHOOK_SECRET,
            )
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = payload.decode("utf-8")
        import json
        event_data = json.loads(event)
        event_type = event_data.get("event", "")

        if event_type == "payment.captured":
            payment = event_data.get("payload", {}).get("payment", {}).get("entity", {})
            # Extract tenant_id from order notes if available
            notes = payment.get("notes", {})
            tenant_id = notes.get("tenant_id")
            plan = notes.get("plan")

            if tenant_id and plan:
                tenant_id = int(tenant_id)
                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if sub:
                    sub.plan = plan
                    sub.monthly_call_limit = PLAN_LIMITS.get(plan, 50)
                    sub.razorpay_payment_id = payment.get("id")
                    db.commit()
                    logger.info(f"Webhook: Upgraded tenant {tenant_id} to {plan}")

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")

    return {"status": "ok"}
