import logging
from typing import List, Dict
from app.services.llm import LLMService
from app.agents.strategy import StrategyAgent
from app.agents.critic import CriticAgent

logger = logging.getLogger(__name__)

class ConversationAgent:
    def __init__(self, language: str = "hi-IN", goal: str = "qualify the lead"):
        self.language = language
        self.goal = goal

    def get_dynamic_prompt(self, state: str, strategy: str) -> str:
        return f"""You are a polite, natural-sounding Indian sales agent.
Language/Tone preference: {self.language} (Use Hinglish where natural).
Your overall goal is to {self.goal}.
Current State: {state}
Current Strategy: {strategy}

CAMPAIGN SCRIPT / KNOWLEDGE:
{getattr(self, 'script', 'No specific script provided. Improvise polite conversation.')}

CRITICAL RULES:
- Keep it extremely conversational. Max 1-2 short sentences.
- DO NOT sound like an AI. Use conversational fillers (e.g., 'haan', 'achha') if making sense.
- Stick to the strategy. If strategy says ask a question, end with a question."""

    async def generate_reply(self, history: List[Dict[str, str]], latest_utterance: str, state: str) -> tuple[str, str]:
        # 1. Strategy Agent decides next move (runs in parallel or sequentially based on optimizations)
        # For lower latency, this could happen asynchronously while user speaks, but we'll do sequential here.
        next_state, strategy = await StrategyAgent.decide_next_move(history, state)
        logger.info(f"Deliberation - Next State: {next_state}, Strategy: {strategy}")

        # 2. Conversation Agent drafts response
        system_prompt = self.get_dynamic_prompt(next_state, strategy)
        messages = [{"role": "system", "content": system_prompt}]
        
        # Pass only last 10 messages for memory optimization
        recent_history = history[-10:] if len(history) > 10 else history
        messages.extend(recent_history)
        messages.append({"role": "user", "content": latest_utterance})
        
        draft_reply = await LLMService.generate_response(messages, provider="openrouter")
        
        # 3. Critic Agent refines response
        final_reply = await CriticAgent.evaluate_and_refine(draft_reply)
        logger.info(f"Deliberation - Final Reply: {final_reply}")
        
        return final_reply, next_state
