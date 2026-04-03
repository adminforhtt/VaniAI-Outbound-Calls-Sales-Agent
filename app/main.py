from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.config.database import Base, engine
from app.api.endpoints import leads, campaigns, calls, reporting, auth, analytics
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(calls.router, prefix="/api/calls", tags=["Calls"])
app.include_router(reporting.router, prefix="/api/reporting", tags=["Reporting"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up AI Outbound Calling System...")

@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
