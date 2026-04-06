import asyncio
import logging
import json
import os
import httpx
from app.agents.qualification import QualificationAgent
from app.services.llm import LLMService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_post_call_analysis():
    print("\n--- TEST 1: REALISTIC SALES TRANSCRIPT ---")
    mock_transcript = """User: Hello?
Assistant: नमस्कार, मी वानी एआय मधून बोलतेय. तुम्हाला गृहकर्जाबद्दल माहिती हवी होती का?
User: हो, खरं तर मला नवीन फ्लॅटसाठी लोन पाहिजे होतं. रेट काय आहेत?
Assistant: नक्कीच! आमचे व्याजदर ८.५ टक्क्यांपासून सुरू होतात. तुम्हाला किती रकमेचे कर्ज हवे आहे?
User: मला साधारण ५० लाखांपर्यंत कर्ज हवंय, पण कागदपत्रे काय लागतील?
Assistant: ५० लाखांसाठी तुम्हाला पॅन कार्ड, आधार कार्ड आणि गेल्या ३ महिन्यांचे पगार स्लिप लागतील. मी तुम्हाला उद्या फोन करू का अधिक माहितीसाठी?
User: ठीक आहे, उद्या दुपारी करा. धन्यवाद.
Assistant: धन्यवाद, शुभ दिवस!"""

    agent = QualificationAgent()
    print("Sending transcript to QualificationAgent (LLM)...")
    result = await agent.score_lead(mock_transcript)
    
    print("\n[Hermes Intelligence Result]:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Assertions
    assert "score" in result, "Missing 'score' field"
    assert "interest_level" in result, "Missing 'interest_level' field"
    assert "reasoning" in result, "Missing 'reasoning' field"
    assert "next_action" in result, "Missing 'next_action' field"
    print("\n✅ TEST 1 PASSED: Comprehensive JSON returned with reasoning and score.")

async def test_short_call_fallback():
    print("\n--- TEST 2: SHORT CALL FALLBACK ---")
    # Transcript is exactly 21 chars, should trigger the fallback branch (if < 20) or LLM (if >= 20)
    # Let's use 10 chars to be safe for fallback trigger
    short_transcript = "User: Hi." 
    
    agent = QualificationAgent()
    result = await agent.score_lead(short_transcript)
    
    print("[Fallback Result]:")
    print(json.dumps(result, indent=2))
    assert result["interest_level"] == "none", f"Expected interest 'none', got '{result['interest_level']}'"
    print("✅ TEST 2 PASSED: Short call correctly handled by fallback logic.")

async def run_tests():
    try:
        await test_post_call_analysis()
        await test_short_call_fallback()
    finally:
        # Cleanly close the persistent client used in LLMService
        from app.services.llm import _http_client
        await _http_client.aclose()

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY") and not os.getenv("OPENROUTER_API_KEY"):
        print("❌ ERROR: No LLM API key found in environment!")
    else:
        asyncio.run(run_tests())
