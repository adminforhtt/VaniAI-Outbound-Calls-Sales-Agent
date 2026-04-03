#!/bin/bash

# Base URL
BASE_URL="http://localhost:8000"

echo "1. Creating Campaign"
curl -X POST "$BASE_URL/api/campaigns" \
-H "Content-Type: application/json" \
-d '{
  "name": "Test Campaign",
  "script_template": "You are a test agent...",
  "language": "en-IN",
  "goal": "Test goal"
}'

echo -e "\n\n2. Creating Lead"
curl -X POST "$BASE_URL/api/leads" \
-H "Content-Type: application/json" \
-d '{
  "name": "Test User",
  "phone": "+1234567890",
  "campaign_id": 1,
  "language": "en-US"
}'

echo -e "\n\n3. Trigerring Outbound Call"
curl -X POST "$BASE_URL/api/calls/initiate?lead_id=1" \
-H "Content-Type: application/json"
