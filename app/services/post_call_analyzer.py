import json
import logging
import re
from typing import Dict, Any
from app.config.settings import settings
import httpx

logger = logging.getLogger(__name__)

def _call_llm_sync(prompt: str) -> str:
    """Synchronous LLM call using Groq or OpenRouter."""
    provider = "groq" if settings.GROQ_API_KEY else "openrouter"
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
        model = "llama-3.3-70b-versatile"
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        model = "meta-llama/llama-3.3-70b-instruct"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Post-call LLM failed: {e}")
        return ""

class PostCallAnalyzer:
    @staticmethod
    def analyze(transcript: str, lead_name: str = "Lead") -> Dict[str, Any]:
        """Analyzes transcript to determine interest and score."""
        if not transcript or len(transcript) < 20:
            return {
                "interest_level": "none",
                "score": 0,
                "objections": ["No conversation occurred"],
                "next_action": "Retry call later",
                "reasoning": "The call was too short or silent to analyze."
            }

        prompt = f\"\"\"Analyze the following sales call transcript between an AI Agent and {lead_name}.
Score the lead's interest on a scale of 0-100 and provide a structured JSON analysis.

Transcript:
{transcript}

Return ONLY a JSON object:
{{
  "interest_level": "high|medium|low|none",
  "score": integer (0-100),
  "objections": ["objection 1", "objection 2"],
  "next_action": "reccomended next step",
  "reasoning": "1-2 sentence summary of the call outcome"
}}
\"\"\"
        raw = _call_llm_sync(prompt)
        try:
            match = re.search(r'{{.*}}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.error(f"Failed to parse post-call JSON: {e}")
        
        return {
            "interest_level": "unknown",
            "score": 0,
            "objections": [],
            "next_action": "Manual review required",
            "reasoning": "Could not parse AI analysis."
        }
