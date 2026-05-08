"""Get detailed odds for today's DC vs KKR match."""
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()
cb_key = os.getenv("CLOUDBET_API_KEY", "")
headers = {"X-Api-Key": cb_key}

EVENT_ID = 34351209  # DC vs KKR today

print("=== DC vs KKR - All Markets ===")
r = httpx.get(
    f"https://sports-api.cloudbet.com/pub/v2/odds/events/{EVENT_ID}",
    headers=headers,
    timeout=15,
)
data = r.json()
print(f"Event: {data.get('name')}")
print(f"Status: {data.get('status')}")
print(f"Cutoff: {data.get('cutoffTime')}")

markets = data.get("markets", {})
print(f"\nTotal markets: {len(markets)}")

for mkey, mval in sorted(markets.items()):
    selections = mval.get("selections", [])
    status = mval.get("status", "?")
    print(f"\n--- {mkey} [{status}] ---")
    for s in selections[:10]:
        sn = s.get("name", "?")
        sp = s.get("price", "?")
        ss = s.get("status", "?")
        line = s.get("line", s.get("handicap", ""))
        line_str = f" line={line}" if line else ""
        print(f"  {sn}: {sp} [{ss}]{line_str}")

# Save full data for the dashboard
with open("today_match_odds.json", "w") as f:
    json.dump(data, f, indent=2)
print("\nSaved full data to today_match_odds.json")