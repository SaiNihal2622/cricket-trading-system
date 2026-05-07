import asyncio
import os
import sys

# add backend path securely
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from data_ingestion.live_feed import LiveFeedManager
from exchange.royalbook import RoyalBookExchange
from config.settings import settings
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_all():
    print("=== TESTING CRICBUZZ API ===")
    feed_mgr = LiveFeedManager()
    try:
        matches = await feed_mgr.scraper.get_live_matches()
        print(f"CricBuzz matches found: {len(matches)}")
        for m in matches[:2]:
            print(f" - {m.get('team_a')} vs {m.get('team_b')}")
    except Exception as e:
        print(f"CricBuzz Error: {e}")

    print("\n=== TESTING ROYALBOOK LIVE SCRAPE ===")
    rb = RoyalBookExchange(username=settings.ROYALBOOK_USERNAME, password=settings.ROYALBOOK_PASSWORD, headless=True)
    try:
        await rb.start()
        rb_matches = await rb.get_live_cricket_matches()
        print(f"RoyalBook matches found: {len(rb_matches)}")
        for m in rb_matches[:3]:
             print(f" - {m.get('title')} | URL: {m.get('url')}")
    except Exception as e:
        print(f"RoyalBook Error: {e}")
    finally:
        await rb.stop()

    print("\n=== TESTING TELEGRAM SESSION ===")
    try:
        if os.getenv("TELEGRAM_SESSION"):
            client = TelegramClient(StringSession(os.getenv("TELEGRAM_SESSION")), settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
            await client.connect()
            print("Telegram authorized:", await client.is_user_authorized())
            await client.disconnect()
        else:
             print("No session string mapped in script env.")
    except Exception as e:
        print(f"Telegram error: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    asyncio.run(test_all())
