import asyncio
import json
import logging
import base64
import time
import random
from fastapi import WebSocket, WebSocketDisconnect
from app.services.stt import SarvamStreamingSTT
from app.services.llm import LLMService
from app.services.tts import TTSService
from app.services.redis_store import redis_client
from app.config.database import SessionLocal
from app.models.core import CallLog, Lead, Campaign
from app.services.policy_engine import PolicyEngine
from app.services.latency_controller import LatencyController
from app.services.prompt_builder import (
    build_call_prompt, 
    LANGUAGE_NAMES, 
    FEMALE_VOICES, 
    detect_language_mismatch, 
    fallback_response
)

logger = logging.getLogger(__name__)

# ── FILLER WORDS: skip LLM/TTS entirely ──
FILLER_WORDS = {
    "जी", "हाँ", "hmm"
}

# Map BCP-47 codes to human-readable language names for the LLM
LANGUAGE_NAMES = {
    "hi-IN": "Hindi",
    "en-IN": "English",
    "bn-IN": "Bengali",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "pa-IN": "Punjabi",
    "or-IN": "Odia",
}

import re

# ── PROBLEM 2: CLEAN LLM FOR TTS ──
def clean_llm_for_tts(text: str, max_chars: int = 250) -> str:
    """
    1. Strip leading greetings
    2. Truncate at a sentence boundary (not mid-word)
    3. Ensure it ends cleanly
    """
    # Step 1: strip leading greeting patterns
    text = re.sub(
        r'^(नमस्कार[!,]?\s*|हॅलो[!,]?\s*|नमस्ते[!,]?\s*|'
        r'मी उत्तर देण्याचा प्रयत्न करेन[.|,]?\s*|'
        r'नमस्कार! मी तुमच्या प्रश्नाचा उत्तर देण्याचा प्रयत्न करेन[.|,]?\s*)',
        '', text, flags=re.UNICODE
    ).strip()

    # Step 2: if under limit, return as-is
    if len(text) <= max_chars:
        return text

    # Step 3: truncate at last sentence boundary before max_chars
    truncated = text[:max_chars]
    # Find last sentence-ending punctuation (।  .  !  ?)
    last_end = max(
        truncated.rfind('।'),
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?'),
    )
    if last_end > 50:  # only truncate there if it's not too short
        return text[:last_end + 1].strip()

    # Step 4: fallback — truncate at last space
    last_space = truncated.rfind(' ')
    if last_space > 50:
        return text[:last_space].strip() + '।'

    return truncated.strip()

# ── PROBLEM 3: STATE MACHINE LOGIC ──
GOODBYE_SIGNALS = {
    'धन्यवाद', 'bye', 'बाय', 'ठीक आहे', 'okay', 'ok', 
    'नको', 'बास', 'थांब', 'पुरे', 'goodbye', 'सगला माहिती',
    'धन्यवाद मला', 'खूप धन्यवाद'
}

POSITIVE_SIGNALS = {
    'हो', 'हाँ', 'हां', 'yes', 'चांगलं', 'ठीक', 'बरं', 
    'सांगा', 'सांगुशक्ता', 'माहिती द्या', 'पुढे सांगा'
}

DOUBT_SIGNALS = {
    'नाही', 'no', 'माहित नाही', 'कळत नाही', 'कसं', 
    'का', 'खर्च', 'किती', 'महाग', 'वेळ'
}

def compute_next_state(
    current_state: str,
    user_text: str,
    intent_memory: list,
    turn_count: int
) -> str:
    text_lower = user_text.lower()
    memory_lower = ' '.join(intent_memory).lower()

    # Check goodbye/done signals first — highest priority
    for signal in GOODBYE_SIGNALS:
        if signal in text_lower or signal in memory_lower:
            if current_state in ('PITCH', 'CLOSE', 'OBJECTION'):
                return 'DONE'

    if current_state == 'GREETING':
        return 'DISCOVERY'

    elif current_state == 'DISCOVERY':
        # Move to PITCH after 3 turns or when user clearly states their need
        if turn_count >= 3:
            return 'PITCH'
        return 'DISCOVERY'

    elif current_state == 'PITCH':
        for signal in DOUBT_SIGNALS:
            if signal in text_lower:
                return 'OBJECTION'
        for signal in POSITIVE_SIGNALS:
            if signal in text_lower:
                return 'CLOSE'
        return 'PITCH'

    elif current_state == 'OBJECTION':
        for signal in POSITIVE_SIGNALS:
            if signal in text_lower:
                return 'CLOSE'
        return 'OBJECTION'

    elif current_state == 'CLOSE':
        return 'DONE'

    elif current_state == 'DONE':
        return 'DONE'

    return current_state

