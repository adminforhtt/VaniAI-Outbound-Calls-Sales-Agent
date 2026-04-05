"""
Hermes Tools — database save helpers for lead enrichment and campaign script evolution.

These are standalone functions (no external agent framework dependency).
They are called directly by LeadEnrichmentService.
"""

import json
import logging
from typing import Dict, Any
from sqlalchemy.sql import func
from app.config.database import SessionLocal
from app.models.core import Lead, Campaign, ScriptVersion

logger = logging.getLogger(__name__)


def save_lead_research(lead_id: int, data: Dict[str, Any]) -> bool:
    """
    Saves structured enrichment data to a Lead record.
    
    Args:
        lead_id: The Lead.id to update
        data: Dict with keys: company_name, summary, recent_activity, pain_points, icebreaker, pitch_angle
    
    Returns:
        True on success, False on failure
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.error(f"save_lead_research: Lead {lead_id} not found")
            return False

        meta = lead.metadata_json or {}

        meta["company_name"] = data.get("company_name", "")
        meta["summary"] = data.get("summary", "")
        # Legacy compat
        meta["description"] = meta["summary"]
        meta["recent_activity"] = data.get("recent_activity", "")
        meta["recent_news"] = meta["recent_activity"]  # for HermesConsole display
        meta["pain_points"] = data.get("pain_points", [])
        meta["icebreaker"] = data.get("icebreaker", "")
        meta["pitch_angle"] = data.get("pitch_angle", "")
        meta["enrichment_status"] = "enriched"

        lead.metadata_json = meta
        lead.enrichment_status = "enriched"
        lead.enriched_at = func.now()

        db.commit()
        logger.info(f"save_lead_research: Lead {lead_id} enriched successfully ({len(json.dumps(meta))} bytes)")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"save_lead_research: Failed for lead {lead_id}: {e}")
        return False
    finally:
        db.close()


def save_campaign_script(campaign_id: int, new_script: str, reasoning: str) -> bool:
    """
    Updates a campaign's script template and adds a version history entry.
    
    Args:
        campaign_id: The Campaign.id to update
        new_script: The new script content
        reasoning: Why the script was changed
    
    Returns:
        True on success, False on failure
    """
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"save_campaign_script: Campaign {campaign_id} not found")
            return False

        # Update the campaign's main script
        campaign.script_template = new_script

        # Record version history
        new_version_num = db.query(ScriptVersion).filter(
            ScriptVersion.campaign_id == campaign_id
        ).count() + 1

        version_entry = ScriptVersion(
            campaign_id=campaign_id,
            version=new_version_num,
            script_content=new_script,
            reasoning=reasoning,
            performance_score=0.0,
        )
        db.add(version_entry)
        db.commit()

        logger.info(f"save_campaign_script: Campaign {campaign_id} updated to version {new_version_num}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"save_campaign_script: Failed for campaign {campaign_id}: {e}")
        return False
    finally:
        db.close()


# ─── Legacy handler aliases (kept for API compatibility) ──────────────────────

def update_lead_research_handler(args: Dict[str, Any], **kwargs) -> str:
    """Legacy wrapper kept for API compatibility."""
    lead_id = args.get("lead_id")
    if not lead_id:
        return json.dumps({"error": "lead_id is required"})
    
    success = save_lead_research(lead_id=lead_id, data=args)
    if success:
        return json.dumps({"status": "success", "message": f"Lead {lead_id} updated."})
    return json.dumps({"error": f"Failed to update lead {lead_id}"})


def update_campaign_script_handler(args: Dict[str, Any], **kwargs) -> str:
    """Legacy wrapper kept for API compatibility."""
    campaign_id = args.get("campaign_id")
    new_script = args.get("new_script", "")
    reasoning = args.get("reasoning", "Evolved by agent.")
    
    if not campaign_id or not new_script:
        return json.dumps({"error": "campaign_id and new_script are required"})
    
    success = save_campaign_script(
        campaign_id=campaign_id,
        new_script=new_script,
        reasoning=reasoning,
    )
    if success:
        return json.dumps({"status": "success"})
    return json.dumps({"error": f"Failed to update campaign {campaign_id}"})
