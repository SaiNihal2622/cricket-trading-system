"""Core trading engine - orchestrates odds fetching, AI prediction, and trade execution."""
import asyncio
import json
import math
from datetime import datetime
from typing import Optional
from config import (
    TRADING_MODE, MAX_BET_SIZE, MIN_CONFIDENCE, KELLY_FRACTION, MIN_EDGE,
    TEAMS, VENUE_PATTERNS,
)
import db
from odds_fetcher import fetch_ipl_events, fetch_event_odds, parse_match_odds
from ai_ensemble import get_ensemble_prediction
from ipl_historical import enrich_prompt_context, build_stats

# Load historical stats once at module level
_HISTORICAL_STATS = None

def get_historical_stats():
    global _HISTORICAL_STATS
    if _HISTORICAL_STATS is None:
        try:
            _HISTORICAL_STATS = build_stats()
        except Exception as e:
            print(f"[Historical] Could not load stats: {e}")
            _HISTORICAL_STATS = {}
    return _HISTORICAL_STATS


def kelly_criterion(prob: float, odds: float, fraction: float = KELLY_FRACTION) -> float:
    """Calculate Kelly Criterion bet size.
    fraction: use fractional Kelly for safety (0.25 = quarter Kelly)
    """
    if odds <= 1 or prob <= 0 or prob >= 1:
        return 0
    b = odds - 1  # net odds
    q = 1 - prob
    kelly = (prob * b - q) / b
    if kelly <= 0:
        return 0
    return min(kelly * fraction * MAX_BET_SIZE, MAX_BET_SIZE)


def get_team_stats(team_name: str) -> dict:
    """Get team statistics from config + historical data."""
    team = TEAMS.get(team_name, {})
    stats = get_historical_stats()
    hist = stats.get("team_stats", {}).get(team_name, {})
    return {
        "avg_score": hist.get("avg_score", team.get("avg_score", 170)),
        "home_ground": team.get("home_ground", ""),
        "short": team.get("short", team_name[:3].upper()),
        "win_rate": hist.get("win_rate", 0.5),
        "matches_played": hist.get("matches", 0),
    }


def get_venue_stats(venue: str) -> dict:
    """Get venue statistics from config + historical data."""
    stats = get_historical_stats()
    hist = stats.get("venue_stats", {}).get(venue, {})
    config_venue = VENUE_PATTERNS.get(venue, {})
    return {
        "avg_1st": hist.get("avg_score", config_venue.get("avg_1st", 170)),
        "powerplay": hist.get("avg_powerplay", config_venue.get("powerplay", 52)),
        "death": config_venue.get("death", 48),
        "spin_friendly": config_venue.get("spin_friendly", False),
        "high_score": hist.get("high_score", 0),
        "low_score": hist.get("low_score", 0),
        "matches_at_venue": hist.get("matches", 0),
    }


def extract_teams_from_event(event_name: str) -> tuple:
    """Extract team names from event name like 'DC v KKR'."""
    parts = event_name.split(" v ")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", ""


def resolve_venue(home_team: str) -> str:
    """Resolve venue from team name."""
    team_data = TEAMS.get(home_team, {})
    return team_data.get("home_ground", "Unknown")


async def analyze_opportunity(opp: dict, live_score: Optional[dict] = None) -> Optional[dict]:
    """Analyze a single market opportunity with the AI ensemble."""
    event_name = opp["event_name"]
    home_team, away_team = extract_teams_from_event(event_name)
    venue = resolve_venue(home_team)
    
    venue_stats = get_venue_stats(venue)
    home_stats = get_team_stats(home_team)
    away_stats = get_team_stats(away_team)
    
    # Get historical context
    stats = get_historical_stats()
    h2h = stats.get("head_to_head", {}).get(home_team, {}).get(away_team, {})
    home_at_venue = stats.get("team_at_venue", {}).get(home_team, {}).get(venue, {})
    away_at_venue = stats.get("team_at_venue", {}).get(away_team, {}).get(venue, {})
    
    h2h_str = f"{home_team} {h2h.get('wins', '?')}-{h2h.get('losses', '?')} {away_team} ({h2h.get('matches', '?')} matches)" if h2h else "N/A"
    
    team_stats = {
        "home_avg": home_stats["avg_score"],
        "away_avg": away_stats["avg_score"],
        "h2h": h2h_str,
        "home_win_rate": home_stats.get("win_rate", 0.5),
        "away_win_rate": away_stats.get("win_rate", 0.5),
        "home_at_venue_avg": home_at_venue.get("avg_score", "N/A"),
        "away_at_venue_avg": away_at_venue.get("avg_score", "N/A"),
        "home_at_venue_matches": home_at_venue.get("matches", 0),
        "away_at_venue_matches": away_at_venue.get("matches", 0),
    }
    
    # Get AI ensemble prediction
    result = await get_ensemble_prediction(
        match_name=event_name,
        home_team=home_team,
        away_team=away_team,
        venue=venue,
        market_type=opp["market_type"],
        selection=opp["selection"],
        odds=opp["odds"],
        line=opp.get("line"),
        live_score=live_score,
        venue_stats=venue_stats,
        team_stats=team_stats,
    )
    
    return result


