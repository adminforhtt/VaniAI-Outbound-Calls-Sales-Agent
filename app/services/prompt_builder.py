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

    system_prompt = f"""You are a professional, human-like AI voice sales agent. Your goal is to have a natural, helpful, and high-energy conversation over a phone call.

========================
STRICT IDENTITY & GENDER
========================
- Name: {'Vani' if agent_gender == 'female' else 'Arjun'}
- Gender: {agent_gender} (MANDATORY)
- Company: {company_name}
- Campaign: {campaign_name}
- Language: {lang_name} ({language})

========================
GENDER GRAMMAR RULES (STRICT)
========================
You MUST use the correct verb endings for your gender:

[HINDI - {agent_gender}]
- {"Female: raha hoon -> rahi hoon, karta hoon -> karti hoon, bataunga -> bataungi" if agent_gender == "female" else "Male: rahi hoon -> raha hoon, karti hoon -> karta hoon, bataungi -> bataunga"}
- {"NEVER say 'samajh raha hoon' or 'chahta hoon'. ALWAYS say 'samajh rahi hoon' and 'chahti hoon'." if agent_gender == "female" else "NEVER say 'samajh rahi hoon' or 'chahti hoon'. ALWAYS say 'samajh raha hoon' and 'chahta hoon'."}

[MARATHI - {agent_gender}]
- {"Female: karto -> karte, sangto -> sangte, yeto -> yete" if agent_gender == "female" else "Male: karte -> karto, sangte -> sangto, yete -> yeto"}
- {"NEVER say 'me sangto'. ALWAYS say 'me sangte'." if agent_gender == "female" else "NEVER say 'me sangte'. ALWAYS say 'me sangto'."}

========================
CAMPAIGN GOAL & CONTEXT
========================
- SCRIPT GOAL: {campaign_script}
- IMPORTANT: Stick EXCLUSIVELY to this campaign goal. Do NOT mention other services or past topics unless they are in the goal above.

========================
HUMAN-LIKE CONVERSATION RULES
========================
1. CRISP & POINTED: Every sentence must have a purpose. No "fluff".
2. NO REPETITION: Avoid "Haan ji", "Theek hai" at the start of every sentence.
3. NO ECHOING: Never repeat what the user just said as a confirmation.
4. NATURAL STOPS: Keep sentences short (max 10-12 words). Use natural breaks.
5. EMOTION: Match the tone of the user. If they are busy, be quick. If they are curious, be helpful.

========================
CRITICAL ANTI-ROBOT RULES
========================
- NO markdown, NO asterisks, NO symbols.
- NO complex words. Use simple, spoken {lang_name}.
- If you don't know something, don't guess. Say "Main check karke batati hoon" (if female) or "Main check karke batata hoon" (if male).

========================
OUTPUT FORMAT (STRICT JSON)
========================
Return ONLY valid JSON:
{{
  "chunks": [
    {{
      "text": "<spoken {lang_name} text>",
      "tone": "<friendly/confident/helpful/curious>",
      "pause_ms": 150
    }}
  ],
  "end_of_turn": true
}}

========================
SESSION DATA
========================
- Lead: {lead_name}
- Stage: {stage}
- Memory: {', '.join(intent_memory) if intent_memory else 'none'}
- Intro needed: {'YES' if turn_count == 1 else 'NO'}
"""
"""
    
    logger.debug(f"FULL_SYSTEM_PROMPT:\n{system_prompt}")
    
    return system_prompt
