import asyncio
import logging
from app.services.tts import TTSService

logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing generate_speech...")
    try:
        audio = await TTSService.generate_speech("Hello, this is a test from Vani AI.", language="hi-IN", speaker="priya")
        print(f"Generated {len(audio)} bytes of ulaw.")
        if len(audio) == 0:
            print("Audio is empty! Check logs.")
        with open("test_out.ulaw", "wb") as f:
            f.write(audio)
        print("Saved to test_out.ulaw")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
