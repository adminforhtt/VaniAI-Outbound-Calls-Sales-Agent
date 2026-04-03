import logging
from typing import List, Dict
from app.services.llm import LLMService

logger = logging.getLogger(__name__)

class CriticAgent:
    """
    Evaluates the drafted response for natural tone, low latency, and Hindi/Hinglish appropriateness.
    In an ultra-low latency system, this could be omitted or done asynchronously, but we include it for deliberation.
    """
    @staticmethod
    async def evaluate_and_refine(draft_response: str) -> str:
        # To save latency, if response is short, we might skip, but let's do a fast LLM call.
        system_prompt = """You are a dialogue critic for an Indian voice agent.
Review the draft response. Ensure it sounds extremely natural in spoken Hinglish (Hindi + English).
It must be short, polite, and persuasive. Avoid robotic or overly formal phrasing.
Return ONLY the revised response, without any commentary."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"DRAFT: {draft_response}"}
        ]
        
        refined = await LLMService.generate_response(messages, provider="openrouter", model="openai/gpt-4o-mini")
        return refined.strip()
