import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "AI Outbound Calling System"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    BASE_URL: str = "http://localhost:8000"

    # Twilio Settings
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # AI API Keys
    SARVAM_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Database Settings
    DATABASE_URL: str = "sqlite:///./test.db"  # Fallback to sqlite if not provided
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
