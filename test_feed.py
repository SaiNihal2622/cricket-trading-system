import asyncio
import os
import sys

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from data_ingestion.live_feed import LiveFeedManager
from data_ingestion.telegram_scraper import TelegramScraper

async def main():
    print("Testing Live Feed Manager / APIs...")
    mgr = LiveFeedManager()
    
    # Try fetching a match state
    match = await mgr.get_live_match_state('rcb', 'csk')
    print("Live Feed Manager (Cricbuzz/CricAPI fallback) working:", match is not None)
    
    # Test telegram scraper instantiation (API check)
    try:
         ts = TelegramScraper()
         print("Telegram Scraper initialized successfully.")
    except Exception as e:
         print("Telegram Scraper init failed:", e)

if __name__ == "__main__":
    asyncio.run(main()) 
