"""Quick API connectivity test - uses environment variables for keys."""
import asyncio
import httpx
import os


async def test_groq():
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        print("No GROQ_API_KEY set, skipping")
        return
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post('https://api.groq.com/openai/v1/chat/completions', 
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, 
            json={'model': 'llama-3.1-8b-instant', 'messages': [{'role': 'user', 'content': 'say hello'}], 'max_tokens': 10})
        print(f'Groq status: {r.status_code}')
        if r.status_code == 200: print('Groq works!')
        else: print(r.text[:300])


async def test_gemini():
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        print("No GEMINI_API_KEY set, skipping")
        return
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        r = model.generate_content('say hello in 5 words')
        print(f'Gemini works! Response: {r.text[:50]}')
    except Exception as e:
        print(f'Gemini error: {e}')


async def test_nvidia():
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        print("No NVIDIA_API_KEY set, skipping")
        return
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post('https://integrate.api.nvidia.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'model': 'deepseek-ai/deepseek-v4-flash', 'messages': [{'role': 'user', 'content': 'say hello'}], 'max_tokens': 10})
        print(f'NVIDIA status: {r.status_code}')
        if r.status_code == 200: print('NVIDIA works!')
        else: print(r.text[:300])


async def test_mimo():
    key = os.getenv("MIMO_API_KEY", "")
    if not key:
        print("No MIMO_API_KEY set, skipping")
        return
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post('https://token-plan-sgp.xiaomimimo.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'model': 'mimo-v2.5-pro', 'messages': [{'role': 'user', 'content': 'say hello'}], 'max_tokens': 10})
        print(f'MiMo status: {r.status_code}')
        if r.status_code == 200: print('MiMo works!')
        else: print(r.text[:300])


async def test_grok():
    key = os.getenv("GROK_API_KEY", "")
    if not key:
        print("No GROK_API_KEY set, skipping")
        return
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post('https://api.x.ai/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'model': 'grok-3-mini', 'messages': [{'role': 'user', 'content': 'say hello'}], 'max_tokens': 10})
        print(f'Grok status: {r.status_code}')
        if r.status_code == 200: print('Grok works!')
        else: print(r.text[:300])


async def main():
    print("=== API Connectivity Test ===")
    print("(Set env vars: GROQ_API_KEY, GEMINI_API_KEY, NVIDIA_API_KEY, MIMO_API_KEY, GROK_API_KEY)")
    for name, func in [("Groq", test_groq), ("Gemini", test_gemini), ("NVIDIA", test_nvidia), ("MiMo", test_mimo), ("Grok", test_grok)]:
        print(f"\n--- Testing {name} ---")
        try:
            await func()
        except Exception as e:
            print(f'{name} failed: {e}')


if __name__ == "__main__":
    asyncio.run(main())