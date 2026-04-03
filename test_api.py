import os
import httpx
from dotenv import load_dotenv
import asyncio
import websockets

load_dotenv()
key = os.getenv('SARVAM_API_KEY')
print('Key length:', len(key) if key else 'None')

# Test TTS API (which succeeded in logs)
r1 = httpx.post('https://api.sarvam.ai/text-to-speech', headers={'api-subscription-key': key}, json={
    "inputs": ["Hello"],
    "target_language_code": "hi-IN",
    "speaker": "priya",
    "pace": 1.0,
    "speech_sample_rate": 8000,
    "enable_preprocessing": True,
    "model": "bulbul:v3"
})
print("TTS API status:", r1.status_code)

async def test_ws():
    headers = {"API-Subscription-Key": key}
    url = "wss://api.sarvam.ai/speech-to-text/translate/ws?model=saaras:v3&language_code=hi-IN&mode=translate&audio_format=pcm_s16le"
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print("WS Connected!")
    except Exception as e:
        print("WS error (test 1):", e)
        # Try alternate URL
        url2 = "wss://api.sarvam.ai/speech-to-text-translate/ws?model=saaras:v3&language_code=hi-IN&mode=transcribe&audio_format=pcm_s16le"
        try:
            async with websockets.connect(url2, additional_headers={"api-subscription-key": key}) as ws:
                print("WS Connected to alternate!")
        except Exception as e2:
            print("WS error (test 2):", e2)

asyncio.run(test_ws())
