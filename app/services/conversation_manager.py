import asyncio
import json
import logging
import base64
import time
import random

logger = logging.getLogger(__name__)
from fastapi import WebSocket, WebSocketDisconnect
from app.services.stt import SarvamStreamingSTT
from app.services.llm import LLMService
from app.services.tts import TTSService
from app.services.redis_store import redis_client
from app.config.database import SessionLocal
from app.models.core import CallLog, Lead, Campaign
from app.services.policy_engine import PolicyEngine
from app.services.latency_controller import LatencyController
import re
import os
from typing import Optional, List, Dict, Any
from app.services.exceptions import (
    STTBufferException, CampaignLoadException,
    TTSGenerationException, LLMInferenceException, TwilioStreamException
)

# ── FILLER WORDS: skip LLM/TTS entirely ──
FILLER_WORDS = {
    "जी", "हाँ", "hmm"
}

# Map BCP-47 codes to human-readable language names for the LLM
from app.services.prompt_builder import LANGUAGE_NAMES, FEMALE_VOICES, detect_language_mismatch, fallback_response, build_call_prompt

import re

# ── PROBLEM 2: CLEAN LLM FOR TTS ──
import re
from typing import Optional

# ── Sentence boundary patterns for all supported languages ──────────────────
# Devanagari (Hindi, Marathi): ।  Double danda: ॥
# Tamil: ।, .  Telugu: ।, .  Bengali: ।, .
_HARD_SENTENCE_BREAKS = re.compile(r'(?<=[.!?।॥])\s+')
_SOFT_CLAUSE_BREAKS = re.compile(r'(?<=[,;:])\s+')

def clean_llm_for_tts(
    text: str,
    max_chars: int = 180,
    ellipsis: str = "..."
) -> str:
    """
    Safely prepare LLM output for TTS generation.

    Truncation priority (highest to lowest):
    1. Hard sentence boundary (. ! ? । ॥)
    2. Soft clause boundary (, ; :)
    3. Word boundary (space)
    4. Hard character cut (last resort — should almost never happen)

    All truncated text gets an ellipsis so TTS generates a natural trailing tone.
    Also strips markdown, code blocks, HTML tags, and emoji.
    """
    if not text:
        return ""

    # ── Step 1: Strip formatting noise ──────────────────────────────────────
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)            # *italic*
    text = re.sub(r'`(.+?)`', r'\1', text)              # `code`
    text = re.sub(r'#{1,6}\s+', '', text)               # # headings
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [link](url)
    text = re.sub(r'<[^>]+>', '', text)                  # HTML tags

    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Remove emoji (basic Unicode ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\u2600-\u26FF\u2700-\u27BF]', '', text
    )

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # ── Step 2: Return as-is if within limit ────────────────────────────────
    if len(text) <= max_chars:
        return text

    # ── Step 3: Find best truncation point ──────────────────────────────────
    search_window = text[:max_chars]

    # Priority 1: Hard sentence break (. ! ? । ॥)
    sentence_positions = [
        search_window.rfind('.'),
        search_window.rfind('!'),
        search_window.rfind('?'),
        search_window.rfind('।'),
        search_window.rfind('॥'),
    ]
    best_sentence = max(p for p in sentence_positions)

    # Only use sentence break if it's past 40% of max_chars (avoids tiny fragments)
    if best_sentence > max_chars * 0.40:
        return text[:best_sentence + 1].strip()

    # Priority 2: Soft clause break (, ; :)
    clause_positions = [
        search_window.rfind(','),
        search_window.rfind(';'),
        search_window.rfind(':'),
    ]
    best_clause = max(p for p in clause_positions)

    if best_clause > max_chars * 0.35:
        return text[:best_clause].strip() + ellipsis

    # Priority 3: Word boundary (space)
    last_space = search_window.rfind(' ')
    if last_space > max_chars * 0.30:
        return text[:last_space].strip() + ellipsis

    # Priority 4: Hard cut (last resort)
    return text[:max_chars].strip() + ellipsis


