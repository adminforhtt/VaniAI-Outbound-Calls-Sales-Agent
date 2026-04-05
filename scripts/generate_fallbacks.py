import httpx, base64, os, json

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
FALLBACKS = {
    "hi-IN": ("hi", "एक सेकंड, मैं सोच रही हूँ।"),
    "mr-IN": ("mr", "थांबा, मी विचार करतेय।"),
    "ta-IN": ("ta", "ஒரு நிமிடம், நான் யோசிக்கிறேன்."),
    "te-IN": ("te", "ఒక్క నిమిషం, నేను ఆలోచిస్తున్నాను."),
    "bn-IN": ("bn", "এক মুহূর্ত, আমি ভাবছি।"),
    "en-IN": ("en", "One moment, let me think."),
}

os.makedirs("assets/fallbacks", exist_ok=True)

for lang_code, (short_code, text) in FALLBACKS.items():
    if not SARVAM_API_KEY:
        print("SARVAM_API_KEY not found, skipping generation")
        break
        
    try:
        resp = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"API-Subscription-Key": SARVAM_API_KEY},
            json={"inputs": [text], "target_language_code": lang_code,
                  "speaker": "meera", "model": "bulbul:v1",
                  "enable_preprocessing": True}
        )
        resp.raise_for_status()
        audio_b64 = resp.json()["audios"][0]
        audio_bytes = base64.b64decode(audio_b64)
        with open(f"assets/fallbacks/fallback_{short_code}.wav", "wb") as f:
            f.write(audio_bytes)
        print(f"✅ Generated fallback_{short_code}.wav")
    except Exception as e:
        print(f"Error generating {lang_code}: {e}")
