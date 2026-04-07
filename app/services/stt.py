import logging
import asyncio
import audioop
import wave
import io
import time
import httpx
from typing import AsyncGenerator, Dict, Any
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Persistent connection pool for STT APIs
_stt_client = httpx.AsyncClient(timeout=10.0)

class GroqWhisperSTT:
    """
    Groq Whisper STT with dual-mode VAD:
      - Emits PARTIAL transcripts for early LLM triggering (after ~400ms of speech)
      - Emits FINAL transcripts after silence detection (1000ms)
    This enables the LLM to start generating before the user fully stops speaking.
    """

    # VAD tuning constants
    ENERGY_THRESHOLD = 300          # RMS energy above which we consider "speech"
    SILENCE_DURATION_MS = 850       # 850ms silence -> trigger final transcription (FASTER)
    PARTIAL_TRIGGER_MS = 200        # After 200ms of speech -> emit partial (FASTER BARGE-IN)
    MIN_SPEECH_DURATION_MS = 200    # ignore utterances shorter than this
    SAMPLE_RATE = 16000             # Groq native
    SAMPLE_WIDTH = 2                # 16-bit PCM

    def __init__(self, language: str = "hi-IN"):
        self.language = language
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False
        self._rate_state = None

        # VAD state
        self._pcm_buffer = bytearray()
        self._is_speaking = False
        self._silence_chunks = 0
        self._speech_chunks = 0
        self._partial_emitted = False

        # Each Twilio chunk is ~20ms of 8kHz mu-law = 160 bytes
        self._chunk_duration_ms = 20
        self._silence_chunks_needed = self.SILENCE_DURATION_MS // self._chunk_duration_ms
        self._min_speech_chunks = self.MIN_SPEECH_DURATION_MS // self._chunk_duration_ms
        self._partial_trigger_chunks = self.PARTIAL_TRIGGER_MS // self._chunk_duration_ms

    async def push_chunk(self, audio_chunk: bytes):
        """Push raw mu-law audio from Twilio into processing queue."""
        await self.audio_queue.put(audio_chunk)

    async def process_stream(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Main loop: consumes audio chunks, runs VAD, and yields transcription results.
        Yields both partial (for early LLM) and final transcripts.
        """
        self._is_running = True
        logger.info("STT started (Groq Whisper, silence=%dms, partial=%dms). Listening...",
                     self.SILENCE_DURATION_MS, self.PARTIAL_TRIGGER_MS)

        while self._is_running:
            try:
                try:
                    mu_law_chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                # Convert mu-law to 16-bit PCM (8kHz)
                pcm_chunk = audioop.ulaw2lin(mu_law_chunk, self.SAMPLE_WIDTH)
                
                # Upsample 8kHz → 16kHz for Whisper
                pcm_16k, self._rate_state = audioop.ratecv(pcm_chunk, self.SAMPLE_WIDTH, 1, 8000, 16000, self._rate_state)
                
                rms = audioop.rms(pcm_chunk, self.SAMPLE_WIDTH)

                if rms > self.ENERGY_THRESHOLD:
                    if not self._is_speaking:
                        self._is_speaking = True
                        self._pcm_buffer = bytearray()
                        self._speech_chunks = 0
                        self._partial_emitted = False
                        logger.info(f"VAD: Speech started (RMS={rms})")

                    self._pcm_buffer.extend(pcm_16k)
                    self._speech_chunks += 1
                    self._silence_chunks = 0

                    # ── PARTIAL TRANSCRIPT: emit early for LLM pre-warming ──
                    if (not self._partial_emitted
                            and self._speech_chunks >= self._partial_trigger_chunks):
                        self._partial_emitted = True
                        t0 = time.time()
                        partial_text = await self._transcribe_buffer(bytes(self._pcm_buffer))
                        stt_ms = int((time.time() - t0) * 1000)
                        if partial_text and len(partial_text.strip()) > 3:
                            logger.info(f"STT PARTIAL ({stt_ms}ms): {partial_text}")
                            yield {"is_final": False, "text": partial_text.strip(), "stt_latency_ms": stt_ms}

                elif self._is_speaking:
                    self._pcm_buffer.extend(pcm_16k)
                    self._silence_chunks += 1

                    # ── FINAL TRANSCRIPT: after 1 sec of silence ──
                    if self._silence_chunks >= self._silence_chunks_needed:
                        self._is_speaking = False

                        if self._speech_chunks >= self._min_speech_chunks:
                            speech_ms = self._speech_chunks * self._chunk_duration_ms
                            logger.info(f"VAD: Speech ended. {self._speech_chunks} chunks ({speech_ms}ms). Transcribing...")

                            t0 = time.time()
                            text = await self._transcribe_buffer(bytes(self._pcm_buffer))
                            stt_ms = int((time.time() - t0) * 1000)

                            if text and text.strip():
                                logger.info(f"STT FINAL ({stt_ms}ms): {text}")
                                logger.info(f"⏱ STT_LATENCY_MS={stt_ms}")
                                yield {"is_final": True, "text": text.strip(), "stt_latency_ms": stt_ms, "speech_ms": speech_ms }
                            else:
                                logger.info(f"STT returned empty ({stt_ms}ms)")
                        else:
                            logger.info("VAD: Utterance too short, discarding.")

                        self._pcm_buffer = bytearray()
                        self._silence_chunks = 0
                        self._speech_chunks = 0
                        self._partial_emitted = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in STT process_stream: {e}")
                await asyncio.sleep(0.1)

    def _build_wav(self, pcm_data: bytes) -> bytes:
        """Convert raw PCM to WAV format in memory."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(pcm_data)
        return wav_buffer.getvalue()

    async def _transcribe_buffer(self, pcm_data: bytes) -> str:
        """Transcription via Groq Whisper."""
        wav_bytes = self._build_wav(pcm_data)
        try:
            iso_lang = self.language.split('-')[0] if '-' in self.language else self.language
            data = {
                "model": "whisper-large-v3",
                "response_format": "text",
                "language": iso_lang  # Explicitly pass ISO language; NEVER auto-detect for Indic Scripts
            }
                
            response = await _stt_client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data=data,
            )
            response.raise_for_status()
            text = response.text
            return text.strip() if text else ""
        except Exception as e:
            logger.warning(f"Whisper STT failed: {e}")
            return ""

    async def stop(self):
        self._is_running = False


# Backward-compatible alias
SarvamStreamingSTT = GroqWhisperSTT
