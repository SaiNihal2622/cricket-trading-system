"""Get all Cloudbet IPL events with odds."""
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()
cb_key = os.getenv("CLOUDBET_API_KEY", "")
headers = {"X-Api-Key": cb_key}

# Get all IPL events
print("=== All IPL Events ===")
r = httpx.get(
    "https://sports-api.cloudbet.com/pub/v2/odds/competitions/cricket-india-indian-premier-league",
    headers=headers,
    params={"limit": 100},
    timeout=15,
)
data = r.json()
events = data.get("events", [])
print(f"Total events: {len(events)}")

for ev in events:
    eid = ev.get("id", "?")
    name = ev.get("name", "?")
    status = ev.get("status", "?")
    cutoff = ev.get("cutoffTime", "?")
    markets = ev.get("markets", {})
    
    print(f"\n--- {name} ---")
    print(f"  ID: {eid}")
    print(f"  Status: {status}")
    print(f"  Cutoff: {cutoff}")
    print(f"  Market keys: {list(markets.keys())[:15]}")
    
    # Show match odds if available
    for mkey in ["cricket.match_odds", "cricket.moneyline", "cricket.match_winner"]:
        if mkey in markets:
            mkt = markets[mkey]
            print(f"  {mkey}:")
            for sel in mkt.get("selections", mkt.get("outcomes", [])):
                name_s = sel.get("name", sel.get("outcome", "?"))
                price = sel.get("price", sel.get("odds", "?"))
                print(f"    {name_s}: {price}")

# Also check for live/recent matches
print("\n\n=== Checking specific match events ===")
for ev in events[:5]:
    eid = ev.get("id")
    if eid:
        try:
            r2 = httpx.get(
                f"https://sports-api.cloudbet.com/pub/v2/odds/events/{eid}",
                headers=headers,
                timeout=15,
            )
            detail = r2.json()
            name = detail.get("name", "?")
            status = detail.get("status", "?")
            markets = detail.get("markets", {})
            print(f"\n  {name} [{status}]")
            print(f"  Available markets: {list(markets.keys())[:20]}")
            
            # Show all market odds
            for mkey, mval in list(markets.items())[:10]:
                selections = mval.get("selections", [])
                if selections:
                    print(f"    {mkey}:")
                    for s in selections[:5]:
                        sn = s.get("name", "?")
                        sp = s.get("price", "?")
                        status_s = s.get("status", "?")
                        print(f"      {sn}: {sp} [{status_s}]")
        except Exception as ex:
            print(f"  Error fetching {eid}: {ex}")