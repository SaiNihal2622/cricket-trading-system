"""
Live Cricket Data Ingestion Layer
Supports Cricbuzz scraping + extensible to official APIs
"""
import asyncio
import logging
import httpx
import re
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from config.settings import settings
from database.redis_client import get_redis, RedisCache

logger = logging.getLogger(__name__)


class MatchState:
    """Current match state snapshot"""

    def __init__(self):
        self.match_id: str = ""
        self.team_a: str = ""
        self.team_b: str = ""
        self.innings: int = 1
        self.total_runs: int = 0
        self.total_wickets: int = 0
        self.overs: float = 0.0
        self.run_rate: float = 0.0
        self.required_run_rate: float = 0.0
        self.target: int = 0
        self.current_batsman_1: str = ""
        self.current_batsman_2: str = ""
        self.current_bowler: str = ""
        self.batsman_1_runs: int = 0
        self.batsman_1_balls: int = 0
        self.batsman_2_runs: int = 0
        self.batsman_2_balls: int = 0
        self.bowler_wickets: int = 0
        self.bowler_runs: int = 0
        self.powerplay_runs: int = 0
        self.last_ball: str = ""
        self.status: str = "live"
        self.timestamp: str = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "MatchState":
        state = cls()
        for k, v in data.items():
            setattr(state, k, v)
        return state


