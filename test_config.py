"""Quick test: verify config and model connectivity."""
import asyncio
from config import MIMO_API_KEY, GEMINI_API_KEY, NVIDIA_API_KEY, GROK_API_KEY

print("=== Cricket Trading System - Config Check ===")
print(f"MiMo API Key: {'SET' if MIMO_API_KEY else 'MISSING'}")
print(f"Gemini API Key: {'SET' if GEMINI_API_KEY else 'MISSING'}")
print(f"NVIDIA API Key: {'SET' if NVIDIA_API_KEY else 'MISSING'}")
print(f"Grok API Key: {'SET' if GROK_API_KEY else 'MISSING'}")

async def test_models():
    from ai_ensemble import call_mimo, call_gemini, call_nvidia, call_grok, SYSTEM_PROMPT
    
    test_prompt = "What is 2+2? Reply in JSON: {\"probability\": 0.5, \"confidence\": 0.9, \"reasoning\": \"math\", \"key_factors\": [\"math\"]}"
    
    results = {}
    
    if MIMO_API_KEY:
        print("\n--- Testing MiMo ---")
        r = await call_mimo(test_prompt)
        results['mimo'] = r
        print(f"  Result: {r}")
    
    if GEMINI_API_KEY:
        print("\n--- Testing Gemini ---")
        r = await call_gemini(test_prompt)
        results['gemini'] = r
        print(f"  Result: {r}")
    
    if NVIDIA_API_KEY:
        print("\n--- Testing NVIDIA ---")
        r = await call_nvidia(test_prompt)
        results['nvidia'] = r
        print(f"  Result: {r}")
    
    if GROK_API_KEY:
        print("\n--- Testing Grok ---")
        r = await call_grok(test_prompt)
        results['grok'] = r
        print(f"  Result: {r}")
    
    working = sum(1 for v in results.values() if v is not None)
    total = len(results)
    print(f"\n=== {working}/{total} models responding ===")
    return results

asyncio.run(test_models())