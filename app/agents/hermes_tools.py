import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.models.core import Lead, Campaign, ScriptVersion
from libs.hermes.tools.registry import registry

logger = logging.getLogger(__name__)

def update_lead_research_handler(args: Dict[str, Any], **kwargs) -> str:
    """
    Update a lead with structured enrichment data found by the Hermes agent.
    Saves a rich JSON object into lead.metadata_json and flips enrichment_status.
    """
    lead_id = args.get("lead_id")
    
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return json.dumps({"error": f"Lead {lead_id} not found"})
        
        meta = lead.metadata_json or {}
        
        # Store structured intelligence fields
        meta["company_name"] = args.get("company_name", "")
        meta["summary"] = args.get("summary") or args.get("research_summary", "")
        meta["recent_activity"] = args.get("recent_activity", "")
        meta["pain_points"] = args.get("pain_points", [])
        meta["icebreaker"] = args.get("icebreaker", "")
        meta["pitch_angle"] = args.get("pitch_angle", "")
        
        # Legacy compat: keep description for dashboard views
        meta["description"] = meta["summary"]
        meta["enrichment_status"] = "enriched"
        
        lead.metadata_json = meta
        lead.enrichment_status = "enriched"
        
        from sqlalchemy.sql import func
        lead.enriched_at = func.now()
        
        db.commit()
        logger.info(f"HERMES_SAVE: Lead {lead_id} enriched with structured data ({len(json.dumps(meta))} bytes)")
        return json.dumps({"status": "success", "message": f"Lead {lead_id} updated with structured research."})
    except Exception as e:
        db.rollback()
        logger.error(f"HERMES_SAVE_FAILED: Lead {lead_id}: {e}")
        return json.dumps({"error": str(e)})
    finally:
        db.close()

def update_campaign_script_handler(args: Dict[str, Any], **kwargs) -> str:
    """
    Updates the campaign script with a new version based on agent's analysis.
    """
    campaign_id = args.get("campaign_id")
    new_script = args.get("new_script")
    reasoning = args.get("reasoning")
    
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            return json.dumps({"error": f"Campaign {campaign_id} not found"})
        
        # 1. Update Campaign script
        campaign.script_template = new_script
        
        # 2. Add to ScriptVersion history
        new_version = db.query(ScriptVersion).filter(ScriptVersion.campaign_id == campaign_id).count() + 1
        history = ScriptVersion(
            campaign_id=campaign_id,
            version=new_version,
            script_content=new_script,
            reasoning=reasoning,
            performance_score=0.0 # Default
        )
        db.add(history)
        db.commit()
        return json.dumps({"status": "success", "version": new_version})
    except Exception as e:
        db.rollback()
        return json.dumps({"error": str(e)})
    finally:
        db.close()

# Register the tools with Hermes Registry
registry.register(
    name="update_lead_research",
    toolset="vania_tools",
    schema={
        "name": "update_lead_research",
        "description": "Save structured research results for a specific lead into the database. You MUST provide all fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer", "description": "The internal ID of the lead to update."},
                "company_name": {"type": "string", "description": "The official company or business name."},
                "summary": {"type": "string", "description": "2-3 sentence summary of what the company does."},
                "recent_activity": {"type": "string", "description": "Any recent news, product launches, or events."},
                "pain_points": {"type": "array", "items": {"type": "string"}, "description": "List of 2-3 business challenges or needs the company might have."},
                "icebreaker": {"type": "string", "description": "A short, 1-sentence personalized opening line referencing something specific about them."},
                "pitch_angle": {"type": "string", "description": "The best angle to pitch our product/service based on their situation."}
            },
            "required": ["lead_id", "company_name", "summary", "icebreaker"]
        }
    },
    handler=update_lead_research_handler
)

registry.register(
    name="update_campaign_script",
    toolset="vania_tools",
    schema={
        "name": "update_campaign_script",
        "description": "Updates a campaign's main script template and records a version history with reasoning.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "The ID of the campaign to optimize."},
                "new_script": {"type": "string", "description": "The full body of the new optimized script template."},
                "reasoning": {"type": "string", "description": "Explanation of why the script was modified."}
            },
            "required": ["campaign_id", "new_script", "reasoning"]
        }
    },
    handler=update_campaign_script_handler
)
