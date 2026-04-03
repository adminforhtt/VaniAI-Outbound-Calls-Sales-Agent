import asyncio
import time
import logging
import random
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)

class LatencyController:
    """
    Latency Masking & Turn Management Middleware.
    Sits directly between ASR -> LLM -> TTS to enforce strict real-time masking limits.
    """
    def __init__(
        self,
        send_audio_func: Callable[[bytes], Awaitable[None]],
        cancel_tts_func: Callable[[], None],
        get_cached_audio_func: Callable[[str], bytes]
    ):
        """
        :param send_audio_func: Async function to stream raw bytes to Twilio payload.
        :param cancel_tts_func: Sync/Async function to halt ongoing TTS buffering.
        :param get_cached_audio_func: Sync function returning pre-cached mu-law bytes for fillers.
        """
        self.send_audio = send_audio_func
        self.cancel_tts = cancel_tts_func
        self.get_cached_audio = get_cached_audio_func
        
        self._turn_start_time = 0.0
        self._filler_played = False
        self._streaming_started = False
        self._latency_task: Optional[asyncio.Task] = None
        
        # Memory to avoid filler recurrence (Keep track of last 3 phrases)
        self._recent_fillers = []

    async def on_user_speech_end(self, intent: str = "neutral"):
        """Called immediately when ASR detects EOF speech."""
        self._turn_start_time = time.time()
        self._filler_played = False
        self._streaming_started = False
        
        # Stop any active masking loop
        if self._latency_task and not self._latency_task.done():
            self._latency_task.cancel()
            
        # 1. Start dynamic latency tracker
        self._latency_task = asyncio.create_task(self._latency_loop(intent))
        
        # 1. INSTANT ACKNOWLEDGEMENT (Triggered within 150-300ms)
        asyncio.create_task(self._play_instant_ack())

    async def _play_instant_ack(self):
        """Fires an instant short backchannel if LLM isn't instantly ready."""
        await asyncio.sleep(0.020) # 20ms delay threshold for instant overlap
        if not self._filler_played and not self._streaming_started:
            audio = self.get_cached_audio("acknowledgement")
            if audio:
                asyncio.create_task(self.send_audio(audio))
            self._filler_played = True

    async def _latency_loop(self, intent: str):
        """Monitors time passed since user ended speech to inject smart masking."""
        try:
            # 2. LATENCY TIMER: Wait for 800ms threshold
            await asyncio.sleep(0.800) 
            if not self._streaming_started:
                # LLM still pulling tokens -> trigger thinking filler
                filler_key = self._select_smart_filler('thinking', intent)
                audio = self.get_cached_audio(filler_key)
                if audio:
                    await self.send_audio(audio)

            # LATENCY TIMER: Wait for 1800ms threshold
            await asyncio.sleep(1.000) 
            if not self._streaming_started:
                # Extremely delayed LLM fallback strategy
                filler_key = self._select_smart_filler('fallback', intent)
                audio = self.get_cached_audio(filler_key)
                if audio:
                    await self.send_audio(audio)
        except asyncio.CancelledError:
            pass

    def _select_smart_filler(self, category: str, intent: str) -> str:
        """3. SMART FILLER ENGINE: Returns the requested top-level category mapping for simplified cache retrieval."""
        return category

    async def on_llm_first_token(self):
        """4. STREAMING RESPONSE START: Called the exact ms the LLM yields its first token."""
        self._streaming_started = True
        if self._latency_task and not self._latency_task.done():
            self._latency_task.cancel()

    async def on_user_barge_in(self):
        """5. INTERRUPT HANDLING (CRITICAL): User spoke cleanly > cutoff threshold."""
        if self._latency_task and not self._latency_task.done():
            self._latency_task.cancel()
            
        # Send immediately to TTS layer to cancel buffering/playback
        self.cancel_tts()
