"""Test NVIDIA models to find which ones work."""
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

# Models from the listing that we should try
MODELS = [
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
    "bytedance/seed-oss-36b-instruct",
    "01-ai/yi-large",
    "ai21labs/jamba-1.5-large-instruct",
    "google/codegemma-1.1-7b",
    "databricks/dbrx-instruct",
]

async def test_models():
    async with httpx.AsyncClient(timeout=60) as client:
        for model in MODELS:
            try:
                r = await client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": 'Reply with this JSON: {"probability": 0.5, "confidence": 0.9, "reasoning": "test", "key_factors": ["test"]}'}],
                        "temperature": 0.1,
                        "max_tokens": 200,
                    },
                )
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    print(f"✅ {model}: {content[:150]}")
                else:
                    print(f"❌ {model}: {r.status_code} - {r.text[:100]}")
            except Exception as e:
                print(f"❌ {model}: {e}")

asyncio.run(test_models())