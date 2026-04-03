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
    
    # SaaS Intelligence (Hermes + Browserbase)
    BROWSERBASE_API_KEY: str = ""
    BROWSERBASE_PROJECT_ID: str = ""
    HERMES_MODEL: str = "qwen/qwen-2.5-72b-instruct:free"

    # Billing (Razorpay)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Database Settings
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Supabase Specific
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
