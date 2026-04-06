"""Try different username formats + demo login."""
import asyncio, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright

USERNAMES_TO_TRY = [
    "sainihal2622204",
    "2622204",
    "sainihal",
    "SAINIHAL2622204",
]
PASSWORD = "Sainihal@22"

async def try_login(page, username, password):
    await page.goto("https://royalbook.win/login", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1000)
    await page.fill('input[name="username"]', username)
    await page.fill('input[type="password"]', password)
    await page.click('button:has-text("Login")')
    await page.wait_for_timeout(3000)
    url = page.url
    body = await page.inner_text("body")
    success = "login" not in url.lower()
    error = ""
    for msg in ["User not found", "Invalid", "incorrect", "error", "An error"]:
        if msg.lower() in body.lower():
            error = msg
            break
    return success, url, error

async def try_demo(page):
    await page.goto("https://royalbook.win/login", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1000)
    await page.click('button:has-text("Demo login")')
    await page.wait_for_timeout(4000)
    url = page.url
    success = "login" not in url.lower()
    body = await page.inner_text("body")
    return success, url, body[:200]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        async def add_origin(route, req):
            await route.continue_(headers={**req.headers, "Origin": "https://royalbook.win", "Referer": "https://royalbook.win/login"})
        await page.route("**/*", add_origin)

        # Try each username format
        for uname in USERNAMES_TO_TRY:
            success, url, error = await try_login(page, uname, PASSWORD)
            status = "SUCCESS" if success else f"FAILED ({error})"
            print(f"  [{status}] Username: {uname!r}  -> {url}")
            if success:
                break

        # Try demo login
        print("\nTrying Demo login...")
        success, url, body = await try_demo(page)
        print(f"  Demo login: {'SUCCESS' if success else 'FAILED'} -> {url}")
        if success:
            print(f"  Page content: {body!r}")
            await page.screenshot(path="rb_demo_logged_in.png")
            print("  Screenshot: rb_demo_logged_in.png")

        await browser.close()

asyncio.run(main())
