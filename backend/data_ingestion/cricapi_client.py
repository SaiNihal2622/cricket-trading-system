"""
CricAPI Integration (cricketdata.org)
Real-time cricket data via official REST API.

Free tier: 100 requests/day
Endpoints used:
  - /currentMatches  → live match list
  - /match_info      → match details + scorecard
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List

import httpx

from config.settings import settings
from data_ingestion.live_feed import MatchState

logger = logging.getLogger(__name__)


class CricAPIClient:
    """
    Client for cricketdata.org API.
    
    Get a free API key at: https://cricketdata.org
    Set CRICKET_API_KEY in .env
    """

    BASE_URL = "https://api.cricapi.com/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or settings.CRICKET_API_KEY
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"Accept": "application/json"},
        )
        self._request_count = 0
        self._daily_limit = 100  # free tier

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def get_live_matches(self) -> List[dict]:
        """
        Fetch all currently live cricket matches.
        Returns list of match dicts with id, teams, status.
        """
        if not self.is_configured:
            logger.debug("CricAPI key not configured, skipping")
            return []

        data = await self._request("/currentMatches", {"apikey": self.api_key})
        if not data or data.get("status") != "success":
            return []

        matches = []
        for m in data.get("data", []):
            # Filter for T20/IPL live matches
            match_type = m.get("matchType", "").lower()
            status = m.get("status", "")

            if m.get("matchStarted") and not m.get("matchEnded"):
                teams = m.get("teams", [])
                matches.append({
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "team_a": teams[0] if len(teams) > 0 else "",
                    "team_b": teams[1] if len(teams) > 1 else "",
                    "match_type": match_type,
                    "venue": m.get("venue", ""),
                    "status": status,
                    "date": m.get("date", ""),
                    "score": m.get("score", []),
                })

        logger.info(f"CricAPI: Found {len(matches)} live matches")
        return matches

    async def get_match_scorecard(self, match_id: str) -> Optional[MatchState]:
        """
        Fetch detailed scorecard for a specific match.
        Converts CricAPI response to internal MatchState format.
        """
        if not self.is_configured:
            return None

        data = await self._request("/match_info", {
            "apikey": self.api_key,
            "id": match_id,
        })

        if not data or data.get("status") != "success":
            return None

        match_data = data.get("data", {})
        return self._parse_match_data(match_data, match_id)

    def _parse_match_data(self, data: dict, match_id: str) -> MatchState:
        """Parse CricAPI match_info response into MatchState"""
        state = MatchState()
        state.match_id = match_id

        # Teams
        teams = data.get("teams", [])
        state.team_a = teams[0] if len(teams) > 0 else ""
        state.team_b = teams[1] if len(teams) > 1 else ""

        # Score array: [{inning, r, w, o}, ...]
        scores = data.get("score", [])
        if scores:
            # Most recent innings is first in the array
            current = scores[0]
            state.total_runs = int(current.get("r", 0))
            state.total_wickets = int(current.get("w", 0))
            state.overs = float(current.get("o", 0))

            # Determine innings number
            state.innings = len(scores)

            # Run rate
            if state.overs > 0:
                state.run_rate = round(state.total_runs / state.overs, 2)

            # Target & RRR (2nd innings)
            if len(scores) >= 2:
                first_innings = scores[-1]  # last element = 1st innings
                state.target = int(first_innings.get("r", 0)) + 1
                runs_needed = max(0, state.target - state.total_runs)
                overs_remaining = max(0.1, 20 - state.overs)
                state.required_run_rate = round(runs_needed / overs_remaining, 2)

            # Powerplay runs (if still in PP)
            if state.overs <= 6:
                state.powerplay_runs = state.total_runs

        # Batsmen (from scorecard if available)
        batsmen = data.get("bpisBatting", []) or data.get("batsman", [])
        if isinstance(batsmen, list):
            for i, bat in enumerate(batsmen[:2]):
                if isinstance(bat, dict):
                    name = bat.get("name", bat.get("batsman", ""))
                    runs = int(bat.get("r", bat.get("runs", 0)))
                    balls = int(bat.get("b", bat.get("balls", 0)))
                    if i == 0:
                        state.current_batsman_1 = name
                        state.batsman_1_runs = runs
                        state.batsman_1_balls = balls
                    else:
                        state.current_batsman_2 = name
                        state.batsman_2_runs = runs
                        state.batsman_2_balls = balls

        # Bowler
        bowlers = data.get("bpisBowling", []) or data.get("bowler", [])
        if isinstance(bowlers, list) and bowlers:
            bowler = bowlers[0] if isinstance(bowlers[0], dict) else {}
            state.current_bowler = bowler.get("name", bowler.get("bowler", ""))
            state.bowler_wickets = int(bowler.get("w", bowler.get("wickets", 0)))
            state.bowler_runs = int(bowler.get("r", bowler.get("runs_conceded", 0)))

        # Status
        if data.get("matchEnded"):
            state.status = "completed"
        elif data.get("matchStarted"):
            state.status = "live"
        else:
            state.status = "upcoming"

        state.timestamp = datetime.utcnow().isoformat()
        return state

    async def get_ipl_matches(self) -> List[dict]:
        """
        Fetch IPL-specific current/recent matches.
        Filters the live match list for IPL tournament.
        """
        all_matches = await self.get_live_matches()
        return [
            m for m in all_matches
            if "ipl" in m.get("name", "").lower()
            or "indian premier league" in m.get("name", "").lower()
            or m.get("match_type") == "t20"
        ]

    async def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make API request with rate limiting"""
        if self._request_count >= self._daily_limit:
            logger.warning(f"CricAPI daily limit reached ({self._daily_limit})")
            return None

        try:
            resp = await self.client.get(f"{self.BASE_URL}{endpoint}", params=params)
            self._request_count += 1

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning("CricAPI rate limit hit")
                return None
            else:
                logger.error(f"CricAPI error {resp.status_code}: {resp.text[:200]}")
                return None

        except httpx.TimeoutException:
            logger.warning(f"CricAPI timeout on {endpoint}")
            return None
        except Exception as e:
            logger.error(f"CricAPI request error: {e}")
            return None

    async def close(self):
        await self.client.aclose()

    def get_usage(self) -> dict:
        """Return current API usage stats"""
        return {
            "requests_used": self._request_count,
            "daily_limit": self._daily_limit,
            "remaining": self._daily_limit - self._request_count,
            "is_configured": self.is_configured,
        }
