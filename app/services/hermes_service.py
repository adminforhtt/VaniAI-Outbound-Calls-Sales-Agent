"""
Lead Enrichment Service (replaces the broken Hermes Agent dependency).

Uses the existing Groq/OpenRouter LLM to research a lead and generate:
  - Company summary
  - Personalized icebreaker
  - Pitch angle
  - Pain points

No external CLI agent required — just a structured LLM prompt.
"""

import asyncio
import json
import logging
from typing import Dict, Any
from app.config.settings import settings

logger = logging.getLogger(__name__)

# A sync-safe HTTP client for Celery tasks (not async context)
import httpx

def _call_llm_sync(prompt: str, provider: str = None) -> str:
    """Synchronous LLM call for use inside Celery workers."""
    # Prefer Groq; fall back to OpenRouter
    use_provider = provider or ("groq" if settings.GROQ_API_KEY else "openrouter")

    if use_provider == "groq" and settings.GROQ_API_KEY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        model = "llama-3.3-70b-versatile"
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        model = "meta-llama/llama-3.3-70b-instruct"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 600,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""


class LeadEnrichmentService:
    """
    Lightweight lead intelligence engine powered by your existing LLM.
    
    Replaces the heavy NousResearch Hermes CLI agent that was cloned into
    libs/hermes/ — which was never designed to be embedded in a web app.
    """

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    def research_lead(self, lead_id: int, lead_name: str, company: str) -> bool:
        """
        Uses Groq/OpenRouter to research a company, then saves the result
        directly into the Lead record via update_lead_research_handler.
        """
        prompt = f"""You are a B2B sales intelligence assistant. Research the company "{company}" 
and generate a structured JSON object to help a sales agent personalize their pitch.

Return ONLY a valid JSON object with these fields (no explanation, no markdown, just JSON):
{{
  "company_name": "Official company name",
  "summary": "2-3 sentence summary of what they do",
  "recent_activity": "Any recent news, product launches, or funding (or 'No specific news found')",
  "pain_points": ["pain point 1", "pain point 2", "pain point 3"],
  "icebreaker": "A natural 1-sentence personalized opening line referencing something specific about them",
  "pitch_angle": "The best angle to pitch our product/service based on their situation"
}}"""

        logger.info(f"LeadEnrichmentService: Researching lead {lead_id} ({company})...")
        
        try:
            raw = _call_llm_sync(prompt)
            if not raw:
                logger.warning(f"Empty LLM response for lead {lead_id}")
                return False

            # Extract JSON from the response (handle any markdown wrapping)
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                logger.error(f"No JSON found in LLM response for lead {lead_id}: {raw[:200]}")
                return False

            data = json.loads(json_match.group())

            # Save to database via the existing handler
            from app.agents.hermes_tools import save_lead_research
            save_lead_research(lead_id=lead_id, data=data)

            logger.info(f"LeadEnrichmentService: Lead {lead_id} enriched successfully")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for lead {lead_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Enrichment failed for lead {lead_id}: {e}")
            return False

    def evolve_campaign(self, campaign_id: int, transcripts_summary: str) -> bool:
        """
        Analyzes recent call transcripts and rewrites the campaign script
        to address common objections and improve conversion.
        """
        prompt = f"""You are a sales script optimization expert. Analyze the following call transcripts 
and rewrite the campaign script to improve conversions.

Call Transcripts Summary:
{transcripts_summary[:3000]}

Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "new_script": "The full rewritten campaign script template",
  "reasoning": "Brief explanation of what was changed and why"
}}"""

        logger.info(f"LeadEnrichmentService: Evolving campaign {campaign_id}...")
        
        try:
            raw = _call_llm_sync(prompt)
            if not raw:
                return False

            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                logger.error(f"No JSON found in evolution response: {raw[:200]}")
                return False

            data = json.loads(json_match.group())
            new_script = data.get("new_script", "")
            reasoning = data.get("reasoning", "Evolved based on transcript analysis.")

            if not new_script:
                return False

            from app.agents.hermes_tools import save_campaign_script
            save_campaign_script(campaign_id=campaign_id, new_script=new_script, reasoning=reasoning)
            
            logger.info(f"LeadEnrichmentService: Campaign {campaign_id} script evolved")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse evolution JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Script evolution failed: {e}")
            return False


# Backwards-compatible alias so existing code using HermesOrchestrator still works
HermesOrchestrator = LeadEnrichmentService
