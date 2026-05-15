"""Quick NVIDIA API connectivity test - uses environment variables."""
import asyncio
import httpx
import os


async def test():
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        print("No NVIDIA_API_KEY set, skipping")
        return
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            'https://integrate.api.nvidia.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'deepseek-ai/deepseek-v4-flash',
                'messages': [{'role': 'user', 'content': 'say hello'}],
                'max_tokens': 10
            }
        )
        print(f'NVIDIA status: {r.status_code}')
        print(r.text[:500])


asyncio.run(test())