# ── PROBLEM 4: GARBAGE STT DETECTION ──
VALID_SHORT_INPUTS = {
    'hello', 'हो', 'हाँ', 'हां', 'नाही', 'ha', 'ok', 'okay',
    'हाय', 'नमस्कार', 'हॅलो', 'bye', 'बाय', 'हम्म', 'hmm',
    'हं', 'अच्छा', 'ठीक', 'बरं', 'काय', 'सांगा'
}

GARBAGE_PATTERNS = {
    '', ' ', '।', '.', ',', '?', '!', '...', 
    'माईं', 'इक्ट', 'अन्ने',  # known hallucinations
}

def is_garbage_stt(text: str) -> bool:
    stripped = text.strip()
    lower = stripped.lower()
    
    # Explicit garbage
    if lower in GARBAGE_PATTERNS:
        return True
    
    # Valid short real words — keep them
    if lower in VALID_SHORT_INPUTS:
        return False
    
    # Too short and not a known real word
    if len(stripped) < 3:
        return True
    
    # Repetition of a single character (hallucination)
    if len(set(stripped.replace(' ', ''))) <= 2:
        return True
    
    return False

# ── PRE-CACHED INSTANT RESPONSES ──
# For common 1-word utterances, skip LLM entirely → instant TTS
INSTANT_RESPONSES = {
    "hi-IN": {
        "yes": "बहुत अच्छा! मैं आगे बताती हूँ।",
        "haan": "बहुत अच्छा! मैं आगे बताती हूँ।",
        "हाँ": "बहुत अच्छा! मैं आगे बताती हूँ।",
        "no": "कोई बात नहीं, क्या कोई और सवाल है?",
        "nahi": "कोई बात नहीं, क्या कोई और सवाल है?",
        "नहीं": "कोई बात नहीं, क्या कोई और सवाल है?",
        "busy": "ठीक है, मैं बाद में कॉल करती हूँ।",
        "not interested": "ठीक है, धन्यवाद। शुभ दिन!",
    },
    "en-IN": {
        "yes": "Great! Let me tell you more.",
        "no": "No problem, anything else I can help with?",
        "busy": "Sure, I'll call back later.",
        "not interested": "Alright, thank you for your time!",
    },
    "mr-IN": {
        "yes": "छान! मी पुढे सांगतो.",
        "हो": "छान! मी पुढे सांगतो.",
        "no": "ठीक आहे, काही प्रश्न आहे का?",
        "नाही": "ठीक आहे, काही प्रश्न आहे का?",
        "busy": "ठीक आहे, मी नंतर कॉल करतो.",
        "not interested": "ठीक आहे, धन्यवाद!",
    },
    "kn-IN": {
        "yes": "ಒಳ್ಳೆಯದು! ನಾನು ಹೇಳುತ್ತೇನೆ.",
        "ಹೌದು": "ಒಳ್ಳೆಯದು! ನಾನು ಹೇಳುತ್ತೇನೆ.",
        "no": "ಸರಿ, ಬೇರೆ ಪ್ರಶ್ನೆ ಇದೆಯೇ?",
        "ಇಲ್ಲ": "ಸರಿ, ಬೇರೆ ಪ್ರಶ್ನೆ ಇದೆಯೇ?",
        "busy": "ಸರಿ, ನಾನು ನಂತರ ಕರೆ ಮಾಡುತ್ತೇನೆ.",
        "not interested": "ಸರಿ, ಧನ್ಯವಾದ!",
    },
    "ta-IN": {
        "yes": "நல்லது! நான் மேலும் சொல்கிறேன்.",
        "ஆம்": "நல்லது! நான் மேலும் சொல்கிறேன்.",
        "no": "பரவாயில்ல, வேறு ஏதாவது கேள்வி?",
        "இல்லை": "பரவாயில்ல, வேறு ஏதாவது கேள்வி?",
        "busy": "சரி, நான் பிறகு அழைக்கிறேன்.",
        "not interested": "சரி, நன்றி!",
    },
    "te-IN": {
        "yes": "చాలా బాగుంది! నేను చెప్తాను.",
        "అవును": "చాలా బాగుంది! నేను చెప్తాను.",
        "no": "పర్వాలేదు, ఇంకేమైనా ప్రశ్న ఉందా?",
        "లేదు": "పర్వాలేదు, ఇంకేమైనా ప్రశ్న ఉందా?",
        "busy": "సరే, నేను తర్వాత కాల్ చేస్తాను.",
        "not interested": "సరే, ధన్యవాదాలు!",
    },
    "bn-IN": {
        "yes": "দারুণ! আমি বলছি.",
        "হ্যাঁ": "দারুণ! আমি বলছি.",
        "no": "ঠিক আছে, আর কিছু প্রশ্ন আছে?",
        "না": "ঠিক আছে, আর কিছু প্রশ্ন আছে?",
        "busy": "ঠিক আছে, পরে কল করব.",
        "not interested": "ঠিক আছে, ধন্যবাদ!",
    },
    "gu-IN": {
        "yes": "બહુ સરસ! હું આગળ કહું છું.",
        "હા": "બહુ સરસ! હું આગળ કહું છું.",
        "no": "ઠીક છે, બીજો કોઈ સવાલ?",
        "ના": "ઠીક છે, બીજો કોઈ સવાલ?",
        "busy": "ઠીક છે, હું પછી કૉલ કરીશ.",
        "not interested": "ઠીક છે, આભાર!",
    },
    "ml-IN": {
        "yes": "നല്ലത്! ഞാൻ പറയാം.",
        "ഉവ്വ്": "നല്ലത്! ഞാൻ പറയാം.",
        "no": "സാരമില്ല, വേറെ എന്തെങ്കിലും ചോദ്യം?",
        "ഇല്ല": "സാരമില്ല, വേറെ എന്തെങ്കിലും ചോദ്യം?",
        "busy": "ശരി, ഞാൻ പിന്നെ വിളിക്കാം.",
        "not interested": "ശരി, നന്ദി!",
    },
    "pa-IN": {
        "yes": "ਬਹੁਤ ਵਧੀਆ! ਮੈਂ ਅੱਗੇ ਦੱਸਦਾ ਹਾਂ.",
        "ਹਾਂ": "ਬਹੁਤ ਵਧੀਆ! ਮੈਂ ਅੱਗੇ ਦੱਸਦਾ ਹਾਂ.",
        "no": "ਕੋਈ ਗੱਲ ਨਹੀਂ, ਹੋਰ ਕੋਈ ਸਵਾਲ?",
        "ਨਹੀਂ": "ਕੋਈ ਗੱਲ ਨਹੀਂ, ਹੋਰ ਕੋਈ ਸਵਾਲ?",
        "busy": "ਠੀਕ ਹੈ, ਮੈਂ ਬਾਅਦ ਵਿੱਚ ਕਾਲ ਕਰਾਂਗਾ.",
        "not interested": "ਠੀਕ ਹੈ, ਸ਼ੁਕਰੀਆ!",
    },
    "or-IN": {
        "yes": "ବହୁତ ଭଲ! ମୁଁ ଆଗେଇ କହୁଛି.",
        "ହଁ": "ବହୁତ ଭଲ! ମୁଁ ଆଗେଇ କହୁଛି.",
        "no": "ଠିକ ଅଛି, ଆଉ କିଛି ପ୍ରଶ୍ନ ଅଛି?",
        "ନା": "ଠିକ ଅଛି, ଆଉ କିଛି ପ୍ରଶ୍ନ ଅଛି?",
        "busy": "ଠିକ ଅଛି, ମୁଁ ପରେ କଲ କରିବି.",
        "not interested": "ଠିକ ଅଛି, ଧନ୍ୟବାଦ!",
    },
}

