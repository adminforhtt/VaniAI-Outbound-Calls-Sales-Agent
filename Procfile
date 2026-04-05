web: uvicorn app.main:app --host 0.0.0.0 --port 8000
worker: celery -A app.worker.celery_app worker --loglevel=info --concurrency=2 --pool=solo
