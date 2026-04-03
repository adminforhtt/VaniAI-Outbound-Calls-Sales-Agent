FROM python:3.10-slim

WORKDIR /app

# Install OS dependencies required via requirements (e.g. psycopg2)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Hermes internal dependencies to satisfy run_agent.py
RUN pip install --no-cache-dir -r libs/hermes/requirements.txt

# Railway injects PORT at runtime — use shell form so $PORT is evaluated
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
