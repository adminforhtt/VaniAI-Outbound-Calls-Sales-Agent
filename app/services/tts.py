import httpx
import logging
import base64
import wave
import io
import audioop
import struct
import time
import os
from app.config.settings import settings

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", settings.SARVAM_API_KEY)

# synthesize_sarvam was deprecated in favor of TTSService.generate_speech.

# Map internal voice names → valid Sarvam bulbul:v3 speaker IDs
VOICE_MAP = {
    # Female voices
    "priya": "priya", "anushka": "anushka", "manisha": "manisha", "vidya": "vidya",
    "arya": "arya", "ritu": "ritu", "neha": "neha", "pooja": "pooja",
    "simran": "simran", "kavya": "kavya", "ishita": "ishita", "shreya": "shreya",
    "roopa": "roopa", "tanya": "tanya", "shruti": "shruti", "suhani": "suhani",
    "kavitha": "kavitha", "rupali": "rupali",
    # Male voices
    "anand": "anand", "shubh": "shubh", "abhilash": "abhilash", "karun": "karun",
    "hitesh": "hitesh", "aditya": "aditya", "rahul": "rahul", "rohan": "rohan",
    "amit": "amit", "dev": "dev", "ratan": "ratan", "varun": "varun",
    "manan": "manan", "sumit": "sumit", "kabir": "kabir", "aayan": "aayan",
    "ashutosh": "ashutosh", "advait": "advait", "tarun": "tarun", "sunny": "sunny",
    "mani": "mani", "gokul": "gokul", "vijay": "vijay", "mohit": "mohit",
    "rehan": "rehan", "soham": "soham",
    # Legacy aliases
    "arjun": "anand", "meera": "anushka", "pavithra": "kavitha",
    "maitreyi": "shreya", "malti": "ritu", "male": "anand", "female": "priya",
}

# Persistent connection pool
_http_client = httpx.AsyncClient()


def inject_prosody(text: str) -> str:
    """Pass raw text through. We removed artificial ellipses to prevent the TTS from over-acting."""
    return text.strip()


def normalize_audio(pcm_data: bytes, sampwidth: int) -> bytes:
    # Normalization disabled to prevent loud distortion.
    return pcm_data


    # Filter disabled to maintain raw sound quality.
    return pcm_data


    # Fades disabled to prevent bit-crushing noise.
    return pcm_data


class TTSService:
    @staticmethod
    async def generate_speech(text: str, language: str = "hi-IN", speaker: str = "priya") -> bytes:
        """
        Generates TTS audio via Sarvam API with prosody injection and audio post-processing.
        Returns raw mu-law bytes optimized for Twilio telephony.
        """
        # 1. PROSODY INJECTION: make text more natural
        processed_text = inject_prosody(text)
        
        url = "https://api.sarvam.ai/text-to-speech"
        headers = {
            "api-subscription-key": settings.SARVAM_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": [processed_text],
            "target_language_code": language,
            "speaker": VOICE_MAP.get(speaker.lower(), "anand"),
            "pace": 1.15,  # Slightly faster conversational speed to prevent 'sleepy' feeling & reduce response latency
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v3"
        }
        resolved_speaker = VOICE_MAP.get(speaker.lower(), "anand")
        logger.info(f"TTS speaker: {speaker!r} → resolved to '{resolved_speaker}'")
        try:
            t0 = time.time()
            response = await _http_client.post(url, headers=headers, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            tts_ms = int((time.time() - t0) * 1000)
            logger.info(f"⏱ TTS_LATENCY_MS={tts_ms} for: {text[:40]}...")

            # Decode base64 WAV from Sarvam
            audio_base64 = data.get("audios", [""])[0] 
            audio_bytes = base64.b64decode(audio_base64)

            # Convert WAV → PCM
            with wave.open(io.BytesIO(audio_bytes), 'rb') as wav:
                pcm_data = wav.readframes(wav.getnframes())
                sampwidth = wav.getsampwidth()
                framerate = wav.getframerate()
                channels = wav.getnchannels()

            # 🛠 BUG FIX: Correct float32 to int16 (little-endian)
            if sampwidth == 4:
                floats = struct.unpack(f"<{len(pcm_data)//4}f", pcm_data)
                ints = [max(-32768, min(32767, int(f * 32767.0))) for f in floats]
                pcm_data = struct.pack(f"<{len(ints)}h", *ints)
                sampwidth = 2

            if channels > 1:
                pcm_data = audioop.tomono(pcm_data, sampwidth, 1, 1)

            # Normalize to 16-bit (2-byte) samples explicitly
            if sampwidth != 2:
                pcm_data = audioop.lin2lin(pcm_data, sampwidth, 2)
                sampwidth = 2

            if framerate != 8000:
                pcm_data, _ = audioop.ratecv(pcm_data, sampwidth, 1, framerate, 8000, None)

            # Encode to mu-law G.711u
            ulaw_data = audioop.lin2ulaw(pcm_data, sampwidth)
            return ulaw_data
        except Exception as e:
            try:
                err_body = response.text if 'response' in dir() else 'N/A'
            except Exception:
                err_body = 'N/A'
            logger.error(f"Error in TTS generation (speaker={speaker}): {e} | Response: {err_body}")
            return b""

    @staticmethod
    async def generate_speech_streaming(text: str, language: str = "hi-IN", speaker: str = "priya"):
        from app.services.conversation_manager import split_text_for_streaming_tts
        import asyncio
        
        chunks = split_text_for_streaming_tts(text, max_chunk_chars=90)
        if not chunks:
            return

        # Fire all TTS requests concurrently
        tasks = [
            asyncio.create_task(TTSService.generate_speech(chunk, language, speaker))
            for chunk in chunks
        ]

        # Yield results IN ORDER as each future completes
        for task in tasks:
            try:
                audio_bytes = await task
                if audio_bytes:
                    yield audio_bytes
                else:
                    yield b""
            except Exception as e:
                logger.error(f"[TTS streaming] Chunk failed: {e}. Yielding silence.")
                yield b""
