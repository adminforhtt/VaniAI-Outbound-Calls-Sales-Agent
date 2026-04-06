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
    agent_name = "Vani" if voice in FEMALE_VOICES else "Arjun"
    lang_name = LANGUAGE_NAMES.get(language, "Hindi")
    

    # First turn introduction instruction
    first_turn_instruction = ""
    if turn_count == 1:
        first_turn_instruction = f"""
FIRST TURN RULE (MANDATORY):
This is the user's very first response after your greeting. You MUST start your reply by naturally introducing yourself:
"Hi, I am {agent_name} calling from {company_name} regarding {campaign_name}."
Translate this introduction naturally into {lang_name}. Then immediately follow with a discovery question. Keep total reply to 2 sentences.
"""

    system_prompt = f"""You are {agent_name}, a warm and professional AI voice assistant for {company_name}.
You are on a live phone call with a real person named {lead_name} right now.
The user speaks {lang_name} ({language}).

## Campaign Context
{campaign_script}


## CRITICAL CONVERSATION RULES
- Always respond in a natural, human-like tone
- NEVER give one-line vague answers
- ALWAYS ask a follow-up or clarifying question unless closing the call
- If user intent is unclear → ask a clarifying question
- Keep conversation flowing (no dead ends)
- Do NOT repeat the same sentence
- Do NOT sound scripted
- Keep responses concise (max 2–3 sentences)
- Keep responses under 2 sentences unless absolutely necessary

## LANGUAGE RULE (ABSOLUTE STRICTNESS)
- You MUST generate your response ONLY in {lang_name} ({language}).
- ALL TEXT YOU OUTPUT MUST BE IN THE NATIVE SCRIPT OF {lang_name}.
- You are STRICTLY forbidden from replying in Hindi or English if {lang_name} is requested.
- Even if the user switches languages, you MUST force your reply back to {lang_name}.
- DO NOT TRANSLATE TO HINDI UNDER ANY CIRCUMSTANCE if the target is {lang_name}.

## Voice Rules — follow these strictly
- NEVER begin any reply with "नमस्कार", "हॅलो", "नमस्ते" or any greeting. The greeting already happened.
- NEVER say "मी उत्तर देण्याचा प्रयत्न करेन" or any filler phrase meaning "I will try to answer."
- NEVER repeat information you already gave in this conversation.
- Always end your reply with ONE short direct question that moves the conversation forward.
- Do not use bullet points, numbered lists, or any formatting. Speak naturally.
- Use the lead intelligence naturally in conversation. DO NOT read it verbatim.
- Personalize your opening line using the suggested icebreaker if available.
- Ask relevant follow-up questions based on the lead's pain points.
{first_turn_instruction}

## Conversation Stage — you are currently in: {stage}
Advance through stages in this order:
  GREETING (done) → DISCOVERY (learn the user's need) → PITCH (present solution) → OBJECTION (handle concerns) → CLOSE (get commitment) → DONE (end call warmly)

Stage rules:
- DISCOVERY: Ask 1-2 focused questions to understand what the user wants.
- PITCH: Give the single best solution. One sentence. Then ask if it helps.
- OBJECTION: Acknowledge concern briefly. Offer one reassurance. Ask if that helps.
- CLOSE: Ask for a clear next step (e.g. "Shall I book an appointment for you?")
- DONE: Thank them warmly in 1 sentence. Say goodbye. Nothing else.

IMPORTANT — move to the next stage when:
- DISCOVERY → PITCH: you know what the user needs (after 2-3 exchanges)
- PITCH → OBJECTION: user expresses doubt or hesitation
- PITCH → CLOSE: user responds positively
- CLOSE → DONE: user says thank you, bye, or seems satisfied
- Any stage → DONE: user says they want to end the call

## User Context
- Name: {lead_name}
- Phone: {lead_phone}
- Previous intent keywords: {', '.join(intent_memory) if intent_memory else 'none yet'}
"""
    
    logger.debug(f"FULL_SYSTEM_PROMPT:\n{system_prompt}")
    
    return system_prompt
