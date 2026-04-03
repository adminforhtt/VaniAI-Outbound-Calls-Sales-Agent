from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.core import User, Tenant, Subscription
from pydantic import BaseModel
from app.services.security import get_current_user

router = APIRouter()

class SyncUserRequest(BaseModel):
    email: str
    company_name: str

@router.post("/sync")
def sync_supabase_user(req: SyncUserRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Called by the frontend immediately after Supabase Auth creates an account.
    This creates the internal Tenant and User mappings.
    """
    supabase_uuid = current_user.get("sub")
    
    # 1. Check if user already exists
    existing_user = db.query(User).filter(User.email == req.email).first()
    if existing_user:
        return {"status": "ok", "message": "User already synced"}
    
    # 2. Create Tenant
    tenant = Tenant(name=req.company_name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    # 3. Create Subscription (Free Tier)
    sub = Subscription(tenant_id=tenant.id, plan="free", monthly_call_limit=50)
    db.add(sub)
    
    # 4. Create User (No need to hash password, Supabase handles auth)
    user = User(
        email=req.email,
        hashed_password=supabase_uuid, # We store their UUID instead
        tenant_id=tenant.id,
        role="admin"
    )
    db.add(user)
    db.commit()
    
    return {"status": "success", "tenant_id": tenant.id}