# ── FILLER PHRASES (played while waiting for TTS) ──
FILLER_PHRASES = {
    "hi-IN": ["हम्म…", "एक सेकंड…", "ठीक है…", "जी…"],
    "en-IN": ["Hmm…", "One moment…", "Okay…", "Right…"],
    "mr-IN": ["हम्म…", "एक सेकंद…", "ठीक आहे…", "जी…"],
    "kn-IN": ["ಹಮ್ಮ…", "ಒಂದು ಕ್ಷಣ…", "ಸರಿ…"],
    "ta-IN": ["ஹ்ம்ம்…", "ஒரு நிமிடம்…", "சரி…"],
    "te-IN": ["హమ్మ్…", "ఒక్క సెకెండ్…", "సరే…"],
    "bn-IN": ["হুম…", "এক সেকেন্ড…", "ঠিক আছে…"],
    "gu-IN": ["હમ્મ…", "એક સેકંડ…", "ઠીક છે…"],
    "ml-IN": ["ഹ്മ്മ…", "ഒരു നിമിഷം…", "ശരി…"],
    "pa-IN": ["ਹਮਮ…", "ਇੱਕ ਸੈਕੰਡ…", "ਠੀਕ ਹੈ…"],
    "or-IN": ["ହମ୍ମ…", "ଏକ ସେକେଣ୍ଡ…", "ଠିକ ଅଛି…"],
}


