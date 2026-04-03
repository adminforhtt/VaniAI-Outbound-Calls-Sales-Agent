import logging
import re
from typing import Tuple, List, Dict

logger = logging.getLogger(__name__)

class LanguageDetector:
    """Fallback detector, mostly handled by campaign.language now"""
    @staticmethod
    def detect_and_lock(user_text: str, session: dict) -> str:
        if session.get("language"):
            return session["language"]
        return "hi-IN"

class PolicyEngine:
    @staticmethod
    def get_initial_state() -> str:
        return "GREETING"

    @staticmethod
    def detect_intent(text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["yes", "haan", "sure", "ok", "ho", "theek", "हाँ", "ठीक"]):
            return "agreed"
        if any(w in text_lower for w in ["no", "nahi", "not interested", "busy", "stop", "bad me", "नहीं"]):
            return "not_interested"
        if any(w in text_lower for w in ["what", "how", "kya", "kaise", "matlab", "bataiye", "batao", "कौन", "कितना", "कितनी"]):
            return "question"
        return "neutral"

    @staticmethod
    def extract_keywords(text: str) -> List[str]:
        words = [w for w in text.split() if w.lower() not in ["hai", "ho", "is", "the", "a", "an", "ke", "ki", "ka"]]
        return words[:3]  # keep only a few significant words

    @staticmethod
    def check_ambiguity(text: str, language_code: str, stage: str, intent_keywords: list) -> Tuple[bool, str]:
        text_words = len(text.split())
        ack_words = ["yes", "no", "ok", "of course", "sure", "definitely", "certainly",
                     "haan", "nahi", "hanji", "namaste", "ji", "theek", "theek hai",
                     "achha", "achhai", "acchi", "achhi", "sahi", "badhiya",
                     "dhanyavaad", "thanks", "thank you", "hello", "hi", "bolo", "batao",
                     "हेलो", "हलो", "नमस्ते", "हाँ", "नहीं", "अच्छा", "ठीक"]
        is_ack = any(w in text.lower() for w in ack_words)
        
        if text_words <= 2 and not is_ack:
            AMBIGUITY_FALLBACK = {
                "kn-IN": "ದಯವಿಟ್ಟು ಇನ್ನಷ್ಟು ವಿವರಿಸಬಹುದೇ?",
                "hi-IN": "कृपया थोड़ा और बताइए?",
                "ta-IN": "கொஞ்சம் விரிவாக சொல்ல முடியுமா?",
                "te-IN": "దయచేసి కొంచెం వివరించగలరా?",
                "mr-IN": "कृपया थोडं अधिक सांगाल का?",
                "bn-IN": "একটু বিস্তারিত বলবেন?",
            }
            fallback_resp = AMBIGUITY_FALLBACK.get(language_code, "Yes, could you please elaborate?")
            return True, fallback_resp
                
        return False, ""

    @staticmethod
    def get_system_prompt(stage: str, campaign_prompt: str, lang_name: str, agent_name: str, recent_history: List[dict], user_text: str, intent_keywords: list) -> str:
        identity = f"You are {agent_name}, a professional and empathetic consultant.\n"
        identity += f"Script Info: {campaign_prompt}\n"
        
        rules = f"""
CRITICAL RULES:
1. CRYSTAL CLEAR PROUNCIATION: Use simple words in {lang_name}. Avoid complex compound words that are hard for TTS to read.
2. SENTENCE STRUCTURE: Use short, complete sentences. End every thought with a full stop for clear audio intonation.
3. Warm & Friendly: Be exceptionally warm and polite. Show genuine empathy and sound like a kind human being.
4. Language Alignment: You MUST speak EXCLUSIVELY in the native script of {lang_name}. ABSOLUTELY NO ENGLISH OR HINGLISH allowed.
5. Context: Stick strictly to the Script Info provided. Do not hallucinate generic topics.
"""
        
        # Format history
        hist_str = ""
        for msg in recent_history:
            role = "User" if msg['role'] == "user" else "Agent"
            hist_str += f"{role}: {msg['content']}\n"
            
        return f"{identity}\n{rules}\nRecent Context:\n{hist_str}\nUser: {user_text}\n\nAgent ({lang_name}):"

    @staticmethod
    def generate_greeting_text(campaign_prompt: str, lang_name: str, agent_name: str) -> str:
        """
        Since we cannot run LLM reliably on the first Twilio 'start' event without blocking audio,
        we return a hardcoded greeting based on the language, or let the user provide one.
        We provide high-quality localized greetings so the first impression is perfect.
        """
        greetings = {
            "Hindi": f"नमस्ते! मैं {agent_name} बात कर रही हूँ। क्या मैं आपको हमारे नए ऑफर के बारे में बता सकती हूँ?",
            "English": f"Hello! This is {agent_name}. Can I take a minute to tell you about our new offer?",
            "Marathi": f"नमस्कार! मी {agent_name} बोलत आहे. मी तुम्हाला आमच्या नवीन ऑफरबद्दल सांगू शकते का?",
            "Kannada": f"ನಮಸ್ಕಾರ! ನಾನು {agent_name} ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ನಮ್ಮ ಹೊಸ ಆಫರ್ ಬಗ್ಗೆ ಹೇಳಬಹುದಾ?",
            "Tamil": f"வணக்கம்! நான் {agent_name} பேசுகிறேன். எங்கள் புதிய சலுகையைப் பற்றி சொல்லலாமா?",
            "Telugu": f"నమస్కారం! నేను {agent_name} మాట్లాడుతున్నాను. మా కొత్త ఆఫర్ గురించి చెప్పవచ్చా?",
            "Bengali": f"নমস্কার! আমি {agent_name} বলছি। আমি কি আমাদের নতুন অফার সম্পর্কে আপনাকে বলতে পারি?",
            "Gujarati": f"નમસ્તે! હું {agent_name} બોલી રહી છું. શું હું તમને અમારી નવી ઓફર વિશે જણાવી શકું?",
            "Malayalam": f"നമസ്കാരം! ഞാൻ {agent_name} ആണ് സംസാരിക്കുന്നത്. നമ്മുടെ പുതിയ ഓഫറിനെക്കുറിച്ച് പറയാമോ?",
            "Punjabi": f"ਸਤਿ ਸ਼੍ਰੀ ਅਕਾਲ! ਮੈਂ {agent_name} ਬੋਲ ਰਹੀ ਹਾਂ। ਕੀ ਮੈਂ ਤੁਹਾਨੂੰ ਸਾਡੇ ਨਵੇਂ ਆਫਰ ਬਾਰੇ ਦੱਸ ਸਕਦੀ ਹਾਂ?",
            "Odia": f"ନମସ୍କାର! ମୁଁ {agent_name} କହୁଛି. ଆମର ନୂଆ ଅଫର ବିଷୟରେ ମୁଁ କହିପାରିବି କି?"
        }
        return greetings.get(lang_name, greetings["Hindi"])

    @staticmethod
    def validate_response(raw_response: str, user_text: str) -> Tuple[bool, str]:
        # Don't fail the response unless it's completely empty. 
        # The prompt limit logic ensures it is short.
        if not raw_response.strip():
            return False, "Response was empty"
        return True, "Valid"

    @staticmethod
    def ensure_complete_sentence(text: str) -> str:
        text = text.strip()
        if not text:
            return text
        
        # Correctly identify if the script is Devanagari (Hindi/Marathi)
        is_devanagari = any("\u0900" <= c <= "\u097F" for c in text)
        
        terminals = [".", "?", "!", "।"]
        if not any(text.endswith(t) for t in terminals):
            # Apply script-correct terminal to avoid Sarvam intonation artifacts
            return text + "।" if is_devanagari else text + "."
        return text

    @staticmethod
    def advance_stage(stage: str, intent: str, user_text: str) -> str:
        if intent == "not_interested":
            return "CLOSING"
        elif stage == "GREETING":
            return "DISCOVERY"
        return stage
