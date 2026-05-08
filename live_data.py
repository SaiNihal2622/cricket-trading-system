"""Live data fetcher - pulls real match data from Cloudbet API."""
import os
import httpx
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("live_data")

API_KEY = os.getenv("CLOUDBET_API_KEY", "")
FEED_BASE = "https://sports-api.cloudbet.com/pub/v2/odds"
IPL_KEY = "cricket-india-indian-premier-league"

_headers = {"X-Api-Key": API_KEY, "Accept": "application/json"}


def fetch_cloudbet_events() -> list:
    """Fetch all active IPL events from Cloudbet with real odds."""
    if not API_KEY:
        log.warning("No CLOUDBET_API_KEY set")
        return []
    try:
        r = httpx.get(f"{FEED_BASE}/competitions/{IPL_KEY}", headers=_headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        events = []
        for ev in data.get("events", []):
            if ev.get("type") == "EVENT_TYPE_OUTRIGHT":
                continue
            home = (ev.get("home") or {}).get("name", "")
            away = (ev.get("away") or {}).get("name", "")
            if not home or not away:
                continue
            status = ev.get("status", "")
            markets = list(ev.get("markets", {}).keys())
            events.append({
                "id": ev["id"],
                "name": f"{home} vs {away}",
                "home": home,
                "away": away,
                "status": "live" if status == "TRADING_LIVE" else ("upcoming" if status == "TRADING" else "completed"),
                "cloudbet_status": status,
                "start_time": ev.get("cutoffTime", ""),
                "markets": markets,
                "market_count": len(markets),
            })
        return events
    except Exception as e:
        log.error(f"Cloudbet fetch error: {e}")
        return []


def fetch_event_odds(event_id: int, market_key: str = "cricket.team_totals") -> dict:
    """Fetch odds for a specific event and market."""
    if not API_KEY:
        return {}
    try:
        r = httpx.get(
            f"{FEED_BASE}/events/{event_id}",
            headers=_headers,
            params={"markets": market_key},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("markets", {})
    except Exception as e:
        log.debug(f"Odds fetch error for {event_id}/{market_key}: {e}")
        return {}


def parse_odds(market_data: dict) -> list:
    """Extract selections with prices from market data."""
    selections = []
    for sub_key, sub in market_data.get("submarkets", {}).items():
        for sel in sub.get("selections", []):
            price = sel.get("price", 0)
            if price and price > 1.0:
                selections.append({
                    "label": sel.get("label", ""),
                    "price": float(price),
                    "outcome": sel.get("outcome", ""),
                    "params": sel.get("params", ""),
                })
    return selections


def get_live_match_data() -> dict:
    """Get comprehensive live match data for the dashboard."""
    events = fetch_cloudbet_events()
    result = {
        "events": events,
        "live_count": len([e for e in events if e["status"] == "live"]),
        "upcoming_count": len([e for e in events if e["status"] == "upcoming"]),
        "total_count": len(events),
        "source": "cloudbet_live",
        "fetched_at": datetime.utcnow().isoformat(),
    }

    # For live events, fetch detailed odds
    for ev in events:
        if ev["status"] == "live":
            odds_data = {}
            for mkt in ["cricket.team_totals", "cricket.over_team_total"]:
                if mkt in ev["markets"]:
                    raw = fetch_event_odds(ev["id"], mkt)
                    sels = parse_odds(raw)
                    if sels:
                        odds_data[mkt] = sels
            ev["live_odds"] = odds_data

    return result