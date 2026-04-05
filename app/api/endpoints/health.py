# app/api/endpoints/health.py

from fastapi import APIRouter
from app.worker.celery_app import celery_app
import asyncio

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Health check for Railway.
    Checks: FastAPI running, Redis reachable, Celery worker alive.
    """
    # Check Redis connectivity via Celery
    try:
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active()
        celery_status = "healthy" if active is not None else "no_workers"
    except Exception as e:
        celery_status = f"unreachable: {str(e)[:50]}"

    return {
        "status": "ok",
        "celery": celery_status,
    }
