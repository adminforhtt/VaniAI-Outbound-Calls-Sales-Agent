import asyncio
import httpx

async def test():
    # Attempting to fetch directly using standard payload that frontend sends
    payload = {
        "phone_number": "+919307201890",
        "script": "Hello, this is a test call from Vani AI.",
        "llm_provider": "groq",
        "voice": "priya",
        "language": "hi-IN"
    }

    try:
        from app.config.database import SessionLocal
        from app.models.core import Tenant, User
        from app.services.security import create_access_token
        
        db = SessionLocal()
        user = db.query(User).first()
        if not user:
            print("No users found to construct JWT. Make sure logic is initiated on frontend.")
            return
            
        token = create_access_token({"sub": user.email, "tenant_id": user.tenant_id})
        db.close()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        print("Sending request...")
        async with httpx.AsyncClient() as client:
            res = await client.post("http://127.0.0.1:8000/api/calls/test-call", json=payload, headers=headers)
            print(res.status_code, res.text)
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test())
