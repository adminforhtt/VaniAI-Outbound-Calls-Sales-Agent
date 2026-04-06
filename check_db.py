from app.config.database import SessionLocal
from app.models.core import CallLog, Lead, Campaign
import json

with SessionLocal() as db:
    call = db.query(CallLog).order_by(CallLog.id.desc()).first()
    if not call:
        print("No calls found in DB.")
    else:
        print(f"Latest Call SID: {call.call_sid}")
        lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
        if not lead:
            print(f"Lead ID {call.lead_id} NOT FOUND.")
        else:
            print(f"Lead Name: {lead.name}, Campaign ID: {lead.campaign_id}")
            if lead.campaign_id:
                campaign = db.query(Campaign).filter(Campaign.id == lead.campaign_id).first()
                if campaign:
                    print(f"Campaign Name: {campaign.name}")
                    print(f"Campaign Script Start: {campaign.script_template[:100]}...")
                else:
                    print(f"Campaign ID {lead.campaign_id} NOT FOUND.")

