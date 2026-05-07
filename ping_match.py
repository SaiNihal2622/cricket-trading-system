import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from backend.data_ingestion.live_feed import LiveFeedManager

async def check():
    print("Fetching CricBuzz Match Status...")
    feed = LiveFeedManager()
    matches = await feed.scraper.get_live_matches()
    if not matches:
        print("CricBuzz says no matches are currently LIVE. Wait a few minutes for the toss/first ball!")
    else:
        for m in matches:
            print(f"LIVE: {m.get('team_a')} vs {m.get('team_b')} | Status: {m.get('status')}")

if __name__ == "__main__":
    asyncio.run(check())
