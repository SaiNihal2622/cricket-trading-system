"""Capture the exact login API request RoyalBook sends."""
import asyncio, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-IN", timezone_id="Asia/Kolkata",
        )
        page = await ctx.new_page()

        # Intercept all requests to add Origin + capture login API calls
        async def intercept(route, req):
            if "login" in req.url.lower() or "auth" in req.url.lower() or "sign" in req.url.lower():
                print(f"\n=== LOGIN API REQUEST ===")
                print(f"URL: {req.url}")
                print(f"Method: {req.method}")
                print(f"Headers: {dict(req.headers)}")
                try:
                    body = req.post_data
                    print(f"Body: {body}")
                except:
                    pass
            await route.continue_(headers={**req.headers,
                "Origin": "https://royalbook.win",
                "Referer": "https://royalbook.win/login"})

        async def on_response(resp):
            if any(x in resp.url.lower() for x in ["login", "auth", "sign", "account"]):
                print(f"\n=== API RESPONSE ===")
                print(f"URL: {resp.url}  Status: {resp.status}")
                try:
                    body = await resp.text()
                    print(f"Body: {body[:500]}")
                except:
                    pass

        await page.route("**/*", intercept)
        page.on("response", on_response)

        print("Loading login page...")
        await page.goto("https://royalbook.win/login", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        # Fill and submit
        await page.fill('input[name="username"]', "sainihal2622204")
        await page.fill('input[type="password"]', "Sainihal@22")
        print("\nFilled form, clicking Login...")
        await page.click('button:has-text("Login")')
        await page.wait_for_timeout(4000)

        print(f"\nFinal URL: {page.url}")
        body = await page.inner_text("body")
        print(f"Page text: {body[:300]!r}")

        await browser.close()

asyncio.run(main())
