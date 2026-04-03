from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.config.database import Base, engine
from app.api.endpoints import leads, campaigns, calls, reporting, auth, analytics, billing, hermes
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

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

@app.get("/health")
async def health_check():
    """Health check for Railway/AWS/Vercel deployments."""
    return {
        "status": "ok", 
        "service": "vania-ai-backend",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION
    }