def split_text_for_streaming_tts(
    text: str,
    max_chunk_chars: int = 100
) -> list[str]:
    """
    Split cleaned LLM output into sentence-sized chunks for streaming TTS.
    Each chunk generates one TTS audio segment.

    Use this instead of clean_llm_for_tts() when implementing streaming TTS.
    Chunks are split at sentence boundaries, falling back to clause boundaries.
    """
    text = clean_llm_for_tts(text, max_chars=99999)  # clean but don't truncate

    if len(text) <= max_chunk_chars:
        return [text] if text else []

    # Split on hard sentence boundaries first
    raw_sentences = _HARD_SENTENCE_BREAKS.split(text)
    chunks = []
    current_chunk = ""

    for sentence in raw_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 <= max_chunk_chars:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single sentence exceeds max_chunk_chars, split at clauses
            if len(sentence) > max_chunk_chars:
                sub_chunks = _split_at_clauses(sentence, max_chunk_chars)
                chunks.extend(sub_chunks[:-1])
                current_chunk = sub_chunks[-1] if sub_chunks else ""
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return [c for c in chunks if c.strip()]


def _split_at_clauses(text: str, max_chars: int) -> list[str]:
    """Split a single long sentence at clause boundaries."""
    parts = _SOFT_CLAUSE_BREAKS.split(text)
    result = []
    current = ""
    for part in parts:
        if len(current) + len(part) + 1 <= max_chars:
            current += (" " if current else "") + part
        else:
            if current:
                result.append(current)
            current = part
    if current:
        result.append(current)
    return result if result else [text[:max_chars]]

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


