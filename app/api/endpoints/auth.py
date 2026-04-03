from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.services.security import create_access_token
from app.config.database import get_db
from sqlalchemy.orm import Session
from app.models.core import User, Tenant

router = APIRouter()

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Mocking simple Auth for MVP
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or user.hashed_password != form_data.password:
        if form_data.username == "admin@test.com":
            # Auto-create test user/tenant
            tenant = Tenant(name="Test Org")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            user = User(email="admin@test.com", hashed_password="password", role="admin", tenant_id=tenant.id)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
            
    access_token = create_access_token(data={"sub": user.email, "tenant_id": user.tenant_id, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}
