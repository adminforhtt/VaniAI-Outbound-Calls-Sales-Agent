#!/bin/bash
set -e

echo "Setting up Twilio Agent SaaS Environment..."

# 1. Setup Backend
echo "-> Setting up backend (Python virtualenv)..."
python3 -m venv venv

# Platform agnostic source
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

pip install -r requirements.txt
echo "Dependencies installed."

echo "-> Initializing SQLite database..."
python -c "from app.config.database import Base, engine; Base.metadata.create_all(bind=engine)"
echo "Database ready."

# 2. Setup Frontend
echo "-> Setting up frontend..."
cd frontend
npm install
cd ..

echo "------------------------------------------------------"
echo "Setup Complete! The environment is ready."
echo "------------------------------------------------------"
echo "To run the API Backend (Port 8000):"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload --port 8000"
echo ""
echo "To run the React Dashboard:"
echo "  cd frontend"
echo "  npm run dev"
echo "------------------------------------------------------"
