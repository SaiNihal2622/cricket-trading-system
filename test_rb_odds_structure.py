"""Dump the full structure of a match detail page to understand layout."""
import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "backend")
from exchange.royalbook import RoyalBookExchange

MATCH_URL = ("https://royalbook.win/exchange_sports/cricket/indian-premier-league/"
             "kolkata-knight-riders-v-punjab-kings/NDoxMDE0ODA6MzU0NDk2NzU6QmV0RmFpcg==")

async def main():
    rb = RoyalBookExchange(username="sainihal2622204", password="Sainihal@22", headless=True)
    await rb.start()
    print(f"logged_in={rb._logged_in} demo={rb._demo_mode}")

    p = rb._page
    await p.goto(MATCH_URL, wait_until="networkidle", timeout=30000)
    await p.wait_for_timeout(3000)
    await rb._dismiss_modal()

    await p.screenshot(path="rb_match_detail.png")
    print("Screenshot saved: rb_match_detail.png")

    # Dump all text content
    body = await p.inner_text("body")
    print("\n=== FULL PAGE TEXT (first 3000 chars) ===")
    print(body[:3000])

    # Check what table/tr/td structure exists
    tables = await p.evaluate("""() => {
        const tables = [...document.querySelectorAll('table')];
        return tables.map(t => ({
            rows: t.querySelectorAll('tr').length,
            text: t.innerText.trim().substring(0, 200)
        }));
    }""")
    print(f"\n=== TABLES FOUND: {len(tables)} ===")
    for i, t in enumerate(tables):
        print(f"  Table {i}: {t['rows']} rows | {t['text']!r}")

    # Check key headings
    headings = await p.evaluate("""() => {
        return [...document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="heading"]')]
            .map(e => e.innerText.trim())
            .filter(t => t.length > 0);
    }""")
    print(f"\n=== HEADINGS/TITLES ===")
    for h in headings[:20]:
        print(f"  {h!r}")

    # Look for odds-like numbers
    odds_structure = await p.evaluate("""() => {
        // Find all elements containing 2-digit decimals (typical odds)
        const result = [];
        document.querySelectorAll('[class*="odd"],[class*="back"],[class*="lay"],[class*="price"],[class*="rate"]').forEach(el => {
            const t = el.innerText.trim();
            if (t && t.length < 100) result.push({class: el.className.substring(0,60), text: t.substring(0,80)});
        });
        return result.slice(0, 30);
    }""")
    print(f"\n=== ELEMENTS WITH ODDS CLASSES ===")
    for o in odds_structure:
        print(f"  [{o['class']}] {o['text']!r}")

    # Look for specific market sections
    markets = await p.evaluate("""() => {
        const keywords = ['Match Odds', 'Bookmaker', 'Session', 'Fancy', 'Over Runs'];
        return keywords.map(kw => {
            const el = [...document.querySelectorAll('*')].find(
                e => e.childElementCount === 0 && e.innerText?.trim() === kw
            );
            return {kw, found: !!el, parentHTML: el ? el.parentElement?.outerHTML?.substring(0,300) : null};
        });
    }""")
    print(f"\n=== MARKET SECTIONS ===")
    for m in markets:
        if m['found']:
            print(f"  [{m['kw']}] Found! Parent: {m['parentHTML']!r}")
        else:
            print(f"  [{m['kw']}] NOT FOUND")

    await rb.stop()

asyncio.run(main())
