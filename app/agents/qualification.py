import logging
import json
from typing import Dict, Any
from app.services.llm import LLMService

logger = logging.getLogger(__name__)

class QualificationAgent:
    def __init__(self):
        self.system_prompt = """You are an expert sales analyst.
Given the transcript of a call between an AI agent and a customer, you need to extract the following information:
1. interest_level: String (High, Medium, Low, Not Interested)
2. intent: String (Summary of what the customer wants to do)
3. next_action: String (Follow up call, Email, Discard, etc.)
4. summary: String (Brief 2 sentence summary of the call)

Return ONLY valid JSON in the exact format:
{
  "interest_level": "...",
  "intent": "...",
  "next_action": "...",
  "summary": "..."
}"""

    async def score_lead(self, transcript: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Transcript:\n{transcript}"}
        ]
        response = await LLMService.generate_response(messages, provider="openrouter", model="openai/gpt-4o-mini")
        
        try:
            # Basic json cleanup
            clean_json = response.replace('```json', '').replace('```', '').strip()
            score_data = json.loads(clean_json)
            return score_data
        except Exception as e:
            logger.error(f"Failed to parse qualification score: {e}")
            return {
                "interest_level": "Unknown",
                "intent": "Could not parse",
                "next_action": "Manual review",
                "summary": "Parsing error from LLM"
            }
