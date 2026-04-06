"""
Cricket Stats Aggregator

Fetches live and historical cricket data from free public sources:
1. Cricbuzz (unofficial JSON endpoints — no API key needed)
2. CricAPI (100 calls/day free tier — optional)
3. Embedded historical IPL player/team averages

Used by the Trading Agent to enrich decision-making with real player data.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Embedded Historical IPL Averages ──────────────────────────────────────────
# Source: public IPL stats (2019-2024, T20 format)
# Batting strike rates for top IPL batsmen
BATSMAN_STRIKE_RATES = {
    "rohit sharma": 136, "virat kohli": 130, "shubman gill": 138,
    "hardik pandya": 142, "ms dhoni": 135, "ravindra jadeja": 120,
    "suryakumar yadav": 170, "kl rahul": 132, "rishabh pant": 148,
    "david warner": 140, "quinton de kock": 137, "faf du plessis": 135,
    "ishan kishan": 133, "devdutt padikkal": 125, "tilak varma": 140,
    "yashasvi jaiswal": 158, "ruturaj gaikwad": 134, "ajinkya rahane": 120,
    "ab de villiers": 152, "jos buttler": 148, "jonny bairstow": 140,
    "jason roy": 143, "travis head": 155, "nicholas pooran": 148,
    "sanju samson": 139, "andre russell": 172, "sunil narine": 163,
    "pat cummins": 148, "mitchell starc": 110, "bumrah": 100,
}

# Team batting averages (runs per over in T20 at different phases)
TEAM_PHASE_AVG = {
    "mumbai indians":      {"pp": 9.2, "mid": 7.8, "death": 10.5},
    "chennai super kings": {"pp": 8.5, "mid": 8.0, "death": 10.0},
    "kolkata knight riders":{"pp": 9.0,"mid": 7.9, "death": 10.8},
    "royal challengers bengaluru": {"pp": 9.5, "mid": 8.2, "death": 10.3},
    "rajasthan royals":    {"pp": 9.3, "mid": 8.1, "death": 10.2},
    "delhi capitals":      {"pp": 8.8, "mid": 7.6, "death": 10.0},
    "punjab kings":        {"pp": 9.1, "mid": 7.7, "death": 10.4},
    "sunrisers hyderabad": {"pp": 8.7, "mid": 7.5, "death": 10.1},
    "gujarat titans":      {"pp": 8.6, "mid": 7.8, "death": 9.8},
    "lucknow super giants":{"pp": 8.4, "mid": 7.6, "death": 9.7},
    # Aliases
    "rcb": {"pp": 9.5, "mid": 8.2, "death": 10.3},
    "mi":  {"pp": 9.2, "mid": 7.8, "death": 10.5},
    "csk": {"pp": 8.5, "mid": 8.0, "death": 10.0},
    "kkr": {"pp": 9.0, "mid": 7.9, "death": 10.8},
    "rr":  {"pp": 9.3, "mid": 8.1, "death": 10.2},
    "dc":  {"pp": 8.8, "mid": 7.6, "death": 10.0},
    "pbks":{"pp": 9.1, "mid": 7.7, "death": 10.4},
    "srh": {"pp": 8.7, "mid": 7.5, "death": 10.1},
    "gt":  {"pp": 8.6, "mid": 7.8, "death": 9.8},
    "lsg": {"pp": 8.4, "mid": 7.6, "death": 9.7},
}

# Head-to-head win percentage (team_a vs team_b, last 5 years IPL)
H2H = {
    ("mumbai indians", "chennai super kings"): 0.51,
    ("mumbai indians", "kolkata knight riders"): 0.55,
    ("royal challengers bengaluru", "chennai super kings"): 0.45,
    ("rajasthan royals", "kolkata knight riders"): 0.50,
}


class CricketStatsService:
    """
    Fetches and caches cricket data from multiple free sources.
    Falls back gracefully if any source is unavailable.
    """

    CRICBUZZ_BASE = "https://www.cricbuzz.com"
    # Try multiple live-match API endpoints in order (Cricbuzz changes these)
    # All JSON APIs return 404 as of Apr 2026 — Cricbuzz is now fully CSR.
    # We rely on HTML scraping only. RoyalBook provides live match data.
    CRICBUZZ_LIVE_URLS = []  # disabled — all return 404
    CRICBUZZ_LIVE_HTML = "https://www.cricbuzz.com/cricket-match/live-scores"
    CRICBUZZ_MATCH = "https://www.cricbuzz.com/api/cricket-match/{match_id}/scorecard"

    def __init__(self, cricapi_key: str = ""):
        self._cricapi_key = cricapi_key
        self._cache: dict = {}
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if not self._client or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=10.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/html",
                    "Referer": "https://www.cricbuzz.com/",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Live Matches ──────────────────────────────────────────────────────────

    async def get_live_ipl_matches(self) -> list:
        """
        Fetch live IPL matches — tries multiple Cricbuzz API endpoints,
        then falls back to scraping the HTML live scores page.
        """
        client = await self.get_client()

        # ── Try JSON endpoints first ──────────────────────────────────────────
        for url in self.CRICBUZZ_LIVE_URLS:
            try:
                resp = await client.get(url, timeout=8.0)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        continue
                    matches = self._parse_cricbuzz_json(data)
                    if matches is not None:
                        logger.info(f"Cricbuzz JSON ({url}): {len(matches)} live IPL matches")
                        return matches
            except Exception as e:
                logger.debug(f"Cricbuzz endpoint {url} failed: {e}")

        # ── Fallback: scrape HTML live scores page ────────────────────────────
        try:
            resp = await client.get(self.CRICBUZZ_LIVE_HTML, timeout=10.0)
            if resp.status_code == 200:
                matches = self._parse_cricbuzz_html(resp.text)
                logger.info(f"Cricbuzz HTML scrape: {len(matches)} live IPL matches")
                return matches
        except Exception as e:
            logger.debug(f"Cricbuzz HTML scrape failed: {e}")

        return []

    def _parse_cricbuzz_json(self, data: dict) -> Optional[list]:
        """Parse Cricbuzz live-matches JSON response."""
        matches = []
        try:
            for m in data.get("typeMatches", []):
                for series in m.get("seriesMatches", []):
                    for match in series.get("seriesAdWrapper", {}).get("matches", []):
                        mi = match.get("matchInfo", {})
                        series_name = mi.get("seriesName", "").lower()
                        if "ipl" in series_name or "indian premier" in series_name:
                            matches.append({
                                "match_id": mi.get("matchId"),
                                "team_a": mi.get("team1", {}).get("teamName", ""),
                                "team_b": mi.get("team2", {}).get("teamName", ""),
                                "series": mi.get("seriesName"),
                                "venue": mi.get("venueInfo", {}).get("ground", ""),
                                "state": mi.get("state", ""),
                            })
            return matches
        except Exception:
            return None

    def _parse_cricbuzz_html(self, html: str) -> list:
        """Extract IPL match cards from Cricbuzz live scores HTML."""
        from bs4 import BeautifulSoup
        matches = []
        ipl_keywords = ["ipl", "indian premier", "t20"]
        try:
            soup = BeautifulSoup(html, "lxml")
            for card in soup.select(".cb-mtch-lst, .cb-match-item, [class*='match']"):
                text = card.get_text(" ", strip=True).lower()
                if any(k in text for k in ipl_keywords):
                    teams_els = card.select("[class*='team'], [class*='tname']")
                    team_names = [e.get_text(strip=True) for e in teams_els if e.get_text(strip=True)]
                    if len(team_names) >= 2:
                        matches.append({
                            "match_id": None,
                            "team_a": team_names[0],
                            "team_b": team_names[1],
                            "series": "IPL",
                            "venue": "",
                            "state": "live",
                        })
        except Exception as e:
            logger.debug(f"HTML parse error: {e}")
        return matches

    async def get_match_scorecard(self, cricbuzz_id: int) -> dict:
        """
        Fetch detailed scorecard from Cricbuzz — batsmen, bowlers, partnerships.
        """
        try:
            client = await self.get_client()
            resp = await client.get(
                f"https://www.cricbuzz.com/api/cricket-match/{cricbuzz_id}/scorecard",
                timeout=8.0,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"Cricbuzz scorecard failed for {cricbuzz_id}: {e}")
        return {}

    async def get_live_score_cricbuzz(self) -> Optional[dict]:
        """
        Get the first live IPL match score from Cricbuzz.
        Tries multiple API endpoints, returns enriched state dict.
        """
        try:
            client = await self.get_client()
            data = None
            for url in self.CRICBUZZ_LIVE_URLS:
                try:
                    resp = await client.get(url, timeout=8.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        break
                except Exception:
                    continue
            if not data:
                return None

            for match_type in data.get("typeMatches", []):
                for series in match_type.get("seriesMatches", []):
                    for match in series.get("seriesAdWrapper", {}).get("matches", []):
                        mi = match.get("matchInfo", {})
                        ms = match.get("matchScore", {})
                        series_name = mi.get("seriesName", "").lower()

                        if "ipl" not in series_name and "indian premier" not in series_name:
                            continue

                        # Parse innings score
                        inn1 = ms.get("team1Score", {}).get("inngs1", {})
                        inn2 = ms.get("team2Score", {}).get("inngs1", {})

                        # Determine batting team
                        team_a = mi.get("team1", {}).get("teamSName", mi.get("team1", {}).get("teamName", ""))
                        team_b = mi.get("team2", {}).get("teamSName", mi.get("team2", {}).get("teamName", ""))

                        # Current batting innings
                        if inn2.get("runs") is not None and inn1.get("runs") is not None:
                            # 2nd innings
                            inn = inn2
                            batting = team_b
                            innings_num = 2
                            target = inn1.get("runs", 0) + 1
                        elif inn1.get("runs") is not None:
                            inn = inn1
                            batting = team_a
                            innings_num = 1
                            target = 0
                        else:
                            continue

                        runs    = inn.get("runs", 0) or 0
                        wickets = inn.get("wickets", 0) or 0
                        overs   = float(inn.get("overs", 0) or 0)
                        crr     = round(runs / overs, 2) if overs > 0 else 0.0
                        rrr     = 0.0
                        if innings_num == 2 and target > 0 and overs < 20:
                            remaining_balls = max(1, (20 - overs) * 6)
                            runs_needed = target - runs
                            rrr = round((runs_needed / remaining_balls) * 6, 2) if runs_needed > 0 else 0.0

                        return {
                            "match_id": str(mi.get("matchId", 1)),
                            "team_a": team_a,
                            "team_b": team_b,
                            "innings": innings_num,
                            "total_runs": runs,
                            "total_wickets": wickets,
                            "overs": overs,
                            "run_rate": crr,
                            "required_run_rate": rrr,
                            "target": target,
                            "batting_team": batting,
                            "venue": mi.get("venueInfo", {}).get("ground", ""),
                            "status": mi.get("status", "Live"),
                            "source": "cricbuzz_live",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
        except Exception as e:
            logger.debug(f"Cricbuzz live score failed: {e}")
        return None

    # ── Player / Team Stats ──────────────────────────────────────────────────

    def get_batsman_sr(self, name: str) -> float:
        """Get historical strike rate for a batsman. Returns 120 as default."""
        return BATSMAN_STRIKE_RATES.get(name.lower().strip(), 120.0)

    def get_team_phase_avg(self, team: str, phase: str) -> float:
        """
        Get average runs per over for a team in a given phase.
        phase: 'pp' (powerplay), 'mid' (middle), 'death'
        """
        team_lower = team.lower().strip()
        stats = TEAM_PHASE_AVG.get(team_lower)
        if not stats:
            # Try partial match
            for key in TEAM_PHASE_AVG:
                if key in team_lower or team_lower in key:
                    stats = TEAM_PHASE_AVG[key]
                    break
        if not stats:
            stats = {"pp": 8.8, "mid": 7.8, "death": 10.0}
        return stats.get(phase, 8.0)

    def get_h2h_win_pct(self, team_a: str, team_b: str) -> float:
        """Get historical head-to-head win percentage for team_a vs team_b."""
        a, b = team_a.lower(), team_b.lower()
        # Check both orderings
        key = (a, b)
        if key in H2H:
            return H2H[key]
        key_rev = (b, a)
        if key_rev in H2H:
            return 1.0 - H2H[key_rev]
        return 0.50  # 50-50 default

    def get_player_form_multiplier(self, batsmen: list) -> float:
        """
        Calculate a run-rate multiplier based on current batsmen's strike rates.
        Returns ratio vs average (1.0 = average, >1.0 = strong batting).
        """
        if not batsmen:
            return 1.0
        srs = [self.get_batsman_sr(b) for b in batsmen if b]
        if not srs:
            return 1.0
        avg_sr = sum(srs) / len(srs)
        return avg_sr / 130.0  # 130 is baseline IPL strike rate

    def enrich_match_state(self, state: dict) -> dict:
        """
        Add derived stats to match state for better ML/decision engine accuracy.
        """
        team_a = state.get("team_a", "")
        team_b = state.get("team_b", "")
        overs  = float(state.get("overs", 0))
        innings = int(state.get("innings", 1))

        # Determine phase
        if overs <= 6:
            phase = "pp"
        elif overs <= 15:
            phase = "mid"
        else:
            phase = "death"

        batting_team = state.get("batting_team", team_a)

        # Enrich with team stats
        state["team_phase_avg"]  = self.get_team_phase_avg(batting_team, phase)
        state["h2h_win_pct_a"]   = self.get_h2h_win_pct(team_a, team_b)
        state["phase"]           = phase

        # Batsman form
        batsmen = [
            state.get("current_batsman_1", ""),
            state.get("current_batsman_2", ""),
        ]
        state["batsman_form_mult"] = self.get_player_form_multiplier(batsmen)

        return state


# Global singleton
cricket_stats = CricketStatsService()
