from sqlalchemy.orm import Session
from app.config.database import SessionLocal, engine, Base
from app.models.core import Tenant, Campaign, Lead, CallLog, ScriptVersion
import datetime

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()
    try:
        # 1. Create a dummy tenant
        tenant = db.query(Tenant).filter(Tenant.id == 1).first()
        if not tenant:
            tenant = Tenant(id=1, name="Vani AI Admin", api_key="test_key_123")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # 2. Create a dummy campaign
        campaign = db.query(Campaign).filter(Campaign.id == 1).first()
        if not campaign:
            campaign = Campaign(
                id=1,
                tenant_id=1,
                name="SaaS Outreach Q1",
                script_template="Hello, this is Vani AI calling to talk about our new cloud solutions...",
                language="en-IN",
                llm_provider="groq",
                voice="priya"
            )
            db.add(campaign)
            db.commit()
            db.refresh(campaign)

        # 3. Create enriched leads
        leads_data = [
            {"name": "Alice Smith", "company": "TechCorp", "phone": "+919876543210"},
            {"name": "Bob Johnson", "company": "DevSolutions", "phone": "+919998887776"},
            {"name": "Charlie Brown", "company": "AI Innovators", "phone": "+919555444333"}
        ]
        
        for i, ld in enumerate(leads_data):
            lead = db.query(Lead).filter(Lead.phone == ld["phone"]).first()
            if not lead:
                lead = Lead(
                    tenant_id=1,
                    name=ld["name"],
                    company=ld["company"],
                    phone=ld["phone"],
                    campaign_id=1,
                    status="completed" if i == 0 else "pending",
                    enrichment_status="enriched" if i == 0 else "pending",
                    metadata_json={
                        "enrichment_status": "enriched" if i == 0 else "pending",
                        "icebreaker": f"Hi {ld['name']}, I saw that {ld['company']} just raised funding!" if i == 0 else None,
                        "description": f"{ld['company']} is a leading software firm." if i == 0 else None
                    }
                )
                db.add(lead)
                db.commit()
                db.refresh(lead)

                # Add a dummy call log for the completed lead
                if i == 0:
                    call = CallLog(
                        tenant_id=1,
                        lead_id=lead.id,
                        call_sid="CAtest123",
                        status="completed",
                        duration=45,
                        transcript="Agent: Hello Alice. User: Hi, who is this? Agent: I am calling from Vani AI.",
                        outcome="High Interest",
                        score={"interest_level": "High", "reasoning": "User asked for a follow-up meeting."}
                    )
                    db.add(call)
                    db.commit()

        # 4. Create script versions
        version = db.query(ScriptVersion).filter(ScriptVersion.campaign_id == 1, ScriptVersion.version == 1).first()
        if not version:
            version = ScriptVersion(
                campaign_id=1,
                version=1,
                script_content="Hello, this is the original script.",
                reasoning="Initial deployment.",
                performance_score=0.5
            )
            db.add(version)
            
            v2 = ScriptVersion(
                campaign_id=1,
                version=2,
                script_content="Hi! We noticed you use AI at your company...",
                reasoning="Hermes optimized the intro to be more engaging based on recent news.",
                performance_score=0.8
            )
            db.add(v2)
            db.commit()

        print("Seeding complete! Dashboard should now have data.")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