def normalize_language_code(lang: str) -> str:
    """Normalizes human names like 'Marathi' or 'Bangla' to BCP-47 codes."""
    if not lang: return "hi-IN"
    
    mapping = {
        "hindi": "hi-IN", "english": "en-IN", "marathi": "mr-IN",
        "bengali": "bn-IN", "bangla": "bn-IN", "tamil": "ta-IN",
        "telugu": "te-IN", "kannada": "kn-IN", "gujarati": "gu-IN",
        "malayalam": "ml-IN", "punjabi": "pa-IN", "odia": "or-IN", "oriya": "or-IN"
    }
    cleaned = lang.lower().strip()
    return mapping.get(cleaned, lang)

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
        self._audio_buffer = bytearray()   # Buffer for perfect 20ms chunks


        # Cached campaign config
        self.campaign_prompt = "You are a helpful AI assistant."
        self.llm_provider = "groq"
        self.voice = "priya"
        self.language = "hi-IN"
        self.company_name = "Our Company"
        self.campaign_name = "AI Assistant"  # Agent Title from campaign.name
        self.lead_name = "Customer"
        self.lead_phone = "Unknown"
        self.has_greeted = False
        self._full_transcript = []  # Maintain full history for recent calls
        
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

        self._fallback_audio_cache: dict[str, str] = {}
        fallback_dir = os.path.join(os.path.dirname(__file__), "../../assets/fallbacks")
        for lang_code in ["hi", "mr", "ta", "te", "bn", "en"]:
            fallback_path = os.path.join(fallback_dir, f"fallback_{lang_code}.wav")
            if os.path.exists(fallback_path):
                try:
                    import wave, audioop, struct
                    with wave.open(fallback_path, "rb") as wav:
                        pcm_data = wav.readframes(wav.getnframes())
                        sampwidth = wav.getsampwidth()
                        framerate = wav.getframerate()
                        channels = wav.getnchannels()
                        
                        if channels > 1:
                            pcm_data = audioop.tomono(pcm_data, sampwidth, 1, 1)
                        if sampwidth != 2:
                            pcm_data = audioop.lin2lin(pcm_data, sampwidth, 2)
                            sampwidth = 2
                        if framerate != 8000:
                            pcm_data, _ = audioop.ratecv(pcm_data, sampwidth, 1, framerate, 8000, None)
                            
                        # Encode to mu-law
                        ulaw_data = audioop.lin2ulaw(pcm_data, sampwidth)
                        self._fallback_audio_cache[lang_code] = base64.b64encode(ulaw_data).decode()
                except Exception as e:
                    logger.warning(f"Error parsing fallback {fallback_path}: {e}")
            else:
                logger.warning(f"[ConversationManager] Missing fallback audio for lang: {lang_code}")

    def _get_cached_audio(self, filler_key: str) -> bytes:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base_dir, "cache", "audio", f"{self.language}_{self.voice}_{filler_key}.mulaw")
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                return f.read()
        return b''

    async def _initialize_campaign_context(self):
        """Fetch campaign details once at call start."""
        try:
            with SessionLocal() as db:
                call_log = db.query(CallLog).filter(CallLog.call_sid == self.call_sid).first()
                if call_log and call_log.lead_id:
                    lead = db.query(Lead).filter(Lead.id == call_log.lead_id).first()
                    if lead:
                        self.lead_name = lead.name
                        self.lead_phone = lead.phone
                        self.language = lead.language or "hi-IN"
                    else:
                        self.lead_name = "Customer"
                        self.lead_phone = "Unknown"
                        self.language = "hi-IN"
                    if lead and lead.campaign_id:
                        campaign = db.query(Campaign).filter(Campaign.id == lead.campaign_id).first()
                        if campaign:
                            self.campaign_prompt = campaign.script_template or self.campaign_prompt
                            self.llm_provider = getattr(campaign, "llm_provider", "groq")
                            self.voice = getattr(campaign, "voice", "priya")
                            
                            # CAMPAIGN WINS: If campaign has a language, use it over the lead default
                            camp_lang = getattr(campaign, "language", None)
                            if camp_lang:
                                self.language = normalize_language_code(camp_lang)
                            
                            self.campaign_name = campaign.name or self.campaign_name
                            
                            from app.models.core import Tenant
                            tenant = db.query(Tenant).filter(Tenant.id == campaign.tenant_id).first()
                            if tenant:
                                self.company_name = tenant.name
                            
                    # Final safety normalization
                    self.language = normalize_language_code(self.language)
                    logger.info(f"Campaign Loaded: name={self.campaign_name}, provider={self.llm_provider}, voice={self.voice}, lang={self.language}")
        except Exception as e:
            logger.error(f"Error initializing campaign context: {e}")

    async def start(self):
        # Context is definitively loaded later when Twilio sends "start" event.
        logger.info(f"Session started, awaiting Twilio socket events to hook language.")

        try:
            twilio_task = asyncio.create_task(self.receive_from_twilio())
            stt_task = asyncio.create_task(self.process_stt_stream_loop())
            keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            
            # Wait for any of them to fail or finish
            done, pending = await asyncio.wait(
                [twilio_task, stt_task, keep_alive_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in done:
                try:
                    task.result()
                except Exception as e:
                    logger.error(f"Task failed in conversation manager: {e}")
            
            for task in pending:
                task.cancel()
        except Exception as e:
            logger.error(f"Error in conversation manager: {e}")
        finally:
            self.cancel_ongoing_tts()
            await self.stt.stop()

    async def _keep_alive_loop(self):
        """Sends a tiny silence chunk every 3 seconds to keep the proxy connection alive."""
        while True:
            await asyncio.sleep(3.0)
            if self.stream_sid:
                # 20ms of silence
                await self._stream_audio_to_twilio(b'\xff' * 160)
                logger.debug("KEEP_ALIVE_SENT")

    async def receive_from_twilio(self):
        logger.info(f"[receive_from_twilio] Stream loop started. Call SID: {self.call_sid}")
        try:
            async for raw_message in self.websocket.iter_text():
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError as e:
                    logger.warning(f"[receive_from_twilio] Malformed JSON frame: {e}. Skipping.")
                    continue  

                event = data.get("event", "")

                if event == "stop":
                    logger.info("[receive_from_twilio] Twilio stop event received. Exiting loop.")
                    break
                elif event == "connected":
                    logger.info("[receive_from_twilio] Twilio WebSocket connected.")
                    continue
                elif event == "start":
                    try:
                        await self._handle_stream_start(data)
                    except CampaignLoadException as e:
                        logger.error(f"[stream_start] Campaign load failed: {e}")
                        await self.send_audio_safe(b"") # fallback via send_audio_safe
                    except Exception as e:
                        logger.exception(f"[stream_start] Unexpected error: {e}")
                        await self.send_audio_safe(b"") # fallback via send_audio_safe
                    continue
                elif event == "media":
                    try:
                        await self._handle_media_chunk(data)
                    except KeyError as e:
                        logger.warning(f"[media] Missing key: {e}. Frame skipped.")
                        continue  
                    except STTBufferException as e:
                        logger.error(f"[media] STT buffer error: {e}")
                        await self.send_audio_safe(b"")
                        continue
                    except TwilioStreamException as e:
                        logger.critical(f"[media] Fatal Twilio stream error: {e}. Exiting loop.")
                        break
                    except Exception as e:
                        logger.exception(f"[media] Unhandled exception (kept alive): {e}")
                        await self.send_audio_safe(b"")
                        continue
                else:
                    logger.debug(f"[receive_from_twilio] Unknown event '{event}'. Ignoring.")
                    continue
        except WebSocketDisconnect:
            logger.info("Twilio disconnected.")
        except Exception as e:
            logger.exception(f"Fatal error in receive_from_twilio loop: {e}")
            
    async def _handle_stream_start(self, data):
        self.stream_sid = data.get("streamSid")
        if not self.stream_sid:
            raise CampaignLoadException("streamSid missing from start event")
        logger.info(f"Stream started: {self.stream_sid}")
        if not self.has_greeted:
            logger.info(f"FIRST_EVENT: Handling 'start' for {self.call_sid}")
            self.has_greeted = True # Mark first so we don't repeat
            
            # 1. IMMEDIATE AUDIO PING (Prevent Twilio Timeout)
            # This is 400ms of soft comfort noise / silence in mu-law
            SAFETY_PING = b'\xff' * 3200 
            await self._stream_audio_to_twilio(SAFETY_PING)
            
            # 2. Async Context Loading
            await self._initialize_campaign_context()
            self.stt.language = self.language
            
            # 3. Dynamic Multi-Lingual Greeting Fallback
            GREETINGS_BY_LANG = {
                "hi-IN": f"नमस्कार! मैं {self.campaign_name} से {self.company_name} के लिए बात कर रही हूँ।",
                "en-IN": f"Hello! I am {self.campaign_name}, calling from {self.company_name}.",
                "mr-IN": f"नमस्कार! मी {self.campaign_name}, {self.company_name} मधून बोलत आहे.",
                "bn-IN": f"নমস্কার! আমি {self.campaign_name}, {self.company_name} থেকে কথা বলছি।",
                "ta-IN": f"வணக்கம்! நான் {self.campaign_name}, {self.company_name} லிருந்து அழைக்கிறேன்.",
                "te-IN": f"నమస్కారం! నేను {self.campaign_name}, {self.company_name} నుండి మాట్లాడుతున్నాను.",
                "kn-IN": f"ನಮಸ್ಕಾರ! ನಾನು {self.campaign_name}, {self.company_name} ನಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ.",
                "gu-IN": f"નમસ્તે! હું {self.campaign_name}, {self.company_name} માંથી બોલું છું.",
                "ml-IN": f"നമസ്കാരം! ഞാൻ {self.campaign_name}, {self.company_name}ൽ നിന്നാണ് വിളിക്കുന്നത്.",
                "pa-IN": f"ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ {self.campaign_name}, {self.company_name} ਤੋਂ ਗੱਲ ਕਰ ਰਿਹਾ ਹਾਂ।",
                "or-IN": f"ନମସ୍କାର! ମୁଁ {self.campaign_name}, {self.company_name} ରୁ କଥା କହୁଛି।",
            }
            
            greeting_text = GREETINGS_BY_LANG.get(self.language) or GREETINGS_BY_LANG["hi-IN"]
                
            logger.info(f"GREETING_PLAN: Generating TTS for: {greeting_text} (Lang: {self.language})")

            try:
                # Try real TTS but with a TIGHT timeout
                greeting_audio = await asyncio.wait_for(
                    TTSService.generate_speech(greeting_text, language=self.language, speaker=self.voice),
                    timeout=4.0
                )
            except Exception as e:
                logger.error(f"GREETING_TTS_FAILED: {e}")
                greeting_audio = b""

            if not greeting_audio:
                greeting_audio = self._get_fallback_audio()

            await self.send_audio_safe(greeting_audio)
            self.last_agent_speech_time = time.time()
            self._session_cache["history"].append({"role": "assistant", "content": greeting_text})
            logger.info("GREETING_SENT: Call is now interactive.")

    async def _handle_media_chunk(self, data):
        payload = data["media"]["payload"]
        audio_bytes = base64.b64decode(payload)
        await self.stt.push_chunk(audio_bytes)

    async def process_stt_stream_loop(self):
        """Handles both partial and final STT transcripts."""
        while True:
            try:
                async for result in self.stt.process_stream():
                    is_final = result.get("is_final", False)
                    text = result.get("text", "")

                    # ── Confidence Gate for Twilio Barge-in / Transcript ──
                    is_garbage = is_garbage_stt(text)

                    # ── HARD BARGE-IN (Faster detection for overspeaking) ──
                    if self.speaking_task and not self.speaking_task.done():
                        if not is_garbage:
                            speech_ms = result.get("speech_ms", 0)
                            # Allow barge-in if user spoke for >400ms
                            if speech_ms >= 400:
                                logger.info(f"⚡ BARGE_IN_DETECTED: {text} ({speech_ms}ms)")
                                await self.latency_controller.on_user_barge_in()
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
        lang = getattr(self, "language", "hi-IN")
        short_lang = lang.split("-")[0]
        
        fallback_b64 = self._fallback_audio_cache.get(short_lang) or \
                       self._fallback_audio_cache.get("hi") or \
                       self._fallback_audio_cache.get("en")
                       
        if fallback_b64:
            return base64.b64decode(fallback_b64)
            
        audio = self._get_cached_audio("fallback")
        if audio:
            return audio
            
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
        """
        Buffer and stream mu-law audio bytes to Twilio with strict 20ms pacing.
        Twilio expects exactly 160 bytes of mu-law per 'media' event.
        """
        if not audio_bytes:
            return

        self._audio_buffer.extend(audio_bytes)
        chunk_size = 160  # 20ms at 8000Hz mu-law
        
        while len(self._audio_buffer) >= chunk_size:
            if asyncio.current_task().cancelled():
                raise asyncio.CancelledError()
                
            chunk = self._audio_buffer[:chunk_size]
            del self._audio_buffer[:chunk_size]
            
            payload = base64.b64encode(chunk).decode("utf-8")
            msg = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": payload}
            }
            await self.websocket.send_text(json.dumps(msg))
            # Strict 20ms pacing (accounting for loop overhead)
            await asyncio.sleep(0.0195) 

    async def flush_audio_buffer(self):
        """Sends remaining bytes with padding to complete the last 20ms frame."""
        if self._audio_buffer:
            padding_needed = 160 - len(self._audio_buffer)
            if padding_needed > 0:
                self._audio_buffer.extend(b'\xff' * padding_needed)
            await self._stream_audio_to_twilio(b"")


    async def _generate_and_speak(self, user_text: str):
        turn_start = time.time()
        if self._processing:
            logger.info("NEW_INPUT_OVERRIDE: cancelling previous response")
            self.cancel_ongoing_tts()
            await asyncio.sleep(0.05)
        
        self._processing = True
        try:
            instant = self._check_instant_response(user_text)
            if instant:
                logger.info(f"⚡ INSTANT RESPONSE: {instant}")
                audio = await TTSService.generate_speech(instant, language=self.language, speaker=self.voice)
                if audio:
                    await self._stream_audio_to_twilio(audio)
                self._session_cache["history"].append({"role": "assistant", "content": instant})
                self._full_transcript.append(f"Assistant: {instant}")
                return

            stage = self.state
            history = self._session_cache.get("history", [])
            new_keywords = PolicyEngine.extract_keywords(user_text)
            if new_keywords:
                self.intent_memory = list(set(self.intent_memory + new_keywords))[-8:]

            history.append({"role": "user", "content": user_text})
            self._full_transcript.append(f"User: {user_text}")
            self.turn_count += 1

            is_ambig, ambig_resp = PolicyEngine.check_ambiguity(user_text, self.language, stage, self.intent_memory)
            if is_ambig:
                valid_response = ambig_resp
                await self.latency_controller.on_llm_first_token()
                async for audio_chunk in TTSService.generate_speech_streaming(valid_response, language=self.language, speaker=self.voice):
                    await self.send_audio_safe(audio_chunk)
            else:
                system_prompt_template = build_call_prompt(
                    campaign_script=self.campaign_prompt,
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
                hist_str = "\n".join([f"{'User' if m['role']=='user' else 'Agent'}: {m['content']}" for m in recent_history])
                full_system_prompt = f"{system_prompt_template}\nRecent Context:\n{hist_str}\nUser: {user_text}\n\nAgent:"
                messages = [{"role": "system", "content": full_system_prompt}]

                # ── STREAMING LLM (JSON) -> TTS PIPELINE ──
                complete_response = ""
                played_chunks = []
                first_token = True
                has_played_fallback = False
                
                # Regex to find "text": "..." values in partially-formed JSON
                text_extractor = re.compile(r'\"text\":\s*\"([^\"]+)\"', re.DOTALL)
                
                async for llm_chunk in LLMService.generate_response_stream(messages, provider=self.llm_provider):
                    if asyncio.current_task().cancelled(): return
                    if first_token:
                        await self.latency_controller.on_llm_first_token()
                        first_token = False
                    
                    complete_response += llm_chunk
                    
                    # Extract all current text chunks and pauses from the buffer
                    # Using a more robust regex for JSON field extraction
                    field_extractor = re.compile(r'\{[^{}]*\"text\":\s*\"([^\"]+)\"[^{}]*\}', re.DOTALL)
                    pause_extractor = re.compile(r'\"pause_ms\":\s*(\d+)', re.DOTALL)
                    
                    found_matches = list(field_extractor.finditer(complete_response))
                    
                    if len(found_matches) > len(played_chunks):
                        for i in range(len(played_chunks), len(found_matches)):
                            match = found_matches[i]
                            chunk_text = match.group(1).replace('\\n', ' ').replace('\\"', '"').strip()
                            
                            # Try to find a pause_ms within this JSON object
                            obj_content = match.group(0)
                            pause_match = pause_extractor.search(obj_content)
                            pause_ms = int(pause_match.group(1)) if pause_match else 150
                            
                            if chunk_text:
                                logger.info(f"🔊 Streaming Chunk: '{chunk_text}' (pause: {pause_ms}ms)")
                                async for audio in TTSService.generate_speech_streaming(chunk_text, language=self.language, speaker=self.voice):
                                    if audio:
                                        await self.send_audio_safe(audio)
                                
                                # Add natural human-like pause between chunks
                                await asyncio.sleep(pause_ms / 1000.0)
                                played_chunks.append(chunk_text)

                # Final fallback check if JSON was empty or malformed
                if not played_chunks and complete_response.strip():
                    # If LLM didn't follow JSON, just play the raw text as fallback
                    plaintext = complete_response.strip()
                    # Clean up some common JSON artifacts if it looks like it started but failed
                    if plaintext.startswith('{'):
                         # Try to find any text between double quotes after "text":
                         match = re.search(r'\"text\":\s*\"([^\"]+)\"', plaintext)
                         if match: plaintext = match.group(1)
                         
                    async for audio in TTSService.generate_speech_streaming(plaintext, language=self.language, speaker=self.voice):
                        if audio:
                            await self.send_audio_safe(audio)
                        played_chunks.append(plaintext)

                # Store clean result for history
                valid_response = " ".join(played_chunks) if played_chunks else fallback_response(self.language)

            # Update State & Cache
            new_stage = compute_next_state(self.state, user_text, self.intent_memory, self.turn_count)
            self.state = new_stage
            self._session_cache["history"] = (history + [{"role": "assistant", "content": valid_response}])[-5:]
            self._full_transcript.append(f"Assistant: {valid_response}")
            await redis_client.save_session(self.call_sid, self._session_cache)
            
            # Persist full transcript to DB if call is nearing end or periodically
            asyncio.create_task(self._sync_transcript_to_db())
            
            # Final buffer flush
            await self.flush_audio_buffer()

        except asyncio.CancelledError:
            logger.info("Agent task cancelled.")
        except Exception as e:
            logger.error(f"Error in speaking task: {e}")
        finally:
            self._processing = False

    async def _sync_transcript_to_db(self):
        try:
            with SessionLocal() as db:
                call_log = db.query(CallLog).filter(CallLog.call_sid == self.call_sid).first()
                if call_log:
                    call_log.transcript = "\n".join(self._full_transcript)
                    db.commit()
        except Exception as e:
            logger.error(f"Transcript DB sync failed: {e}")

