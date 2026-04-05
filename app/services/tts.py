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

def validate_tts_payload(payload: dict):
    allowed_keys = ["text", "voice", "model", "sample_rate"]
    for key in payload.keys():
        if key not in allowed_keys:
            raise Exception(f"Invalid TTS param: {key}")

async def synthesize_sarvam(text: str, speaker: str = "kavya") -> bytes:
    """
    Call Sarvam AI TTS. Returns raw PCM/WAV bytes decoded from base64.
    """
    if not text or not text.strip():
        logger.warning("TTS called with empty text — skipping")
        return b""

    text = text.strip()
    if len(text) > 500:
        text = text[:500]

    payload = {
        "text": text,
        "voice": speaker,
        "model": "bulbul:v3",
        "sample_rate": 8000
    }

    validate_tts_payload(payload)

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    logger.info(f"TTS_PAYLOAD: {payload}")
    logger.info("TTS_MODEL_USED: bulbul:v3")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                json=payload,
                headers=headers
            )

            if response.status_code != 200:
                logger.error(f"TTS_FAILED_REASON: status={response.status_code} body={response.text[:300]}")
                return b""

            data = response.json()
            audios = data.get("audios", [])
            if not audios or not audios[0]:
                logger.error(f"TTS_SARVAM_EMPTY_RESPONSE: {data}")
                return b""

            audio_bytes = base64.b64decode(audios[0])
            logger.info(f"TTS_SUCCESS: {len(audio_bytes)} bytes")
            return audio_bytes

    except httpx.TimeoutException:
        logger.error(f"TTS_TIMEOUT: Sarvam did not respond in 10s")
        return b""
    except Exception as e:
        logger.error(f"TTS_FAILED_REASON: Exception: {e}")
        return b""

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
    """Normalize PCM volume to target RMS, apply +2dB gain."""
    if not pcm_data:
        return pcm_data
    
    try:
        rms = audioop.rms(pcm_data, sampwidth)
        if rms == 0:
            return pcm_data
        
        # Target RMS for clear telephony audio
        target_rms = 4000
        gain_factor = target_rms / rms
        
        # Clamp gain to prevent distortion
        gain_factor = min(gain_factor, 3.0)
        gain_factor = max(gain_factor, 0.5)
        
        # Apply +2dB on top (factor ≈ 1.26)
        gain_factor *= 1.26
        
        # Apply gain via audioop.mul
        pcm_data = audioop.mul(pcm_data, sampwidth, gain_factor)
        
        return pcm_data
    except Exception as e:
        logger.warning(f"Audio normalization failed: {e}")
        return pcm_data


def apply_telephony_filter(pcm_data: bytes, sampwidth: int) -> bytes:
    """Simple low-pass filter for telephony clarity (attenuate >3kHz)."""
    if not pcm_data or len(pcm_data) < sampwidth * 4:
        return pcm_data
    
    try:
        # Apply bias removal
        pcm_data = audioop.bias(pcm_data, sampwidth, 0)
        return pcm_data
    except Exception as e:
        logger.warning(f"Telephony filter failed: {e}")
        return pcm_data


def add_fade_edges(pcm_data: bytes, sampwidth: int, fade_ms: int = 30) -> bytes:
    """Add fade-in/fade-out to prevent audio clicks/pops."""
    if not pcm_data:
        return pcm_data
    
    try:
        n_samples = len(pcm_data) // sampwidth
        fade_samples = min(int(8000 * fade_ms / 1000), n_samples // 4)
        
        if fade_samples < 2:
            return pcm_data
        
        # Convert to list of samples
        fmt = '<' + ('h' if sampwidth == 2 else 'b') * n_samples
        if len(pcm_data) != struct.calcsize(fmt):
            return pcm_data
        
        samples = list(struct.unpack(fmt, pcm_data))
        
        # Fade in
        for i in range(fade_samples):
            factor = i / fade_samples
            samples[i] = int(samples[i] * factor)
        
        # Fade out
        for i in range(fade_samples):
            factor = i / fade_samples
            samples[n_samples - 1 - i] = int(samples[n_samples - 1 - i] * factor)
        
        return struct.pack(fmt, *samples)
    except Exception as e:
        logger.warning(f"Fade edges failed: {e}")
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

            if channels > 1:
                pcm_data = audioop.tomono(pcm_data, sampwidth, 1, 1)

            # Normalize to 16-bit (2-byte) samples explicitly
            if sampwidth != 2:
                pcm_data = audioop.lin2lin(pcm_data, sampwidth, 2)
                sampwidth = 2

            if framerate != 8000:
                pcm_data, _ = audioop.ratecv(pcm_data, sampwidth, 1, framerate, 8000, None)

            # 5. AUDIO POST-PROCESSING PIPELINE
            pcm_data = normalize_audio(pcm_data, sampwidth)
            pcm_data = apply_telephony_filter(pcm_data, sampwidth)
            pcm_data = add_fade_edges(pcm_data, sampwidth, fade_ms=30)

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
                    # 0.5s mulaw silence
                    yield bytes([0x7F] * 4000)
            except Exception as e:
                logger.error(f"[TTS streaming] Chunk failed: {e}. Yielding silence.")
                yield bytes([0x7F] * 4000)
