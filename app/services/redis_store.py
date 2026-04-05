import redis
import json
from typing import List, Dict, Any
from app.config.settings import settings

class RedisStore:
    def __init__(self):
        import redis.asyncio as redis_async
        # Hardened for Production: Only apply SSL settings if using rediss://
        kwargs = {"decode_responses": True}
        if settings.REDIS_URL.startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = None
            
        self.redis = redis_async.from_url(settings.REDIS_URL, **kwargs)

    async def get_session(self, call_sid: str) -> Dict[str, Any]:
        data = await self.redis.get(f"session:{call_sid}")
        if data:
            return json.loads(data)
        return {"history": [], "state": "INIT", "conversation_stage": "GREETING", "user_intent": "neutral"}

    async def save_session(self, call_sid: str, session_data: Dict[str, Any], ttl_seconds: int = 3600*24):
        await self.redis.setex(f"session:{call_sid}", ttl_seconds, json.dumps(session_data))

    async def add_message(self, call_sid: str, role: str, content: str):
        session = await self.get_session(call_sid)
        session["history"].append({"role": role, "content": content})
        # Keep only the last 5 messages for minimal prompt size
        if len(session["history"]) > 5:
            session["history"] = session["history"][-5:]
        await self.save_session(call_sid, session)

    async def get_history(self, call_sid: str) -> List[Dict[str, str]]:
        session = await self.get_session(call_sid)
        return session.get("history", [])

    async def get_state(self, call_sid: str) -> str:
        session = await self.get_session(call_sid)
        return session.get("state", "INIT")
        
    async def set_state(self, call_sid: str, state: str):
        session = await self.get_session(call_sid)
        session["state"] = state
        await self.save_session(call_sid, session)

redis_client = RedisStore()
