import logging
from typing import List, Dict, Tuple
from app.services.llm import LLMService

logger = logging.getLogger(__name__)

class StrategyAgent:
    """
    Decides the next conversational move based on history and current state.
    """
    @staticmethod
    async def decide_next_move(history: List[Dict[str, str]], current_state: str) -> Tuple[str, str]:
        system_prompt = f"""You are an expert sales strategist.
Current conversation state: {current_state}
Valid states: INIT, GREETING, DISCOVERY, PITCH, OBJECTION_HANDLING, CLOSING, END
Based on the conversation history, decide:
1. The NEXT_STATE of the conversation.
2. The STRATEGY for the agent's next turn (e.g., 'push sale', 'ask open question', 'handle objection gracefully').

Return ONLY in this format:
STATE: <next_state>
STRATEGY: <strategy text>"""

        messages = [{"role": "system", "content": system_prompt}]
        # Pass a summarized or truncated history to save tokens
        recent_history = history[-4:] if len(history) > 4 else history
        messages.extend(recent_history)
        
        # We can run this async
        response = await LLMService.generate_response(messages, provider="openrouter", model="openai/gpt-4o-mini")
        
        next_state = current_state
        strategy = "respond naturally"
        
        try:
            for line in response.split('\n'):
                if line.startswith("STATE:"):
                    next_state = line.split("STATE:")[1].strip()
                elif line.startswith("STRATEGY:"):
                    strategy = line.split("STRATEGY:")[1].strip()
        except Exception as e:
            logger.error(f"Failed to parse strategy output: {e}")
            
        return next_state, strategy
