"""Test real Cloudbet API connectivity."""
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("CLOUDBET_API_KEY", "")
FEED_BASE = "https://sports-api.cloudbet.com/pub/v2/odds"
IPL_KEY = "cricket-india-indian-premier-league"

headers = {"X-Api-Key": API_KEY, "Accept": "application/json"}

print(f"API Key present: {bool(API_KEY)}")
print(f"API Key length: {len(API_KEY)}")
print()

# Test 1: Get IPL competition events
print("=" * 60)
print("TEST 1: Fetching IPL events from Cloudbet")
print("=" * 60)
try:
    r = httpx.get(f"{FEED_BASE}/competitions/{IPL_KEY}", headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        events = data.get("events", [])
        print(f"Total events found: {len(events)}")
        for ev in events[:10]:
            if ev.get("type") == "EVENT_TYPE_OUTRIGHT":
                continue
            home = (ev.get("home") or {}).get("name", "?")
            away = (ev.get("away") or {}).get("name", "?")
            status = ev.get("status", "?")
            markets = list(ev.get("markets", {}).keys())
            cutoff = ev.get("cutoffTime", "")
            print(f"  ID={ev['id']} | {home} vs {away} | status={status}")
            print(f"    cutoff={cutoff}")
            print(f"    markets={markets}")
            print()
    else:
        print(f"Error: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Get Odds API live scores
print("=" * 60)
print("TEST 2: Fetching live scores from The Odds API")
print("=" * 60)
ODDS_KEY = os.getenv("ODDS_API_KEY", "")
print(f"Odds API Key present: {bool(ODDS_KEY)}")
if ODDS_KEY:
    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports/cricket_ipl/scores/",
            params={"apiKey": ODDS_KEY, "daysFrom": 1},
            timeout=10,
        )
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            scores = r.json()
            print(f"Score entries: {len(scores)}")
            for ev in scores[:5]:
                print(f"  {ev.get('id')} | {ev.get('sport_key')} | completed={ev.get('completed')}")
                for s in (ev.get("scores") or []):
                    print(f"    {s.get('name')}: {s.get('score')}")
        else:
            print(f"Error: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

# Test 3: Get live cricket odds
print()
print("=" * 60)
print("TEST 3: Fetching live cricket odds from The Odds API")
print("=" * 60)
if ODDS_KEY:
    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports/cricket_ipl/odds/",
            params={"apiKey": ODDS_KEY, "regions": "us,uk", "markets": "h2h"},
            timeout=10,
        )
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            odds = r.json()
            print(f"Odds entries: {len(odds)}")
            for ev in odds[:5]:
                teams = ev.get("teams", [])
                home = ev.get("home_team", "?")
                away = ev.get("away_team", "?")
                commence = ev.get("commence_time", "?")
                print(f"  {home} vs {away} | commence={commence}")
                for book in (ev.get("bookmakers", []) or [])[:2]:
                    print(f"    Book: {book.get('title')}")
                    for mkt in (book.get("markets") or []):
                        for out in (mkt.get("outcomes") or []):
                            print(f"      {out.get('name')}: {out.get('price')}")
        else:
            print(f"Error: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

print()
print("=" * 60)
print("DONE")
print("=" * 60)