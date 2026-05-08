"""Quick script to check today's IPL matches and Cloudbet odds."""
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Check The Odds API for IPL matches
api_key = os.getenv("ODDS_API_KEY", "")
if api_key:
    print("=== The Odds API - IPL Matches ===")
    try:
        r = httpx.get(
            "https://api.the-odds-api.com/v4/sports/cricket_ipl/odds/",
            params={"apiKey": api_key, "regions": "us,eu", "markets": "h2h"},
            timeout=15,
        )
        data = r.json()
        for e in data[:10]:
            print(f"  {e['home_team']} vs {e['away_team']} - {e['commence_time']}")
            for bm in e.get("bookmakers", [])[:3]:
                for mkt in bm.get("markets", []):
                    for o in mkt.get("outcomes", []):
                        print(f"    {bm['title']}: {o['name']} @ {o['price']}")
        if not data:
            print("  No IPL matches found on The Odds API")
    except Exception as ex:
        print(f"  Error: {ex}")
else:
    print("No ODDS_API_KEY set")

# Check Cloudbet for cricket events
cb_key = os.getenv("CLOUDBET_API_KEY", "")
if cb_key:
    print("\n=== Cloudbet - Cricket Events ===")
    try:
        headers = {"X-Api-Key": cb_key}
        r = httpx.get(
            "https://sports-api.cloudbet.com/pub/v2/odds/events",
            params={"sport": "cricket", "limit": 20},
            headers=headers,
            timeout=15,
        )
        data = r.json()
        events = data if isinstance(data, list) else data.get("events", data.get("data", []))
        for ev in events[:10]:
            name = ev.get("name", ev.get("description", "Unknown"))
            status = ev.get("status", "?")
            print(f"  {name} [{status}]")
        if not events:
            print("  No cricket events found on Cloudbet")
    except Exception as ex:
        print(f"  Error: {ex}")
else:
    print("No CLOUDBET_API_KEY set")

# Check current positions
print("\n=== Current Positions ===")
pos_file = "cloudbet_positions.json"
if os.path.exists(pos_file):
    with open(pos_file) as f:
        positions = json.load(f)
    print(json.dumps(positions, indent=2)[:2000])
else:
    print("No positions file found")

# Check trader stats
print("\n=== Trader Stats ===")
stats_file = "trader_stats.json"
if os.path.exists(stats_file):
    with open(stats_file) as f:
        stats = json.load(f)
    print(json.dumps(stats, indent=2)[:2000])
else:
    print("No stats file found")

# Check DB for trades
print("\n=== Recent Trades from DB ===")
db_file = "cricket_trading_local.db"
if os.path.exists(db_file):
    import sqlite3
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    # Get table names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {tables}")
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM [{table}]")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
            if count > 0 and count < 50:
                cur.execute(f"SELECT * FROM [{table}] ORDER BY rowid DESC LIMIT 5")
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    print(f"    {dict(zip(cols, row))}")
        except Exception as ex:
            print(f"  {table}: error - {ex}")
    conn.close()
else:
    print("No database found")