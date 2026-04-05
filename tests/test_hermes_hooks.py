from app.agents.hermes_tools import save_lead_research, save_campaign_script

def test_hooks_importable():
    assert callable(save_lead_research)
    assert callable(save_campaign_script)