class ConversationManager:
    """
    Ultra-low-latency conversation pipeline with optimizations:
    1. Parallel asyncio pipeline
    2. Chunked TTS playback
    3. Filler audio while waiting
    4. Pre-cached instant responses
    5. Memory optimization (5 messages)
    6. 1 sec silence detection
    7. Full latency logging
    """
    def __init__(self, websocket: WebSocket, call_sid: str):
        self.websocket = websocket
        self.call_sid = call_sid
        self.stream_sid = None
        self.stt = SarvamStreamingSTT()
        self.speaking_task: asyncio.Task = None
        self.last_agent_speech_time = 0.0
        self._pending_partial: str = None  # track partial STT for early LLM
        self._stt_buffer = []              # merges split sentences across breathing pauses
        self._stt_debounce_task = None     # handles sentence completion timing


        # Cached campaign config
        self.campaign_prompt = "You are a helpful AI assistant."
        self.llm_provider = "groq"
        self.voice = "priya"
        self.language = "hi-IN"
        self.company_name = "Our Company"
        self.campaign_name = "AI Assistant"  # Agent Title from campaign.name
        self.lead_name = "Customer"
        self.lead_phone = "Unknown"
        self.lead_metadata = {}  # Hermes enrichment data
        self.has_greeted = False
        
        self.state = 'GREETING'
        self.turn_count = 0
        self.intent_memory = []

        self._session_cache = {"history": []}
        self._processing = False  # Simple flag, no lock — latest input wins

        self.latency_controller = LatencyController(
            send_audio_func=self._stream_audio_to_twilio,
            cancel_tts_func=self.cancel_ongoing_tts,
            get_cached_audio_func=self._get_cached_audio
        )

    def _get_cached_audio(self, filler_key: str) -> bytes:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base_dir, "cache", "audio", f"{self.language}_{self.voice}_{filler_key}.mulaw")
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                return f.read()
        return b''

    async def _initialize_campaign_context(self):
        """Fetch campaign details AND Hermes lead intelligence once at call start."""
        try:
            with SessionLocal() as db:
                call_log = db.query(CallLog).filter(CallLog.call_sid == self.call_sid).first()
                if call_log and call_log.lead_id:
                    lead = db.query(Lead).filter(Lead.id == call_log.lead_id).first()
                    if lead:
                        self.lead_name = lead.name
                        self.lead_phone = lead.phone
                        self.language = lead.language or "hi-IN"  # Default to lead's specific lang
                        
                        # ── HERMES INTEGRATION: Load lead intelligence ──
                        if lead.metadata_json:
                            self.lead_metadata = lead.metadata_json
                            logger.info(f"HERMES_LOADED: Lead {lead.id} has {len(json.dumps(self.lead_metadata))} bytes of intelligence")
                        else:
                            self.lead_metadata = {}
                            logger.info(f"HERMES_EMPTY: Lead {lead.id} has no enrichment data")
                    else:
                        self.lead_name = "Customer"
                        self.lead_phone = "Unknown"
                        self.language = "hi-IN"
                        self.lead_metadata = {}
                        logger.info(f"HERMES_EMPTY: Lead {call_log.lead_id} not found")
                    
                    if lead and lead.campaign_id:
                        campaign = db.query(Campaign).filter(Campaign.id == lead.campaign_id).first()
                        if campaign:
                            self.campaign_prompt = campaign.script_template or self.campaign_prompt
                            self.llm_provider = getattr(campaign, "llm_provider", "groq")
                            self.voice = getattr(campaign, "voice", "priya")
                            # Only overwrite lead language if it's explicitly set in campaign and not in lead
                            if not lead.language:
                                self.language = getattr(campaign, "language", "hi-IN")
                            
                            self.campaign_name = campaign.name or self.campaign_name
                            
                            from app.models.core import Tenant
                            tenant = db.query(Tenant).filter(Tenant.id == campaign.tenant_id).first()
                            if tenant:
                                self.company_name = tenant.name
                            logger.info(f"Campaign loaded: name={self.campaign_name}, provider={self.llm_provider}, voice={self.voice}, lang={self.language}")
        except Exception as e:
            logger.error(f"Error initializing campaign context: {e}")

    async def start(self):
        # Context is definitively loaded later when Twilio sends "start" event.
        logger.info(f"Session started, awaiting Twilio socket events to hook language.")


        try:
            twilio_task = asyncio.create_task(self.receive_from_twilio())
            stt_task = asyncio.create_task(self.process_stt_stream_loop())
            await asyncio.gather(twilio_task, stt_task)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in conversation manager: {e}")
        finally:
            self.cancel_ongoing_tts()
            await self.stt.stop()

    async def receive_from_twilio(self):
        try:
            while True:
                message = await self.websocket.receive_text()
                data = json.loads(message)
                event = data.get("event")

                if event == "start":
                    self.stream_sid = data.get("streamSid")
                    logger.info(f"Stream started: {self.stream_sid}")
                    if not self.has_greeted:
                        # Load campaign context FIRST
                        await self._initialize_campaign_context()
                        self.stt.language = self.language
                        
                        # ── DYNAMIC GREETING: Generate live via TTS using campaign name ──
                        lang_name = LANGUAGE_NAMES.get(self.language, "Hindi")
                        FEMALE_VOICES = {"priya", "anushka", "manisha", "vidya", "arya", "ritu", "neha",
                                         "pooja", "simran", "kavya", "ishita", "shreya", "roopa", "tanya",
                                         "shruti", "suhani", "kavitha", "rupali", "female"}
                        agent_name = "Vani" if self.voice in FEMALE_VOICES else "Arjun"
                        
                        # Build a short, natural greeting in the campaign language
                        if self.language.startswith("en"):
                            greeting_text = f"Hello! I am {agent_name}, calling from {self.company_name} regarding {self.campaign_name}. How are you today?"
                        elif self.language.startswith("hi"):
                            greeting_text = f"नमस्कार! मैं {agent_name} बोल रही हूँ, {self.company_name} से {self.campaign_name} के बारे में। आप कैसे हैं?"
                        elif self.language.startswith("mr"):
                            greeting_text = f"नमस्कार! मी {agent_name}, {self.company_name} मधून {self.campaign_name} बद्दल बोलत आहे. तुम्ही कसे आहात?"
                        else:
                            # Fallback: use Hindi greeting for other Indic languages
                            greeting_text = f"नमस्कार! मैं {agent_name}, {self.company_name} से {self.campaign_name} के बारे में बात कर रही हूँ।"
                        
                        logger.info(f"DYNAMIC_GREETING: Generating TTS for: {greeting_text}")
                        
                        try:
                            greeting_audio = await asyncio.wait_for(
                                TTSService.generate_speech(greeting_text, language=self.language, speaker=self.voice),
                                timeout=15.0
                            )
                        except Exception as e:
                            logger.error(f"GREETING_TTS_FAILED: {e}")
                            greeting_audio = b""
                        
                        if not greeting_audio or len(greeting_audio) == 0:
                            # Fallback to cached/silence if TTS fails
                            greeting_audio = self._get_cached_audio("greeting")
                            if not greeting_audio:
                                greeting_audio = self._get_fallback_audio()
                            
                        await self.send_audio_safe(greeting_audio)
                        self.last_agent_speech_time = time.time()
                        
                        self._session_cache["history"].append({"role": "assistant", "content": greeting_text})
                        self._session_cache["conversation_stage"] = "GREETING"
                        self.has_greeted = True

                elif event == "media":
                    payload = data["media"]["payload"]
                    audio_bytes = base64.b64decode(payload)
                    await self.stt.push_chunk(audio_bytes)

                elif event == "stop":
                    logger.info("Call stopped by Twilio.")
                    break
        except WebSocketDisconnect:
            logger.info("Twilio disconnected.")
        except Exception as e:
            logger.error(f"Error in receive_from_twilio: {e}")

    async def process_stt_stream_loop(self):
        """Handles both partial and final STT transcripts."""
        while True:
            try:
                async for result in self.stt.process_stream():
                    is_final = result.get("is_final", False)
                    text = result.get("text", "")

                    # ── Confidence Gate for Twilio Barge-in / Transcript ──
                    is_garbage = is_garbage_stt(text)

                    # ── SOFT BARGE-IN (with protection window + fade-out) ──
                    if self.speaking_task and not self.speaking_task.done():
                        # Only allow barge-in if the incoming STT is not garbage hallucinations
                        if not is_garbage:
                            speech_ms = result.get("speech_ms", 0)
                            time_since = time.time() - self.last_agent_speech_time
                            # Only allow barge-in if agent has been speaking for >1.5s AND user spoke >800ms
                            if speech_ms >= 800 and time_since > 1.5:
                                logger.info(f"⚡ SOFT_BARGE_IN: {text} (duration: {speech_ms}ms, agent_played: {time_since:.1f}s)")
                                await self.latency_controller.on_user_barge_in()
                                # Soft cancel: send clear after 150ms for fade effect
                                await asyncio.sleep(0.15)
                                self.cancel_ongoing_tts()
                                await self.send_clear_to_twilio()

                    if not is_final:
                        if len(text) > 0 and self._stt_debounce_task and not self._stt_debounce_task.done():
                            self._stt_debounce_task.cancel()  # Extend silence window if user is still talking
                        logger.info(f"📝 Partial STT (latency hint only): {text}")
                    else:
                        # ── FINAL: trigger full response with smart debounce buffer ──
                        if is_final and len(text) > 0:
                            if self._stt_debounce_task and not self._stt_debounce_task.done():
                                self._stt_debounce_task.cancel()
                                
                            self._stt_buffer.append(text)
                            
                            async def debounced_trigger():
                                await asyncio.sleep(0.15)  # 150ms micro-buffer for sentence merging (VAD already applies 800ms silence detection)
                                combined_text = " ".join(self._stt_buffer)
                                self._stt_buffer.clear()
                                
                                text_clean = combined_text.strip().lower()
                                if is_garbage:
                                    logger.info(f"GARBAGE_STT_DISCARDED: '{combined_text}'")
                                    return
                                    
                                if text_clean in FILLER_WORDS or (len(text_clean.split()) == 1 and text_clean in FILLER_WORDS):
                                    logger.info(f"FILLER_IGNORED: '{combined_text}' — skipping LLM/TTS")
                                    return
                                    
                                session = await redis_client.get_session(self.call_sid)
                                intent = PolicyEngine.detect_intent(combined_text)
                                await self.latency_controller.on_user_speech_end(intent)
                                
                                logger.info(f"User Final (Buffered): {combined_text}")
                                self.cancel_ongoing_tts()
                                self.speaking_task = asyncio.create_task(self._generate_and_speak(combined_text))
                                
                            self._stt_debounce_task = asyncio.create_task(debounced_trigger())

            except Exception as e:
                logger.error(f"Error in process_stt_stream_loop: {e}, restarting...")
                await asyncio.sleep(1)

    def cancel_ongoing_tts(self):
        if self.speaking_task and not self.speaking_task.done():
            self.speaking_task.cancel()

    async def send_clear_to_twilio(self):
        if self.stream_sid:
            msg = {"event": "clear", "streamSid": self.stream_sid}
            await self.websocket.send_text(json.dumps(msg))

    async def trigger_agent_response(self, user_text: str):
        self.cancel_ongoing_tts()
        self.speaking_task = asyncio.create_task(self._generate_and_speak(user_text))

    def _check_instant_response(self, text: str) -> str:
        """Check if the user's text matches a pre-cached instant response."""
        normalized = text.strip().lower()
        lang_cache = INSTANT_RESPONSES.get(self.language, {})

        # Also check the fallback Hindi/English caches
        for cache in [lang_cache, INSTANT_RESPONSES.get("hi-IN", {}), INSTANT_RESPONSES.get("en-IN", {})]:
            if normalized in cache:
                return cache[normalized]
        return None



    def _get_fallback_audio(self) -> bytes:
        """Get fallback audio from cache, with hard fallback to silence."""
        audio = self._get_cached_audio("fallback")
        if audio:
            return audio
            
        # Try generic Hindi fallback if specific language is missing
        generic = self._get_cached_audio("hi-IN")
        if generic:
            return generic
            
        # Absolute last resort: 200ms of mu-law silence
        return b'\xff' * 1600

    async def send_audio_safe(self, audio: bytes):
        if not audio or len(audio) == 0:
            logger.info("FALLBACK_USED")
            audio = self._get_fallback_audio()
            
        await self._stream_audio_to_twilio(audio)
        logger.info("AUDIO_SENT")
        
    async def _stream_audio_to_twilio(self, audio_bytes: bytes):
        """Stream mu-law audio bytes to Twilio in exactly 160-byte chunks (20ms) perfectly synced with Twilio's jitter buffer."""
        chunk_size = 160
        for i in range(0, len(audio_bytes), chunk_size):
            if asyncio.current_task().cancelled():
                raise asyncio.CancelledError()
            chunk = audio_bytes[i:i + chunk_size]
            payload = base64.b64encode(chunk).decode("utf-8")
            msg = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": payload}
            }
            await self.websocket.send_text(json.dumps(msg))
            await asyncio.sleep(0.018)  # 18ms pacing to prevent Twilio buffer overrun

    async def _generate_and_speak(self, user_text: str):
        turn_start = time.time()

        # If already processing, cancel old and take new (latest input wins)
        if self._processing:
            logger.info("NEW_INPUT_OVERRIDE: cancelling previous response")
            self.cancel_ongoing_tts()
            await asyncio.sleep(0.05)  # let cancellation propagate
        
        self._processing = True
        try:
            # ── OPT 6: PRE-CACHED INSTANT RESPONSE ──
            instant = self._check_instant_response(user_text)
            if instant:
                logger.info(f"⚡ INSTANT RESPONSE: {instant}")
                audio = await TTSService.generate_speech(instant, language=self.language, speaker=self.voice)
                if audio:
                    e2e_ms = int((time.time() - turn_start) * 1000)
                    logger.info(f"⏱ E2E_LATENCY_MS={e2e_ms} (instant)")
                    self.last_agent_speech_time = time.time()
                    await self._stream_audio_to_twilio(audio)
                self._session_cache["history"].append({"role": "assistant", "content": instant})
                total_ms = int((time.time() - turn_start) * 1000)
                logger.info(f"⏱ TURN_TOTAL_MS={total_ms} (instant)")
                return

            # ── INTENT MEMORY: extract & store keywords ──
            stage = self.state
            history = self._session_cache.get("history", [])
            
            # Extract keywords for context memory
            new_keywords = PolicyEngine.extract_keywords(user_text)
            if new_keywords:
                self.intent_memory = list(set(self.intent_memory + new_keywords))[-8:]  # keep last 8
                logger.info(f"INTENT_DETECTED: {new_keywords} | MEMORY: {self.intent_memory}")

            history.append({"role": "user", "content": user_text})
            self.turn_count += 1

            # 7. AMBIGUITY HANDLING (context-aware with intent memory)
            is_ambig, ambig_resp = PolicyEngine.check_ambiguity(user_text, self.language, stage, self.intent_memory)
            if is_ambig:
                if getattr(self, "last_ambig_turn", -1) == self.turn_count - 1:
                    logger.info("AMBIGUITY LOOP DETECTED: Forcing guided question.")
                    valid_response = "काय आप पढ़ाई या नौकरी के बारे में पूछ रहे हैं?"
                else:
                    valid_response = ambig_resp
                self.last_ambig_turn = self.turn_count
                new_stage = stage
                logger.info(f"Ambiguity detected. Skipping LLM.")
                await self.latency_controller.on_llm_first_token()
            else:
                # ── HERMES-POWERED SYSTEM PROMPT via prompt_builder ──
                system_prompt_template = build_call_prompt(
                    campaign_script=self.campaign_prompt,
                    lead_metadata=self.lead_metadata,
                    language=self.language,
                    voice=self.voice,
                    company_name=self.company_name,
                    campaign_name=self.campaign_name,
                    lead_name=self.lead_name,
                    lead_phone=self.lead_phone,
                    stage=stage,
                    intent_memory=self.intent_memory,
                    turn_count=self.turn_count,
                )

                recent_history = history[-5:]
                hist_str = ""
                for msg in recent_history:
                    role_str = "User" if msg['role'] == "user" else "Agent"
                    hist_str += f"{role_str}: {msg['content']}\n"
                full_system_prompt = f"{system_prompt_template}\nRecent Context:\n{hist_str}\nUser: {user_text}\n\nAgent:"
                messages = [{"role": "system", "content": full_system_prompt}]

                valid_response = ""
                max_attempts = 2
                fallback_triggered = False
                
                logger.info(f"LANGUAGE_ENFORCED: {self.language}")
                
                for attempt in range(max_attempts):
                    if asyncio.current_task().cancelled():
                        return
                        
                    t0 = time.time()
                    try:
                        # Wrap LLM call with a strict timeout
                        raw_response = await asyncio.wait_for(
                            LLMService.generate_response(messages, provider=self.llm_provider),
                            timeout=3.5
                        )
                        response_time = time.time() - t0
                        logger.info(f"LLM_RESPONSE_TIME: {response_time:.2f}s")
                    except asyncio.TimeoutError:
                        logger.warning("LLM TimeoutError: generation took too long.")
                        valid_response = fallback_response(self.language)
                        fallback_triggered = True
                        break
                        
                    # 9. LOGGING
                    logger.info(f"FULL_LLM_RESPONSE: {raw_response}")
                    
                    # Signal Latency Controller
                    await self.latency_controller.on_llm_first_token()
                    
                    is_valid, reason = PolicyEngine.validate_response(raw_response, user_text)
                    if is_valid:
                        if detect_language_mismatch(raw_response, self.language):
                            logger.warning(f"LANGUAGE MISMATCH DETECTED: Expected {self.language}")
                            valid_response = fallback_response(self.language)
                            fallback_triggered = True
                            break

                        valid_response = raw_response
                        break
                    else:
                        logger.warning(f"Response rejected by PolicyEngine: {reason}. Regenerating...")

                if not valid_response:
                    valid_response = fallback_response(self.language)
                    fallback_triggered = True
                    
                logger.info(f"FALLBACK_USED: {fallback_triggered}")
            
            # Apply strict limit
            valid_response = clean_llm_for_tts(valid_response, max_chars=250)
            
            if len(valid_response.strip()) == 0:
                valid_response = "कृपया फिर से बताएं"
                
            logger.info(f"RESPONSE_LENGTH: {len(valid_response)}")
            logger.info(f"FINAL_TTS_INPUT: {valid_response}")

            # STATE MACHINE CORRECTION
            new_stage = compute_next_state(
                current_state=self.state,
                user_text=user_text,
                intent_memory=self.intent_memory,
                turn_count=self.turn_count
            )
            self.state = new_stage
            logger.info(f"STATE_TRANSITION: {stage} -> {new_stage}")

            self.last_agent_speech_time = time.time()
            
            async def safe_tts(text: str) -> bytes:
                try:
                    response = await asyncio.wait_for(
                        TTSService.generate_speech(text, language=self.language, speaker=self.voice),
                        timeout=15.0
                    )
                    if not response or len(response) == 0:
                        raise Exception("Empty TTS output")
                    logger.info("TTS_SUCCESS")
                    return response
                except Exception as e:
                    logger.error(f"TTS FAILED: {e}")
                    logger.info("FALLBACK_USED")
                    return self._get_fallback_audio()
            
            async def state_update_routine():
                self._session_cache["history"] = history[-5:] + [{"role": "assistant", "content": valid_response}]
                await redis_client.save_session(self.call_sid, self._session_cache)
                logger.info("STATE_UPDATE = Completed Async")
                
            async def tts_send_routine():
                audio = await safe_tts(valid_response)
                await self.send_audio_safe(audio)
                
                e2e_ms = int((time.time() - turn_start) * 1000)
                logger.info(f"⏱ E2E_LATENCY_MS={e2e_ms} (turn start → one TTS call)")
                self.last_agent_speech_time = time.time()
                    
            try:
                # PARALLEL EXECUTION
                asyncio.create_task(state_update_routine())
                await tts_send_routine()
            except asyncio.CancelledError:
                logger.info("Agent TTS task cancelled (barge-in).")
                raise

            total_turn_ms = int((time.time() - turn_start) * 1000)
            logger.info(f"Agent ({self.language}) [{new_stage}]: {valid_response}")
            logger.info(f"⏱ TURN_TOTAL_MS={total_turn_ms}")

        except asyncio.CancelledError:
            logger.info("Agent task cancelled (barge-in).")
        except Exception as e:
            logger.error(f"Error in speaking task: {e}")
        finally:
            self._processing = False

