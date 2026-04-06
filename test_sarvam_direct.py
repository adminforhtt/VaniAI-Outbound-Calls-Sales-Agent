import asyncio
import logging
import os
from app.services.tts import TTSService
from app.config.settings import settings

logging.basicConfig(level=logging.INFO)
# Un-hide debug logs from the module if needed
logging.getLogger("app.services.tts").setLevel(logging.INFO)

async def main():
    text = "तुमचं स्वागत आहे."
    audio = await TTSService.generate_speech(text, language="mr-IN", speaker="priya")
    print(f"Direct generate_speech audio length: {len(audio)}")

if __name__ == "__main__":
    asyncio.run(main())
