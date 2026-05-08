"""Fetch odds from Cloudbet and parse market data."""
import httpx
import json
from typing import Optional
from config import CLOUDBET_API_KEY, CLOUDBET_BASE, IPL_COMPETITION
import db


async def fetch_ipl_events() -> list:
    """Fetch all IPL events from Cloudbet."""
    if not CLOUDBET_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{CLOUDBET_BASE}/odds/competitions/{IPL_COMPETITION}",
                headers={"X-Api-Key": CLOUDBET_API_KEY},
                params={"limit": 100},
            )
            data = resp.json()
            events = data.get("events", [])
            
            # Save matches to DB
            for ev in events:
                name = ev.get("name", "")
                teams = name.split(" v ") if " v " in name else ["", ""]
                db.save_match({
                    "id": str(ev.get("id", "")),
                    "name": name,
                    "home_team": teams[0].strip(),
                    "away_team": teams[1].strip() if len(teams) > 1 else "",
                    "venue": "",
                    "start_time": ev.get("cutoffTime", ""),
                    "status": ev.get("status", "upcoming").lower(),
                })
            
            return events
    except Exception as e:
        print(f"[OddsFetcher] Error fetching events: {e}")
        return []


async def fetch_event_odds(event_id: str) -> dict:
    """Fetch detailed odds for a specific event."""
    if not CLOUDBET_API_KEY:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{CLOUDBET_BASE}/odds/events/{event_id}",
                headers={"X-Api-Key": CLOUDBET_API_KEY},
            )
            data = resp.json()
            
            # Save odds snapshots to DB
            markets = data.get("markets", {})
            for market_type, market_data in markets.items():
                selections = market_data.get("selections", [])
                if selections:
                    db.save_odds(event_id, market_type, selections)
            
            return data
    except Exception as e:
        print(f"[OddsFetcher] Error fetching odds for {event_id}: {e}")
        return {}


def parse_match_odds(event_data: dict) -> list:
    """Parse event data into tradeable market opportunities."""
    opportunities = []
    event_id = str(event_data.get("id", ""))
    event_name = event_data.get("name", "")
    markets = event_data.get("markets", {})
    
    for market_type, market_data in markets.items():
        selections = market_data.get("selections", [])
        status = market_data.get("status", "")
        
        if status not in ("TRADING", ""):
            continue
        
        for sel in selections:
            sel_name = sel.get("name", "")
            price = sel.get("price", 0)
            sel_status = sel.get("status", "")
            line = sel.get("line", sel.get("handicap", None))
            
            if sel_status not in ("TRADING", ""):
                continue
            if not price or price <= 1.0:
                continue
            
            opportunities.append({
                "event_id": event_id,
                "event_name": event_name,
                "market_type": market_type,
                "selection": sel_name,
                "odds": float(price),
                "line": float(line) if line else None,
                "status": sel_status,
            })
    
    return opportunities


def get_upcoming_matches() -> list:
    """Get upcoming IPL matches from DB."""
    events = []
    try:
        conn = db.get_conn()
        rows = conn.execute("""
            SELECT * FROM matches 
            WHERE status IN ('upcoming', 'trading')
            ORDER BY start_time ASC
        """).fetchall()
        conn.close()
        events = [dict(r) for r in rows]
    except Exception:
        pass
    return events


async def place_bet_cloudbet(event_id: str, market_type: str, selection: str, 
                              amount: float, odds: float) -> Optional[dict]:
    """Place a bet on Cloudbet (live mode only)."""
    if not CLOUDBET_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{CLOUDBET_BASE}/bet",
                headers={
                    "X-Api-Key": CLOUDBET_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "eventId": event_id,
                    "marketType": market_type,
                    "selection": selection,
                    "amount": str(amount),
                    "odds": str(odds),
                },
            )
            return resp.json()
    except Exception as e:
        print(f"[Cloudbet] Bet placement error: {e}")
        return None