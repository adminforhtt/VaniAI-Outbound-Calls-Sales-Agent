import asyncio
from app.config.settings import settings
from supabase import create_client

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

async def test():
    # simulate signup
    try:
        res = supabase.auth.sign_up({"email": "testing_auth@test.com", "password": "password123"})
        token = res.session.access_token
        print("Got token:", token[:10] + "...")
        # Now verify
        admin = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        user_res = admin.auth.get_user(token)
        print("Verified!", user_res.user.email)
    except Exception as e:
        print("Error:", e)
        
asyncio.run(test())
