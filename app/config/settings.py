import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "AI Outbound Calling System"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "vani-ai-super-secret-auth-key-2026"  # Should be env var in production

    # Twilio Settings
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # AI API Keys
    SARVAM_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    
    # Billing (Razorpay)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Database Settings
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Supabase Specific (Hardcoded fallbacks for Demo Stability)
    SUPABASE_URL: str = "https://nqgjtartntbyhipafjjf.supabase.co"
    SUPABASE_ANON_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5xZ2p0YXJ0bnRieWhpcGFmampmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMDM2MDEsImV4cCI6MjA5MDc3OTYwMX0.DVsmcoBnYKnDs5513kqYMzk-zsiewz6ri06WzDigsaA"
    SUPABASE_SERVICE_ROLE_KEY: str = "" # User must still provide this in Railway!
    
    BYPASS_AUTH: str = "False"  # Set to "True" in Railway env vars to skip JWT checks

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
