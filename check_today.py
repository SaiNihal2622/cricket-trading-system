"""Check today's IPL matches from multiple sources."""
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

# 1. Check The Odds API
api_key = os.getenv("ODDS_API_KEY", "")
if api_key:
    print("=== The Odds API ===")
    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports/cricket_ipl/odds/",
            params={"apiKey": api_key, "regions": "us,eu", "markets": "h2h"},
            timeout=15,
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Type: {type(data)}")
        if isinstance(data, list):
            for e in data[:10]:
                print(f"  {e['home_team']} vs {e['away_team']} - {e['commence_time']}")
                for bm in e.get("bookmakers", [])[:3]:
                    for mkt in bm.get("markets", []):
                        for o in mkt.get("outcomes", []):
                            print(f"    {bm['title']}: {o['name']} @ {o['price']}")
        else:
            print(f"Response: {json.dumps(data, indent=2)[:1000]}")
    except Exception as ex:
        print(f"Error: {ex}")

# 2. Check Cloudbet - try different endpoints
cb_key = os.getenv("CLOUDBET_API_KEY", "")
if cb_key:
    print("\n=== Cloudbet ===")
    headers = {"X-Api-Key": cb_key}
    
    # Try competitions endpoint first
    for endpoint in [
        "https://sports-api.cloudbet.com/pub/v2/odds/competitions/cricket-india-indian-premier-league",
        "https://sports-api.cloudbet.com/pub/v2/odds/competitions",
    ]:
        try:
            r = httpx.get(endpoint, headers=headers, params={"limit": 20}, timeout=15)
            print(f"\n  {endpoint}")
            print(f"  Status: {r.status_code}")
            data = r.json()
            if isinstance(data, dict):
                # Print keys
                print(f"  Keys: {list(data.keys())[:10]}")
                events = data.get("events", data.get("data", []))
                if isinstance(events, list):
                    for ev in events[:5]:
                        name = ev.get("name", ev.get("description", "?"))
                        status = ev.get("status", "?")
                        eid = ev.get("id", "?")
                        print(f"    {name} [{status}] id={eid}")
                else:
                    print(f"  Data snippet: {json.dumps(data, indent=2)[:500]}")
            elif isinstance(data, list):
                for ev in data[:5]:
                    print(f"    {ev.get('name', ev.get('description', '?'))}")
        except Exception as ex:
            print(f"  Error: {ex}")

# 3. Check CricAPI for today's matches
cric_key = os.getenv("CRICAPI_KEY", "")
if cric_key:
    print("\n=== CricAPI ===")
    try:
        r = httpx.get(
            "https://api.cricapi.com/v1/currentMatches",
            params={"apikey": cric_key, "offset": 0},
            timeout=15,
        )
        data = r.json()
        for m in data.get("data", [])[:10]:
            name = m.get("name", "?")
            status = m.get("status", "?")
            match_type = m.get("matchType", "?")
            print(f"  {name} [{status}] type={match_type}")
    except Exception as ex:
        print(f"  Error: {ex}")

# 4. Scrape ESPN for today's IPL
print("\n=== ESPN Cricinfo ===")
try:
    r = httpx.get(
        "https://www.espncricinfo.com/ci/engine/match/index.html",
        params={"view": "live"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
        follow_redirects=True,
    )
    print(f"Status: {r.status_code}")
    # Look for IPL mentions
    text = r.text
    if "Indian Premier League" in text or "IPL" in text:
        print("  Found IPL content on ESPN")
    else:
        print("  No IPL content found on ESPN live page")
except Exception as ex:
    print(f"  Error: {ex}")

# 5. Check Google for today's IPL match
print("\n=== Quick IPL Schedule Check ===")
try:
    r = httpx.get(
        "https://www.google.com/search",
        params={"q": "IPL 2025 match today May 8"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=15,
        follow_redirects=True,
    )
    # Extract match info from Google
    text = r.text
    if "IPL" in text:
        # Find match-related text
        import re
        matches = re.findall(r'(\w+\s+\w+\s+\w*)\s+vs\s+(\w+\s+\w+\s+\w*)', text)
        for m in matches[:5]:
            print(f"  {m[0]} vs {m[1]}")
except Exception as ex:
    print(f"  Error: {ex}")