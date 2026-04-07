"""
Prompt Builder: Constructs the final system prompt for live calls by merging campaign context.

This module is the single source of truth for how the AI agent's personality,
instructions, and contextual knowledge are assembled before every turn.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)
# Map BCP-47 codes to human-readable language names
LANGUAGE_NAMES = {
    "hi-IN": "Hindi", "en-IN": "English", "bn-IN": "Bengali",
    "ta-IN": "Tamil", "te-IN": "Telugu", "mr-IN": "Marathi",
    "gu-IN": "Gujarati", "kn-IN": "Kannada", "ml-IN": "Malayalam",
    "pa-IN": "Punjabi", "or-IN": "Odia",
}

FEMALE_VOICES = {
    "priya", "anushka", "manisha", "vidya", "arya", "ritu", "neha",
    "pooja", "simran", "kavya", "ishita", "shreya", "roopa", "tanya",
    "shruti", "suhani", "kavitha", "rupali", "female"
}

def fallback_response(language: str) -> str:
    """Returns a safe fallback response in the requested language."""
    fallbacks = {
        "hi-IN": "माफ़ कीजिए, मुझे ठीक से समझ नहीं आया। क्या आप दोहरा सकते हैं?",
        "en-IN": "Sorry, I didn't catch that clearly. Could you please repeat?",
        "mr-IN": "माफ करा, मला नीट समजले नाही. कृपया पुन्हा सांगू शकाल का?",
        "ta-IN": "மன்னிக்கவும், எனக்கு சரியாக புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
        "te-IN": "క్షమించండి, నాకు సరిగా అర్థం కాలేదు. మళ్ళీ చెప్పగలరా?",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಸರಿಯಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಪುನರಾವರ್ತಿಸುವಿರಾ?",
        "bn-IN": "দুঃখিত, আমি ঠিক বুঝতে পারিনি। আপনি কি আবার বলতে পারবেন?",
        "gu-IN": "માફ કરજો, મને બરાબર સમજાયું નહીં. શું તમે ફરીથી કહી શકશો?",
        "ml-IN": "ക്ഷമിക്കണം, എനിക്ക് കൃത്യമായി മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?",
        "pa-IN": "ਮੁਆਫ ਕਰਨਾ, ਮੈਨੂੰ ਠੀਕ ਤਰ੍ਹਾਂ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਕੀ ਤੁਸੀਂ ਦੁਹਰਾ ਸਕਦੇ ਹੋ?",
        "or-IN": "କ୍ଷମା କରିବେ, ମୁଁ ଠିକରେ ବୁଝିପାରିଲି ନାହିଁ । ଦୟାକରି ଆଉଥରେ କହିବେ କି?"
    }
    return fallbacks.get(language, fallbacks["hi-IN"])

def detect_language_mismatch(text: str, expected_lang: str) -> bool:
    """
    Lightweight heuristic to ensure LLM doesn't hallucinate wrong script.
    Checks if an Indic language is missing its native script, or if English contains Indic script.
    """
    has_indic = bool(re.search(r'[\u0900-\u0DFF]', text))
    
    if expected_lang.startswith("en"):
        return has_indic  # Match fails if English contains Indic characters
    else:
        # Match fails if Indic language response has NO Indic characters (and is purely English letters)
        has_latin = bool(re.search(r'[a-zA-Z]', text))
        if not has_indic and has_latin and len(text.strip()) > 5:
            return True
            
    return False

def build_call_prompt(
    campaign_script: str,
    language: str,
    voice: str,
    company_name: str,
    campaign_name: str,
    lead_name: str,
    lead_phone: str,
    stage: str,
    intent_memory: List[str],
    turn_count: int,
) -> str:
    """
    Builds the complete system prompt for a live call turn.
    
    This is the ONLY place where the system prompt is constructed.
    It merges the campaign goal with lead intelligence and
    conversation state into one coherent instruction set.
    """
    agent_gender = "female" if voice in FEMALE_VOICES else "male"
    lang_name = LANGUAGE_NAMES.get(language, "Hindi")
    
    # First turn introduction instruction
    introduction = ""
    if turn_count == 1:
        introduction = f"Hi, I am {'Vani' if agent_gender == 'female' else 'Arjun'} calling from {company_name} regarding {campaign_name}."

    system_prompt = f"""You are a real-time AI voice sales agent designed for natural, human-like conversations over phone calls.

========================
CORE IDENTITY
========================
- Agent Name: {'Vani' if agent_gender == 'female' else 'Arjun'}
- Agent Gender: {agent_gender} (MANDATORY)
- Conversation Language: {lang_name} ({language})
- Company: {company_name}
- Campaign: {campaign_name}
- Persona: Friendly, confident, helpful, human-like (NOT robotic)
- Goal: {campaign_script}

========================
GENDER CONSISTENCY (STRICT)
========================
You MUST use the correct verb endings for your gender ({agent_gender}).
[HINDI]: {"Female: raha hoon -> rahi hoon, karta hoon -> karti hoon" if agent_gender == "female" else "Male: rahi hoon -> raha hoon, karti hoon -> karta hoon"}
[MARATHI]: {"Female: karto -> karte, sangto -> sangte" if agent_gender == "female" else "Male: karte -> karto, sangte -> sangto"}
NEVER mix genders. If you are {agent_gender}, use {agent_gender} grammar ONLY.

========================
CRITICAL RULES (NON-NEGOTIABLE)
========================

1. LANGUAGE LOCK
- Speak ONLY in {lang_name} ({language}). Always use native script.
- Do NOT switch languages unless explicitly requested.

2. NO REPETITION / NO ECHO
- NEVER repeat the user's question or rephrase it as an answer.

3. HUMAN-LIKE DELIVERY
- Keep responses SHORT (1–2 sentences).
- Use natural spoken language. Use conversational tone:
  ✅ "{'Haan, main batati hoon...' if agent_gender == 'female' else 'Samajh gaya, main batata hoon...'}"

4. OUTPUT FORMAT (STRICT JSON)
Return ONLY valid JSON:
{{
  "chunks": [
    {{
      "text": "<spoken {lang_name} sentence>",
      "tone": "<friendly/confident/helpful/curious>",
      "pause_ms": 150
    }}
  ],
  "end_of_turn": true
}}

========================
SESSION DATA
========================
- User: {lead_name}
- Stage: {stage}
- Memory: {', '.join(intent_memory) if intent_memory else 'none'}
- Intro Needed: {'YES' if turn_count == 1 else 'NO'}

========================
GOAL
========================
Sound like a REAL HUMAN on a phone call. Be quick, clear, and emotionally appropriate.
"""
    
    logger.debug(f"FULL_SYSTEM_PROMPT:\n{system_prompt}")
    
    return system_prompt
