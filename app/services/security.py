from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config.settings import settings
from supabase import create_client, Client
from sqlalchemy.orm import Session
from app.config.database import get_db
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# Initialize Supabase Admin Client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Validates the Supabase JWT and fetches the corresponding Tenant ID from our database.
    """
    if settings.BYPASS_AUTH:
        logger.warning("⚠️ SECURITY_WARNING: AUTH BYPASS IS ENABLED! Returning dummy demo user.")
        from app.models.core import User
        # Try to find the first admin user in the DB to represent the demo
        admin = db.query(User).filter(User.role == "admin").first()
        return {
            "sub": "demo-uuid",
            "email": admin.email if admin else "demo@vani.ai",
            "tenant_id": admin.tenant_id if admin else 1,
            "role": "admin"
        }

    try:
        # Validate JWT via Supabase API
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        email = user_response.user.email
        uuid = user_response.user.id
        
        # We allow /sync to pass without a tenant_id so it can create one
        from app.models.core import User
        db_user = db.query(User).filter(User.email == email).first()
        
        tenant_id = db_user.tenant_id if db_user else None
            
        return {
            "sub": uuid, 
            "email": email,
            "tenant_id": tenant_id, 
            "role": db_user.role if db_user else "user"
        }
    except Exception as e:
        logger.error(f"AUTH_FAILURE: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {e}. Try logging out and in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_auth_tenant(current_user: dict = Depends(get_current_user)) -> int:
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized or no tenant mapped. Try logging out and in again.")
    return tenant_id