async def evaluate_and_trade(opp: dict, ensemble_result: dict) -> Optional[dict]:
    """Evaluate ensemble result and decide whether to trade."""
    edge = ensemble_result.get("edge", 0)
    ensemble_prob = ensemble_result.get("ensemble_prob", 0)
    consensus = ensemble_result.get("consensus_score", 0)
    models_agreed = ensemble_result.get("models_agreed", 0)
    models_total = ensemble_result.get("models_total", 0)
    
    # Decision logic
    should_trade = (
        edge >= MIN_EDGE
        and ensemble_prob >= MIN_CONFIDENCE
        and consensus >= 0.3
        and models_agreed >= max(1, models_total // 2)
    )
    
    if not should_trade:
        return None
    
    # Calculate position size
    kelly_size = kelly_criterion(ensemble_prob, opp["odds"])
    if kelly_size < 0.10:
        return None
    
    # Save ensemble decision
    decision = {
        "match_id": opp["event_id"],
        "market_type": opp["market_type"],
        "selection": opp["selection"],
        "ensemble_prob": ensemble_prob,
        "consensus_score": consensus,
        "models_agreed": models_agreed,
        "models_total": models_total,
        "decision": "TRADE" if should_trade else "SKIP",
        "edge": edge,
        "kelly_size": round(kelly_size, 2),
        "reasoning": ensemble_result.get("reasoning", ""),
    }
    db.save_ensemble_decision(decision)
    
    if not should_trade:
        return None
    
    # Execute trade
    trade = {
        "match_id": opp["event_id"],
        "market_type": opp["market_type"],
        "selection": opp["selection"],
        "side": "back",  # always backing value
        "odds": opp["odds"],
        "stake": round(kelly_size, 2),
        "mode": TRADING_MODE,
        "status": "pending",
    }
    
    if TRADING_MODE == "demo":
        trade["status"] = "open"
        trade["cloudbet_ref"] = f"demo_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db.save_trade(trade)
        print(f"  [DEMO TRADE] {opp['selection']} @ {opp['odds']} | "
              f"stake={kelly_size:.2f} | edge={edge:.1%} | prob={ensemble_prob:.1%}")
    else:
        # Live mode - place on Cloudbet
        from odds_fetcher import place_bet_cloudbet
        result = await place_bet_cloudbet(
            opp["event_id"], opp["market_type"], opp["selection"],
            kelly_size, opp["odds"]
        )
        if result and result.get("status") == "SUCCESS":
            trade["cloudbet_ref"] = result.get("refId", "")
            trade["status"] = "open"
            db.save_trade(trade)
            print(f"  [LIVE TRADE] {opp['selection']} @ {opp['odds']} | "
                  f"stake={kelly_size:.2f} | ref={trade['cloudbet_ref']}")
        else:
            trade["status"] = "failed"
            db.save_trade(trade)
            print(f"  [TRADE FAILED] {result}")
    
    return trade


async def scan_and_trade():
    """Main loop: fetch odds, analyze, and trade."""
    print(f"\n{'='*60}")
    print(f"  Cricket Trading Engine - {TRADING_MODE.upper()} MODE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Fetch all IPL events
    events = await fetch_ipl_events()
    if not events:
        print("  No IPL events found")
        return
    
    print(f"  Found {len(events)} IPL events")
    
    total_opportunities = 0
    total_trades = 0
    
    for ev in events:
        event_id = str(ev.get("id", ""))
        event_name = ev.get("name", "")
        status = ev.get("status", "")
        
        if status != "TRADING":
            continue
        
        # Fetch detailed odds
        event_data = await fetch_event_odds(event_id)
        if not event_data:
            continue
        
        opportunities = parse_match_odds(event_data)
        if not opportunities:
            print(f"  {event_name}: No active markets")
            continue
        
        print(f"\n  {event_name}: {len(opportunities)} markets")
        total_opportunities += len(opportunities)
        
        for opp in opportunities:
            # Analyze with AI ensemble
            ensemble_result = await analyze_opportunity(opp)
            if not ensemble_result:
                continue
            
            # Evaluate and potentially trade
            trade = await evaluate_and_trade(opp, ensemble_result)
            if trade:
                total_trades += 1
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
    
    print(f"\n  Summary: {total_opportunities} opportunities analyzed, {total_trades} trades placed")


async def run_single_scan():
    """Run a single scan cycle."""
    db.init_db()
    await scan_and_trade()


if __name__ == "__main__":
    asyncio.run(run_single_scan())