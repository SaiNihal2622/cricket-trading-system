"""Debug: capture RoyalBook login network requests + screenshot the form."""
import asyncio, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        # Add Origin to all requests
        async def add_origin(route, req):
            await route.continue_(headers={**req.headers, "Origin": "https://royalbook.win", "Referer": "https://royalbook.win/login"})

        page = await ctx.new_page()
        await page.route("**/*", add_origin)

        # Capture all API requests/responses
        api_calls = []
        def on_response(resp):
            if any(x in resp.url for x in ['/api', '/login', '/auth', '/user']):
                api_calls.append({"url": resp.url, "status": resp.status})
                print(f"  API: {resp.status} {resp.url}")
        page.on("response", on_response)

        print("Navigating to login page...")
        await page.goto("https://royalbook.win/login", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Screenshot before filling
        await page.screenshot(path="rb_before.png")
        print("Screenshot saved: rb_before.png")

        # List ALL inputs
        inputs = await page.evaluate("""() => {
            return [...document.querySelectorAll('input')].map(i => ({
                name: i.name, type: i.type, id: i.id,
                placeholder: i.placeholder, value: i.value,
                visible: i.offsetParent !== null
            }));
        }""")
        print("\nAll inputs on page:")
        for i in inputs:
            print(f"  {i}")

        # List all buttons
        buttons = await page.evaluate("""() => {
            return [...document.querySelectorAll('button')].map(b => ({
                text: b.innerText.trim()[:40], type: b.type,
                class: b.className[:60]
            }));
        }""")
        print("\nAll buttons:")
        for b in buttons:
            print(f"  {b}")

        # Try to find and click Username tab
        tabs = await page.query_selector_all('a, button, span, li')
        for t in tabs:
            txt = await t.inner_text()
            if txt.strip().lower() in ["username", "user id", "userid"]:
                print(f"\nClicking tab: {txt.strip()!r}")
                await t.click()
                await page.wait_for_timeout(500)
                break

        # Re-screenshot after tab click
        await page.screenshot(path="rb_after_tab.png")

        # Fill User ID
        uid_sels = ['input[name="username"]', 'input[name="userId"]', 'input[name="user_id"]',
                    'input[placeholder*="User" i]', 'input[placeholder*="ID" i]',
                    'input[type="text"]:visible']
        for sel in uid_sels:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await el.fill("sainihal2622204")
                    val = await el.input_value()
                    print(f"\nFilled {sel!r} with value: {val!r}")
                    break
            except Exception as e:
                pass

        # Fill password
        pwd_el = await page.query_selector('input[type="password"]')
        if pwd_el:
            await pwd_el.fill("Sainihal@22")
            print("Password filled")

        await page.screenshot(path="rb_filled.png")
        print("\nScreenshot saved: rb_filled.png (form filled, before submit)")
        print("\nWaiting 3s so you can see the browser...")
        await page.wait_for_timeout(3000)

        # Submit
        submit = await page.query_selector('button[type="submit"], button:has-text("Login")')
        if submit:
            print("Clicking submit...")
            await submit.click()
            await page.wait_for_timeout(3000)

        await page.screenshot(path="rb_after_login.png")
        print(f"\nFinal URL: {page.url}")
        print("Screenshot saved: rb_after_login.png")

        # Show final page text
        body_text = await page.inner_text("body")
        print(f"\nPage text after login: {body_text[:300]!r}")

        await browser.close()

asyncio.run(main())
