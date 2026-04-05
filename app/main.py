from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.config.database import Base, engine
from app.api.endpoints import leads, campaigns, calls, reporting, auth, analytics, billing, hermes
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permissive for initial cloud sync, can restrict to specific app.vaniai.in later
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(calls.router, prefix="/api/calls", tags=["Calls"])
app.include_router(reporting.router, prefix="/api/reporting", tags=["Reporting"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(hermes.router, prefix="/api/hermes", tags=["Hermes"])

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting up Vani AI for Production (Env: {settings.ENVIRONMENT})")
    logger.info(f"BASE_URL: {settings.BASE_URL} (Important for Twilio webhooks)")

@app.on_event("startup")
async def run_db_migrations():
    """
    Run pending Alembic migrations on every startup.
    This is safe — Alembic tracks which migrations have run via alembic_version table.
    No-op if already at head. Never runs a migration twice.
    """
    try:
        logger.info("Running Alembic migrations...")
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("✅ DB migrations complete — at head.")
    except Exception as e:
        import traceback
        logger.critical(f"❌ DB migration failed on startup: {str(e)}")
        logger.critical(traceback.format_exc())
        raise  # crash startup if migrations fail — better than silent data corruption

from app.api.endpoints.health import router as health_router
app.include_router(health_router)
