import os
import sys
import logging
from typing import Dict, Any, Optional

# Add the libs/hermes directory to the Python path for imports to work
HERMES_PATH = os.path.join(os.getcwd(), "libs", "hermes")
if HERMES_PATH not in sys.path:
    sys.path.append(HERMES_PATH)

# Import the AIAgent and tools registry from the Nous Research framework
from run_agent import AIAgent
from model_tools import registry
from app.config.settings import settings

# Import our custom tools to ensure they are registered
import app.agents.hermes_tools

logger = logging.getLogger(__name__)

class HermesOrchestrator:
    """
    Orchestrates the Nous Research Hermes Agent to perform Vani AI tasks.
    It uses Browserbase + OpenRouter (Free Qwen) to fulfill requests.
    """
    
    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.model = settings.HERMES_MODEL or "qwen/qwen-2.5-72b-instruct:free"
        
        # Inject Browserbase and OpenRouter credentials into environment for Hermes
        os.environ["BROWSERBASE_API_KEY"] = settings.BROWSERBASE_API_KEY or ""
        os.environ["BROWSERBASE_PROJECT_ID"] = settings.BROWSERBASE_PROJECT_ID or ""
        os.environ["OPENROUTER_API_KEY"] = settings.OPENROUTER_API_KEY or ""
        
        # Initialize the AIAgent with native Nous Research configuration
        self.agent = AIAgent(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            model=self.model,
            max_iterations=10, # Keep it tight for performance
            enabled_toolsets=["vania_tools", "browser_tools", "web_tools"], # Use our tools plus built-in browsing
            quiet_mode=True
        )

    def research_lead(self, lead_id: int, lead_name: str, company: str) -> bool:
        """
        Uses Hermes to research a company and update lead metadata with structured intelligence.
        """
        prompt = f"""
        Task: Research the company "{company}" for lead "{lead_name}" (ID: {lead_id}).
        
        Steps:
        1. Use the browser to find their website and recent news.
        2. Identify what they do, any recent launches or initiatives.
        3. Identify 2-3 potential pain points or business challenges they might have.
        4. Create a short personalized icebreaker referencing something specific about them.
        5. Suggest the best pitch angle for our product based on their situation.
        
        IMPORTANT: Use the 'update_lead_research' tool to save the results with ALL these fields:
        - company_name: The official company name
        - summary: 2-3 sentence summary of what they do
        - recent_activity: Any recent news, product launches, or events
        - pain_points: List of 2-3 business challenges they might face
        - icebreaker: A personalized 1-sentence opening line
        - pitch_angle: The best angle to pitch our service
        """
        try:
            logger.info(f"Hermes starting structured research for lead {lead_id} ({company})...")
            self.agent.run_conversation(prompt)
            return True
        except Exception as e:
            logger.error(f"Hermes research failed: {e}")
            return False

    def evolve_campaign(self, campaign_id: int, transcripts_summary: str) -> bool:
        """
        Uses Hermes to analyze transcripts and optimize the script.
        """
        prompt = f"""
        Campaign ID: {campaign_id}
        User Hang-up Reasons / Feedback Summary:
        {transcripts_summary}
        
        Task:
        1. Analyze why users are hanging up.
        2. Rewrite the campaign script to address these objections (e.g. move price later, highlight benefits sooner).
        3. Use the 'update_campaign_script' tool to deploy version version.
        4. Be concise and professional in reasoning.
        """
        try:
            logger.info(f"Hermes starting script evolution for Campaign {campaign_id}...")
            self.agent.run_conversation(prompt)
            return True
        except Exception as e:
            logger.error(f"Hermes evolution failed: {e}")
            return False
