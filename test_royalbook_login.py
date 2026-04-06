"""
Quick test: Can we log into RoyalBook from this machine?
Run: python test_royalbook_login.py
"""
import asyncio, sys
sys.path.insert(0, "backend")

# Fix Windows terminal encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from exchange.royalbook import RoyalBookExchange

async def main():
    rb = RoyalBookExchange(
        username="sainihal2622204",
        password="Sainihal@22",
        headless=False,   # visible window so you can see what happens
    )
    print("Starting browser...")
    await rb.start()
    print(f"Logged in: {rb._logged_in}")

    if rb._logged_in:
        print("[SUCCESS] RoyalBook login works from local machine!")
        print("Fetching live matches...")
        matches = await rb.get_live_cricket_matches()
        print(f"Found {len(matches)} matches:")
        for m in matches:
            print(f"  - {m.get('title', m.get('url', '?'))} | IPL={m.get('is_ipl')} | Live={m.get('is_live')}")
    else:
        print("[FAILED] Login failed even locally. Check credentials or site status.")

    input("Press Enter to close browser...")
    await rb.stop()

asyncio.run(main())
