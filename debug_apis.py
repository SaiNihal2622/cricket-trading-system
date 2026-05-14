"""Debug API responses to fix parsing."""
import asyncio
import httpx
import os
from dotenv import load_dotenv
load_dotenv()

MIMO_API_KEY = os.getenv("MIMO_API_KEY")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2-omni")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def debug_mimo():
    print("=== MIMO DEBUG ===")
    if not MIMO_API_KEY:
        print("No API key")
        return
    async with httpx.AsyncClient(timeout=30) as client:
        # Try /v1/models first
        try:
            r = await client.get(f"{MIMO_BASE_URL}/models", headers={"Authorization": f"Bearer {MIMO_API_KEY}"})
            print(f"Models endpoint: {r.status_code}")
            if r.status_code == 200:
                models = r.json()
                print(f"Available models: {str(models)[:500]}")
        except Exception as e:
            print(f"Models error: {e}")
        
        # Try chat completion
        try:
            r = await client.post(
                f"{MIMO_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"},
                json={"model": MIMO_MODEL, "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 50},
            )
            print(f"Chat status: {r.status_code}")
            print(f"Chat response: {r.text[:500]}")
        except Exception as e:
            print(f"Chat error: {e}")

async def debug_nvidia():
    print("\n=== NVIDIA DEBUG ===")
    if not NVIDIA_API_KEY:
        print("No API key")
        return
    async with httpx.AsyncClient(timeout=30) as client:
        # Try listing models
        try:
            r = await client.get(f"{NVIDIA_BASE_URL}/models", headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"})
            print(f"Models endpoint: {r.status_code}")
            if r.status_code == 200:
                models = r.json()
                if isinstance(models, dict) and 'data' in models:
                    for m in models['data'][:15]:
                        print(f"  - {m.get('id', m)}")
                else:
                    print(str(models)[:500])
        except Exception as e:
            print(f"Models error: {e}")
        
        # Try a simple chat with commonly available model
        for model in ["meta/llama-3.1-8b-instruct", "meta/llama-3.1-70b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct", "deepseek-ai/deepseek-r1"]:
            try:
                r = await client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 50},
                )
                print(f"{model}: {r.status_code}")
                if r.status_code == 200:
                    print(f"  Response: {r.text[:200]}")
                    break
                else:
                    print(f"  Error: {r.text[:200]}")
            except Exception as e:
                print(f"{model}: error {e}")

async def debug_gemini():
    print("\n=== GEMINI DEBUG ===")
    if not GEMINI_API_KEY:
        print("No API key")
        return
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # List models
        for m in genai.list_models():
            if 'flash' in m.name.lower() or 'gemini' in m.name.lower():
                print(f"  Model: {m.name}")
        model = genai.GenerativeModel("gemini-2.0-flash")
        resp = model.generate_content("Say hello in JSON format: {\"msg\": \"hello\"}")
        print(f"Gemini response: {resp.text[:200]}")
    except Exception as e:
        print(f"Gemini error: {e}")

async def main():
    await debug_mimo()
    await debug_nvidia()
    await debug_gemini()

asyncio.run(main())