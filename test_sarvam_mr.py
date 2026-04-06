import asyncio
import logging
import httpx
import os
from app.config.settings import settings

logging.basicConfig(level=logging.INFO)

async def main():
    url = "https://api.sarvam.ai/text-to-speech"
    key = os.getenv("SARVAM_API_KEY", settings.SARVAM_API_KEY)
    headers = {
        "api-subscription-key": key,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": ["तुमचं स्वागत आहे, मी कर्ज विभागातून बोलत आहे"],
        "target_language_code": "mr-IN",
        "speaker": "priya",
        "pace": 1.0,
        "speech_sample_rate": 8000,
        "model": "bulbul:v3"
    }
    
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("SUCCESS! Marathi is working.")
        else:
            print(f"FAILED! Error: {r.text}")

if __name__ == "__main__":
    asyncio.run(main())