class CricbuzzScraper:
    """Scrapes live match data from Cricbuzz"""

    BASE_URL = "https://www.cricbuzz.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=httpx.Timeout(15.0),
            follow_redirects=True
        )

    async def get_live_matches(self) -> list[dict]:
        """Fetch list of live matches"""
        try:
            resp = await self.client.get(f"{self.BASE_URL}/cricket-match/live-scores")
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            matches = []
            # Parse live match cards
            match_cards = soup.select("div.cb-mtch-lst.cb-tms-itms")

            for card in match_cards:
                try:
                    link_el = card.select_one("a.cb-lv-scrs-well")
                    if not link_el:
                        continue

                    href = link_el.get("href", "")
                    match_id = self._extract_match_id(href)

                    teams_el = card.select("div.cb-hmscg-tm-nm")
                    team_names = [el.get_text(strip=True) for el in teams_el]

                    status_el = card.select_one("div.cb-text-live")
                    is_live = status_el is not None

                    if match_id and len(team_names) >= 2 and is_live:
                        matches.append({
                            "id": match_id,
                            "team_a": team_names[0] if team_names else "",
                            "team_b": team_names[1] if len(team_names) > 1 else "",
                            "url": f"{self.BASE_URL}{href}",
                            "is_live": is_live
                        })
                except Exception as e:
                    logger.warning(f"Error parsing match card: {e}")
                    continue

            return matches
        except Exception as e:
            logger.error(f"Error fetching live matches: {e}")
            return []

    async def get_match_scorecard(self, match_url: str) -> Optional[MatchState]:
        """Fetch and parse scorecard for a match"""
        try:
            resp = await self.client.get(match_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            state = MatchState()

            # Score
            score_el = soup.select_one("div.cb-min-bat-rw span")
            if score_el:
                score_text = score_el.get_text(strip=True)
                state.total_runs, state.total_wickets = self._parse_score(score_text)

            # Overs
            overs_el = soup.select_one("div.cb-min-inf")
            if overs_el:
                overs_text = overs_el.get_text()
                state.overs = self._parse_overs(overs_text)
                state.run_rate = self._parse_run_rate(overs_text)

            # Batsmen
            batsmen_rows = soup.select("div.cb-min-bat-rw")
            for i, row in enumerate(batsmen_rows[:2]):
                name_el = row.select_one("a")
                runs_el = row.select("span")
                if name_el and runs_el:
                    if i == 0:
                        state.current_batsman_1 = name_el.get_text(strip=True)
                        state.batsman_1_runs = self._safe_int(runs_el[0].get_text())
                        state.batsman_1_balls = self._safe_int(runs_el[1].get_text() if len(runs_el) > 1 else "0")
                    else:
                        state.current_batsman_2 = name_el.get_text(strip=True)
                        state.batsman_2_runs = self._safe_int(runs_el[0].get_text())
                        state.batsman_2_balls = self._safe_int(runs_el[1].get_text() if len(runs_el) > 1 else "0")

            # Bowler
            bowler_rows = soup.select("div.cb-min-bowl-rw")
            if bowler_rows:
                bowler_name_el = bowler_rows[-1].select_one("a")
                if bowler_name_el:
                    state.current_bowler = bowler_name_el.get_text(strip=True)

            state.timestamp = datetime.utcnow().isoformat()
            return state

        except Exception as e:
            logger.error(f"Error fetching scorecard: {e}")
            return None

    def _extract_match_id(self, href: str) -> str:
        match = re.search(r"/(\d+)/", href)
        return match.group(1) if match else ""

    def _parse_score(self, text: str) -> tuple[int, int]:
        match = re.search(r"(\d+)[/-](\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r"(\d+)", text)
        return (int(match.group(1)), 0) if match else (0, 0)

    def _parse_overs(self, text: str) -> float:
        match = re.search(r"(\d+)\.(\d+)\s*ov", text)
        if match:
            return float(f"{match.group(1)}.{match.group(2)}")
        return 0.0

    def _parse_run_rate(self, text: str) -> float:
        match = re.search(r"CRR[:\s]+(\d+\.?\d*)", text)
        return float(match.group(1)) if match else 0.0

    def _safe_int(self, text: str) -> int:
        try:
            return int(re.search(r"\d+", text).group())
        except (AttributeError, ValueError):
            return 0

    async def close(self):
        await self.client.aclose()


class MockLiveFeed:
    """Simulated live feed for development/testing"""

    def __init__(self):
        self._balls = 0  # total balls bowled (integer)
        self._runs = 0
        self._wickets = 0
        import random
        self._rng = random.Random(42)

    def next_ball(self) -> MatchState:
        state = MatchState()
        state.match_id = "MOCK_001"
        state.team_a = "Mumbai Indians"
        state.team_b = "Chennai Super Kings"

        # Simulate a ball
        ball_runs = self._rng.choices(
            [0, 1, 2, 3, 4, 6, -1],  # -1 = wicket
            weights=[30, 25, 15, 5, 15, 7, 3]
        )[0]

        if ball_runs == -1:
            self._wickets += 1
            ball_runs = 0
        else:
            self._runs += ball_runs

        self._balls += 1
        over = self._balls // 6
        ball_in_over = self._balls % 6
        self._over = over + ball_in_over / 10  # e.g., 4.3 = over 4, ball 3

        state.total_runs = self._runs
        state.total_wickets = self._wickets
        state.overs = self._over
        state.run_rate = (self._runs / max(self._balls / 6, 0.1)) if self._balls > 0 else 0
        state.current_batsman_1 = "Rohit Sharma"
        state.current_batsman_2 = "Ishan Kishan"
        state.current_bowler = "Deepak Chahar"
        state.batsman_1_runs = self._runs // 2
        state.batsman_2_runs = self._runs - self._runs // 2
        state.last_ball = str(ball_runs) if ball_runs >= 0 else "W"
        state.innings = 1
        state.powerplay_runs = min(self._runs, 60) if over < 6 else 60

        if over >= 20 or self._wickets >= 10:
            state.status = "completed"
            self._balls = 0
            self._runs = 0
            self._wickets = 0

        return state


class LiveFeedManager:
    """
    Manages real-time data ingestion from all sources.
    
    Priority:
    1. CricAPI (if CRICKET_API_KEY is set)
    2. Cricbuzz scraping (if _use_mock = False)
    3. Mock feed (development default)
    """

    def __init__(self):
        self.scraper = CricbuzzScraper()
        self.mock_feed = MockLiveFeed()
        self.cricapi = None
        self._running = False
        self._subscribers: list = []
        self._active_matches: Dict[str, MatchState] = {}
        self._use_mock = True  # Overridden by CricAPI detection
        self._data_source = "mock"

        # Auto-detect CricAPI
        try:
            from data_ingestion.cricapi_client import CricAPIClient
            self.cricapi = CricAPIClient()
            if self.cricapi.is_configured:
                self._use_mock = False
                self._data_source = "cricapi"
                logger.info("CricAPI key detected — using live data source")
            else:
                logger.info("No CricAPI key — using mock feed")
        except ImportError:
            logger.info("CricAPI client not available — using mock feed")

    async def start(self):
        self._running = True
        logger.info(f"LiveFeedManager started (source: {self._data_source})")
        await self._poll_loop()

    async def stop(self):
        self._running = False
        await self.scraper.close()
        if self.cricapi:
            await self.cricapi.close()
        logger.info("LiveFeedManager stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                if self._data_source == "cricapi":
                    await self._fetch_cricapi_data()
                else:
                    # Cricbuzz JSON APIs are dead (404 since 2026).
                    # Try HTML scraping → mock fallback.
                    # Primary live data comes from RoyalBook scraper.
                    got_live = False
                    try:
                        got_live = await self._fetch_cricbuzz_json()
                    except Exception:
                        pass
                    if not got_live:
                        try:
                            await self._fetch_live_data()
                        except Exception:
                            await self._fetch_mock_data()
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
            await asyncio.sleep(settings.MATCH_POLL_INTERVAL)

    async def _fetch_cricbuzz_json(self) -> bool:
        """
        Fetch live IPL data from Cricbuzz unofficial JSON API.
        No API key required. Returns True if data was obtained.
        """
        try:
            from data_ingestion.cricket_stats import cricket_stats
            live = await cricket_stats.get_live_score_cricbuzz()
            if not live:
                return False

            # Convert to MatchState
            state = MatchState()
            state.match_id    = str(live.get("match_id", "1"))
            state.team_a      = live.get("team_a", "")
            state.team_b      = live.get("team_b", "")
            state.innings     = int(live.get("innings", 1))
            state.total_runs  = int(live.get("total_runs", 0))
            state.total_wickets = int(live.get("total_wickets", 0))
            state.overs       = float(live.get("overs", 0))
            state.run_rate    = float(live.get("run_rate", 0))
            state.required_run_rate = float(live.get("required_run_rate", 0))
            state.target      = int(live.get("target", 0))
            state.status      = live.get("status", "live")
            state.timestamp   = live.get("timestamp", datetime.utcnow().isoformat())

            # Enrich with player stats
            state_dict = cricket_stats.enrich_match_state(state.to_dict())
            for k, v in state_dict.items():
                if hasattr(state, k):
                    setattr(state, k, v)

            self._active_matches[state.match_id] = state
            self._data_source = "cricbuzz_live"

            redis = await get_redis()
            cache = RedisCache(redis)
            await cache.set_match_state(1, state.to_dict())
            await cache.publish("match:updates", {"match_id": 1, "state": state.to_dict()})

            return True
        except Exception as e:
            logger.debug(f"Cricbuzz JSON fetch failed: {e}")
            return False

    async def _fetch_cricapi_data(self):
        """Fetch from CricAPI (cricketdata.org)"""
        matches = await self.cricapi.get_live_matches()
        if not matches:
            # Fallback to mock if no live matches
            await self._fetch_mock_data()
            return

        for match in matches[:3]:
            try:
                state = await self.cricapi.get_match_scorecard(match["id"])
                if state:
                    self._active_matches[state.match_id] = state

                    redis = await get_redis()
                    cache = RedisCache(redis)
                    await cache.set_match_state(match["id"], state.to_dict())
                    await cache.publish("match:updates", {
                        "match_id": match["id"],
                        "state": state.to_dict()
                    })
            except Exception as e:
                logger.warning(f"Error fetching CricAPI match {match['id']}: {e}")

    async def _fetch_mock_data(self):
        """Simulate live ball-by-ball data"""
        state = self.mock_feed.next_ball()
        self._active_matches[state.match_id] = state

        # Cache in Redis
        redis = await get_redis()
        cache = RedisCache(redis)
        await cache.set_match_state(1, state.to_dict())
        await cache.publish("match:updates", {
            "match_id": 1,
            "state": state.to_dict()
        })

    async def _fetch_live_data(self):
        """Fetch from Cricbuzz scraping (fallback)"""
        matches = await self.scraper.get_live_matches()
        for match in matches[:3]:  # Limit concurrent fetches
            try:
                state = await self.scraper.get_match_scorecard(match["url"])
                if state:
                    state.match_id = match["id"]
                    state.team_a = match["team_a"]
                    state.team_b = match["team_b"]
                    self._active_matches[state.match_id] = state

                    redis = await get_redis()
                    cache = RedisCache(redis)
                    await cache.set_match_state(match["id"], state.to_dict())
                    await cache.publish("match:updates", {
                        "match_id": match["id"],
                        "state": state.to_dict()
                    })
            except Exception as e:
                logger.warning(f"Error fetching match {match['id']}: {e}")

    def get_active_matches(self) -> Dict[str, dict]:
        return {k: v.to_dict() for k, v in self._active_matches.items()}

    def get_match_state(self, match_id: str) -> Optional[MatchState]:
        return self._active_matches.get(match_id)

    def get_data_source(self) -> str:
        """Returns current data source: cricapi, cricbuzz, mock"""
        return self._data_source

