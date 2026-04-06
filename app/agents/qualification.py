import logging
import json
from typing import Dict, Any
from app.services.llm import LLMService

logger = logging.getLogger(__name__)

class QualificationAgent:
    def __init__(self):
        self.system_prompt = """You are an expert sales analyst.
Given the transcript of a call between an AI agent and a customer, analyze the conversation and produce a structured JSON object.

Extract:
1. interest_level: "high", "medium", "low", or "none"
2. score: Integer 0-100 indicating likelihood of conversion
3. reasoning: 1-2 sentence explanation of the score
4. next_action: String (e.g. "Schedule Follow-up", "Send PDF", "Discard")
5. objections: List of strings (e.g. ["pricing", "not authorized", "already using competitor"])
6. summary: 1-2 sentence summary of the call

Return ONLY valid JSON in the exact format:
{
  "interest_level": "...",
  "score": 0,
  "reasoning": "...",
  "next_action": "...",
  "objections": [],
  "summary": "..."
}"""

    async def score_lead(self, transcript: str) -> Dict[str, Any]:
        if not transcript or len(transcript) < 20:
            return {
                "interest_level": "none",
                "score": 0,
                "reasoning": "Call was too short or silent to analyze.",
                "next_action": "No action",
                "objections": [],
                "summary": "Short/empty call"
            }

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Transcript:\n{transcript}"}
        ]
        
        # Use our standard LLM service which already handles Groq vs OpenRouter
        response = await LLMService.generate_response(messages)
        
        try:
            # Basic json cleanup
            clean_json = response.replace('```json', '').replace('```', '').strip()
            score_data = json.loads(clean_json)
            return score_data
        except Exception as e:
            logger.error(f"Failed to parse qualification score: {e}")
            return {
                "interest_level": "Unknown",
                "score": 0,
                "reasoning": f"Parsing failed: {str(e)}",
                "next_action": "Manual review",
                "objections": [],
                "summary": "Analysis technical error"
            }
