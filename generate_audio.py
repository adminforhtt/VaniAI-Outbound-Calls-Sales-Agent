import asyncio
import os
from app.services.tts import TTSService

async def gen():
    print("Generating greeting.mulaw...")
    greeting = await TTSService.generate_speech("नमस्ते, क्या आप मुझसे बात कर सकते हैं?", language="hi-IN", speaker="priya")
    if greeting:
        with open("greeting.mulaw", "wb") as f:
            f.write(greeting)
        print("greeting.mulaw saved!")
    
    print("Generating fallback.mulaw...")
    fallback = await TTSService.generate_speech("एक क्षण...", language="hi-IN", speaker="priya")
    if fallback:
        with open("fallback.mulaw", "wb") as f:
            f.write(fallback)
        print("fallback.mulaw saved!")

if __name__ == "__main__":
    asyncio.run(gen())
