# app/worker/celery_app.py

import os
import logging
from celery import Celery
from celery.signals import worker_ready, worker_shutdown, task_failure
from kombu import Queue

logger = logging.getLogger(__name__)

# ── Redis URL normalization ──────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# Railway Redis sometimes uses rediss:// (TLS) — keep as-is
# Ensure it's not the raw postgres URL accidentally
if REDIS_URL.startswith("postgres"):
    raise ValueError("REDIS_URL is set to a PostgreSQL URL. Check Railway env vars.")

# ── Celery app creation ──────────────────────────────────────────────────────
celery_app = Celery(
    "vani_ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"]  # auto-discover tasks
)

# ── Core configuration ───────────────────────────────────────────────────────
celery_app.conf.update(

    # Task serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,

    # ── RELIABILITY: Task acknowledgment ────────────────────────────────────
    # acks_late=True: Task is removed from queue ONLY after successful completion.
    # If worker dies mid-task, task re-queues automatically.
    task_acks_late=True,
    task_reject_on_worker_lost=True,  # re-queue if worker process dies
    worker_prefetch_multiplier=1,     # fetch one task at a time (fair dispatch)

    # ── RELIABILITY: Redis broker transport ─────────────────────────────────
    broker_transport_options={
        # Retry connecting to Redis up to 15 times before giving up
        "max_retries": 15,
        # Start with no delay, then increase up to 5s between retries
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 5.0,
        "retry_on_timeout": True,
        # Visibility timeout: task becomes visible again if not acked in 1hr
        "visibility_timeout": 3600,
    },

    # ── RELIABILITY: Connection retry ───────────────────────────────────────
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=20,

    # ── RELIABILITY: Heartbeat ───────────────────────────────────────────────
    # Worker sends heartbeat every 10s. If missed, broker marks worker as dead.
    broker_heartbeat=10,
    broker_heartbeat_checkrate=2,

    # ── RELIABILITY: Cancel tasks on connection loss ─────────────────────────
    worker_cancel_long_running_tasks_on_connection_loss=True,

    # ── PERFORMANCE: Result expiry ───────────────────────────────────────────
    result_expires=3600,  # Keep task results for 1 hour

    # ── QUEUES: Explicit queue definitions ──────────────────────────────────
    task_queues=(
        Queue("default",  routing_key="default"),
        Queue("enrichment", routing_key="enrichment"),
        Queue("reporting", routing_key="reporting"),
    ),
    task_default_queue="default",
    task_default_routing_key="default",
)

# ── Signal handlers for observability ───────────────────────────────────────

@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    logger.info("✅ [Celery] Worker is ready and connected to Redis.")

@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    logger.info("🔴 [Celery] Worker shutting down.")

@task_failure.connect
def on_task_failure(task_id, exception, traceback, einfo, **kwargs):
    logger.error(
        f"[Celery] Task {task_id} FAILED: {exception}",
        exc_info=True
    )
    # TODO: Send to your alerting system (Slack/PagerDuty) here
