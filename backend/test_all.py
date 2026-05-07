import asyncio
import os
from data_ingestion.live_feed import LiveFeedManager
from exchange.royalbook import RoyalBookExchange
from config.settings import settings
from telethon import TelegramClient
from telethon.sessions import StringSession

async def test_all():
    with open('test_results.txt', 'w') as f:
        f.write("=== TESTING CRICBUZZ API ===\\n")
        feed_mgr = LiveFeedManager()
        try:
            matches = await feed_mgr.scraper.get_live_matches()
            f.write(f"CricBuzz matches found: {len(matches)}\\n")
            for m in matches[:2]:
                f.write(f" - {m.get('team_a')} vs {m.get('team_b')}\\n")
        except Exception as e:
            f.write(f"CricBuzz Error: {e}\\n")

        f.write("\\n=== TESTING ROYALBOOK LIVE SCRAPE ===\\n")
        rb = RoyalBookExchange(username=settings.ROYALBOOK_USERNAME, password=settings.ROYALBOOK_PASSWORD, headless=True)
        try:
            await rb.start()
            rb_matches = await rb.get_live_cricket_matches()
            f.write(f"RoyalBook matches found: {len(rb_matches)}\\n")
            for m in rb_matches[:3]:
                 f.write(f" - {m.get('title')} | URL: {m.get('url')}\\n")
        except Exception as e:
            f.write(f"RoyalBook Error: {e}\\n")
        finally:
            await rb.stop()

        f.write("\\n=== TESTING TELEGRAM SESSION ===\\n")
        try:
            session = os.getenv("TELEGRAM_SESSION", "")
            if session:
                client = TelegramClient(StringSession(session), int(os.getenv("TELEGRAM_API_ID", 0)), os.getenv("TELEGRAM_API_HASH", ""))
                await client.connect()
                f.write(f"Telegram authorized: {await client.is_user_authorized()}\\n")
                await client.disconnect()
            else:
                 f.write("No session string.\\n")
        except Exception as e:
            f.write(f"Telegram error: {e}\\n")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    asyncio.run(test_all())
