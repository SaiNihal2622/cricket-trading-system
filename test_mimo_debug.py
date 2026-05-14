import asyncio
import httpx
import json

MIMO_API_KEY = "tp-smb26vqnngif8xfg9yumoj1npvc0cr0jjy0csju1rnbc83zz"
MIMO_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"

async def test_mimo():
    print(f"[MiMo] Testing endpoint: {MIMO_BASE_URL}/chat/completions")
    print(f"[MiMo] Key: {MIMO_API_KEY[:20]}...")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{MIMO_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {MIMO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2.5-pro",
                    "messages": [
                        {"role": "user", "content": 'Respond with exactly this JSON: {"probability": 0.65, "confidence": 0.7, "reasoning": "test", "key_factors": ["test"]}'}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            print(f"[MiMo] Status: {resp.status_code}")
            print(f"[MiMo] Response headers: {dict(resp.headers)}")
            data = resp.json()
            print(f"[MiMo] Full response: {json.dumps(data, indent=2)[:2000]}")
            
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                print(f"[MiMo] Choice keys: {choice.keys()}")
                if "message" in choice:
                    msg = choice["message"]
                    print(f"[MiMo] Message keys: {msg.keys()}")
                    print(f"[MiMo] Content: '{msg.get('content', '')}'")
                    if "reasoning_content" in msg:
                        rc = msg["reasoning_content"]
                        print(f"[MiMo] Reasoning content: '{rc[:500] if rc else ''}'")
    except Exception as e:
        err_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
        print(f"[MiMo] Error: {err_msg}")

asyncio.run(test_mimo())