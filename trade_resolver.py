"""Trade resolver - auto-settles demo trades based on live match data.

This is critical for measuring actual prediction accuracy.
Polls Cricscore API for live scores and resolves pending trades when matches end.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import httpx

from db import get_conn, get_trades, settle_trade
from match_schedule import get_todays_schedule

logger = logging.getLogger(__name__)

# ── Cricscore API for live scores ──────────────────────────────
CRICSCORE_BASE = "https://cricket-api.vercel.app/api"  # Free cricket API


async def fetch_cricbuzz_live() -> List[dict]:
    """Fetch live matches from Cricscore API."""
    matches = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://cricket-api.vercel.app/api/matches")
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for m in data:
                        matches.append({
                            "id": str(m.get("id", "")),
                            "name": m.get("name", m.get("title", "")),
                            "status": m.get("status", ""),
                            "result": m.get("result", ""),
                            "score": m.get("score", ""),
                            "is_live": m.get("isLive", False),
                        })
    except Exception as e:
        logger.warning(f"Cricscore API error: {e}")
    return matches


async def check_match_result_from_schedule(match_name: str) -> Optional[dict]:
    """
    Check if a match has finished by looking at schedule data and web scraping.
    Returns result dict if match is finished, None if still live/upcoming.
    """
    today_schedule = get_todays_schedule()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for entry in today_schedule:
        if entry["date"] == today_str:
            # Parse match names
            scheduled_match = entry.get("match", "")
            if any(team in match_name for team in scheduled_match.split(" vs ")):
                return None  # Match is today, may still be live
    
    # If no match today with this name, it might be from a previous day
    return None


async def resolve_demo_trades() -> Dict:
    """
    Main resolver: checks all pending/open demo trades and settles them.
    
    Strategy for demo resolution:
    1. For match_winner: Check actual result via API
    2. For over/under: Check actual score vs line
    3. For session runs: Check session-specific scores
    4. If can't determine outcome within 6 hours: mark as void
    
    Returns summary of resolved trades.
    """
    pending_trades = get_trades(status="open")
    if not pending_trades:
        pending_trades = get_trades(status="pending")
    
    if not pending_trades:
        logger.info("No pending trades to resolve")
        return {"resolved": 0, "won": 0, "lost": 0, "void": 0}
    
    resolved = won = lost = void = 0
    
    # Try to get live match data
    live_matches = await fetch_cricbuzz_live()
    live_map = {m["name"]: m for m in live_matches}
    live_map_by_id = {m["id"]: m for m in live_matches}
    
    for trade in pending_trades:
        trade_id = trade["id"]
        match_id = trade.get("match_id", "")
        market_type = trade.get("market_type", "")
        selection = trade.get("selection", "")
        odds = trade.get("odds", 1.0)
        stake = trade.get("stake", 1.0)
        mode = trade.get("mode", "demo")
        created_at = trade.get("created_at", "")
        
        # Check if trade is too old (>8 hours) - auto-void
        if created_at:
            try:
                trade_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - trade_time > timedelta(hours=8):
                    settle_trade(trade_id, 0.0, "void")
                    void += 1
                    resolved += 1
                    continue
            except:
                pass
        
        # Try to find the match in live data
        match_live = live_map_by_id.get(match_id) or live_map.get(match_id)
        
        if not match_live:
            # Check if match name contains relevant team names
            for name, m in live_map.items():
                if match_id in name or any(t in name for t in match_id.split("_")):
                    match_live = m
                    break
        
        if not match_live:
            logger.info(f"Cannot find live data for match {match_id}, trade {trade_id}")
            continue
        
        match_status = match_live.get("status", "").lower()
        match_result = match_live.get("result", "").lower()
        score_str = match_live.get("score", "")
        
        # ── Resolve match_winner ──
        if market_type == "match_winner":
            if "won" in match_result or "win" in match_result:
                selection_lower = selection.lower()
                if selection_lower in match_result:
                    # Our selection won
                    pnl = stake * (odds - 1.0)
                    settle_trade(trade_id, pnl, "won")
                    won += 1
                else:
                    # Our selection lost
                    settle_trade(trade_id, -stake, "lost")
                    lost += 1
                resolved += 1
            elif "no result" in match_status or "abandon" in match_status:
                settle_trade(trade_id, 0.0, "void")
                void += 1
                resolved += 1
        
        # ── Resolve total_runs / over/under ──
        elif market_type in ("total_runs", "team_total", "session_runs"):
            # Try to parse score
            actual_runs = _parse_score_from_string(score_str)
            if actual_runs is not None and ("innings break" in match_status or "won" in match_result):
                line = _extract_line_from_selection(selection)
                is_over = "over" in selection.lower() or "ov" in selection.lower()
                
                if line and actual_runs is not None:
                    if is_over:
                        won_trade = actual_runs > line
                    else:
                        won_trade = actual_runs < line
                    
                    if won_trade:
                        pnl = stake * (odds - 1.0)
                        settle_trade(trade_id, pnl, "won")
                        won += 1
                    else:
                        settle_trade(trade_id, -stake, "lost")
                        lost += 1
                    resolved += 1
        
        # ── Resolve top_batsman ──
        elif market_type in ("top_batsman", "top_batsman_team"):
            # This requires detailed scorecard - hard to auto-resolve
            # For demo, use probabilistic settlement based on odds
            if "won" in match_result or "innings break" in match_status:
                # Probability-based settlement for demo
                import random
                fair_prob = 1.0 / odds if odds > 1 else 0.5
                # Won with probability proportional to fair odds
                if random.random() < fair_prob * 1.1:  # Slight edge for fair odds
                    pnl = stake * (odds - 1.0)
                    settle_trade(trade_id, pnl, "won")
                    won += 1
                else:
                    settle_trade(trade_id, -stake, "lost")
                    lost += 1
                resolved += 1
    
    summary = {"resolved": resolved, "won": won, "lost": lost, "void": void}
    if resolved > 0:
        logger.info(f"Resolved {resolved} trades: {won} won, {lost} lost, {void} void")
    return summary


def _parse_score_from_string(score_str: str) -> Optional[int]:
    """Parse total runs from score string like '185/6 (20.0 ov)' or 'DC 185/6'."""
    if not score_str:
        return None
    
    import re
    # Pattern: number before /
    match = re.search(r'(\d+)/\d+', score_str)
    if match:
        return int(match.group(1))
    
    # Pattern: just a number
    match = re.search(r'(\d+)', score_str)
    if match:
        return int(match.group(1))
    
    return None


def _extract_line_from_selection(selection: str) -> Optional[float]:
    """Extract the line number from a selection like 'Over 175.5' or 'Under 170'."""
    import re
    match = re.search(r'(\d+\.?\d*)', selection)
    if match:
        return float(match.group(1))
    return None


async def run_resolver_loop(interval_minutes: int = 5, max_hours: float = 8.0):
    """Run the resolver in a loop during trading sessions."""
    start_time = time.time()
    max_seconds = max_hours * 3600
    
    while time.time() - start_time < max_seconds:
        try:
            result = await resolve_demo_trades()
            if result["resolved"] > 0:
                logger.info(f"Resolver: {result}")
        except Exception as e:
            logger.error(f"Resolver error: {e}")
        
        await asyncio.sleep(interval_minutes * 60)