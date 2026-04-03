import asyncio
import os
import sys

# Ensure app modules can be imported
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from app.services.tts import TTSService

FILLERS = {
    "hi-IN": {
        "acknowledgement": "जी",
        "thinking": "एक सेकंड",
        "fallback": "हम्म"
    },
    "mr-IN": {
        "acknowledgement": "हो जी",
        "thinking": "एक सेकंद",
        "fallback": "हम्म"
    },
    "en-IN": {
        "acknowledgement": "Got it",
        "thinking": "One second",
        "fallback": "Hmm"
    }
}

# The two standard voices used by the manager
VOICES = ["priya", "arjun"]

async def main():
    print("Starting audio caching...")
    cache_dir = os.path.join(base_dir, "cache", "audio")
    os.makedirs(cache_dir, exist_ok=True)
    
    for lang, categories in FILLERS.items():
        for category, text in categories.items():
            for voice in VOICES:
                filename = f"{lang}_{voice}_{category}.mulaw"
                filepath = os.path.join(cache_dir, filename)
                
                if not os.path.exists(filepath):
                    print(f"Generating: {filename} ('{text}')")
                    try:
                        audio_bytes = await TTSService.generate_speech(text, language=lang, speaker=voice)
                        if audio_bytes:
                            with open(filepath, "wb") as f:
                                f.write(audio_bytes)
                            print(f"✅ Saved {filename}")
                        else:
                            print(f"❌ Failed to generate audio for {filename}")
                    except Exception as e:
                        print(f"Error on {filename}: {e}")
                else:
                    print(f"⏭  Skipped {filename} (already exists)")
                    
    print("\nCaching complete! The LatencyController now has zero-latency filler access.")

if __name__ == "__main__":
    asyncio.run(main())
