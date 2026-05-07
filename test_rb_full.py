"""
Full RoyalBook accessibility test:
1. Login (real creds or demo fallback)
2. List IPL matches + extract odds from list view
3. Dismiss modal, click match div, resolve URL
4. Navigate to match detail, scrape full odds (match_odds, bookmaker, sessions)
5. Print everything + screenshots at each stage

Run: python test_rb_full.py
"""
import asyncio, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "backend")

from exchange.royalbook import RoyalBookExchange

SCREENSHOTS = "rb_screenshots"

async def main():
    os.makedirs(SCREENSHOTS, exist_ok=True)

    rb = RoyalBookExchange(
        username="sainihal2622204",
        password="Sainihal@22",
        headless=False,
    )

    print("=" * 60)
    print("STEP 1 — Starting browser & logging in")
    print("=" * 60)
    await rb.start()
    print(f"  logged_in={rb._logged_in}  demo_mode={rb._demo_mode}")
    await rb._page.screenshot(path=f"{SCREENSHOTS}/01_after_login.png")

    if not rb._logged_in:
        print("  ❌ Login failed — cannot continue")
        await rb.stop()
        return

    print("\n" + "=" * 60)
    print("STEP 2 — Navigate to cricket page + dismiss modal")
    print("=" * 60)
    from playwright.async_api import async_playwright
    p = rb._page
    await p.goto(rb.CRICKET_URL, wait_until="networkidle", timeout=25000)
    await p.wait_for_timeout(3000)
    await rb._page.screenshot(path=f"{SCREENSHOTS}/02_cricket_before_dismiss.png")
    print("  Screenshot saved (before dismiss)")

    await rb._dismiss_modal()
    await p.wait_for_timeout(500)
    await rb._page.screenshot(path=f"{SCREENSHOTS}/03_cricket_after_dismiss.png")
    print("  Modal dismissed. Screenshot saved.")

    print("\n" + "=" * 60)
    print("STEP 3 — Get live matches (list view)")
    print("=" * 60)
    matches = await rb.get_live_cricket_matches()
    print(f"  Found {len(matches)} total matches")
    ipl = [m for m in matches if m.get("is_ipl")]
    print(f"  IPL matches: {len(ipl)}")
    for m in matches[:10]:
        url_str = m.get('url') or 'NO_URL'
        print(f"    {'[IPL]' if m.get('is_ipl') else '     '} "
              f"{m.get('title','?')} | "
              f"back_a={m.get('back_a')} back_b={m.get('back_b')} | "
              f"url={url_str[:60]}")

    await rb._page.screenshot(path=f"{SCREENSHOTS}/04_after_match_list.png")

    # Pick first IPL match with a URL
    target = next((m for m in matches if m.get("is_ipl") and m.get("url")), None)
    if not target:
        target = next((m for m in matches if m.get("is_ipl")), None)

    if not target:
        print("\n  ⚠ No IPL match found — stopping here")
        await rb.stop()
        return

    print(f"\n  → Target match: {target.get('title')}")

    print("\n" + "=" * 60)
    print("STEP 4 — Navigate to match detail")
    print("=" * 60)
    if target.get("url"):
        print(f"  Using URL: {target['url']}")
        await rb.navigate_to_match(target["url"])
    else:
        # Try JS click again with fresh page
        await p.goto(rb.CRICKET_URL, wait_until="domcontentloaded", timeout=20000)
        await p.wait_for_timeout(2000)
        await rb._dismiss_modal()
        print("  No URL — trying JS click on cricket page")
        team_a = target.get("team_a", "")
        team_b = target.get("team_b", "")
        before = p.url
        await p.evaluate("""([ta, tb]) => {
            const allDivs = [...document.querySelectorAll('div')];
            let best = null, bestSize = Infinity;
            for (const d of allDivs) {
                const txt = d.innerText || '';
                if (txt.includes(ta) && txt.includes(tb)) {
                    if (txt.length < bestSize) { bestSize = txt.length; best = d; }
                }
            }
            if (best) best.click();
        }""", [team_a, team_b])
        await p.wait_for_timeout(3000)
        print(f"  URL after click: {p.url}")
        rb._active_match_url = p.url

    await rb._page.screenshot(path=f"{SCREENSHOTS}/05_match_detail.png")
    print(f"  Page URL: {p.url}")
    body_text = await p.inner_text("body")
    print(f"  Page content preview: {body_text[:300]!r}")

    print("\n" + "=" * 60)
    print("STEP 5 — Scrape full odds")
    print("=" * 60)
    odds = await rb.scrape_match_odds()
    print(f"  match_title : {odds.get('match_title')}")
    print(f"  score       : {odds.get('score')}")
    print(f"  match_odds  : {odds.get('match_odds')}")
    print(f"  bookmaker   : {odds.get('bookmaker')}")
    sessions = odds.get("sessions", [])
    print(f"  sessions    : {len(sessions)} entries")
    for s in sessions[:5]:
        print(f"    {s}")
    premium = odds.get("premium_sessions", [])
    print(f"  premium     : {len(premium)} entries")
    for s in premium[:3]:
        print(f"    {s}")

    await rb._page.screenshot(path=f"{SCREENSHOTS}/06_odds_scraped.png")

    print("\n" + "=" * 60)
    print("STEP 6 — Balance check")
    print("=" * 60)
    bal = await rb.get_balance()
    print(f"  Balance: ₹{bal}")

    print("\n✅ Full accessibility test complete!")
    print(f"   Screenshots saved in: {SCREENSHOTS}/")

    input("\nPress Enter to close browser...")
    await rb.stop()

asyncio.run(main())
