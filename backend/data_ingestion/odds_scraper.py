"""
Live Odds Scraper — Monitors and ingests real-time betting odds.

Responsible for:
- Scraping odds from configured sources (e.g., Betfair, external API, or mock)
- Detecting odds volatility and spreads
- Publishing latest odds to Redis for the Trading Agent

In mock mode, generates realistic odds that react to match state
(runs, wickets, overs, run rate) so the autonomous agent has
meaningful odds movement to trade on.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict

from config.settings import settings

logger = logging.getLogger(__name__)


class OddsScraper:
    """
    Monitors market odds.
    In mock mode, generates odds that respond to live match state.
    """

    def __init__(self):
        self._running = False
        self._loop_interval = getattr(settings, 'ODDS_SCRAPE_INTERVAL', 5)
        self._current_odds: Dict[str, dict] = {}
        self._rng = random.Random(99)
        # Persistent state for random walk
        self._odds_a = 1.85
        self._odds_b = 2.10

    async def start(self):
        self._running = True
        logger.info(f"OddsScraper started (interval: {self._loop_interval}s)")
        await self._poll_loop()

    async def stop(self):
        self._running = False
        logger.info("OddsScraper stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._fetch_odds()
            except Exception as e:
                logger.error(f"Odds scrape error: {e}")
            await asyncio.sleep(self._loop_interval)

    def attach_exchange(self, exchange):
        """Attach live exchange for real odds scraping."""
        self._exchange = exchange

    async def _fetch_odds(self):
        """Fetch odds — RoyalBook live first, reactive mock as fallback."""
        try:
            from database.redis_client import get_redis, RedisCache
            redis = await get_redis()
            cache = RedisCache(redis)
            match_id = 1

            # ── Live path: Direct API Scraper ──────────────────────────────
            exchange = getattr(self, '_exchange', None)
            if exchange and exchange._logged_in:
                try:
                    # In a real implementation we would fetch match_id dynamically
                    raw = await exchange.get_match_odds(str(match_id))
                    
                    if raw and "back_a" in raw:
                        odds = {
                            "match_id": match_id,
                            "team_a": "Team A",
                            "team_b": "Team B",
                            "team_a_odds": raw["back_a"],
                            "team_b_odds": raw["back_b"],
                            "implied_prob_a": round(1 / raw["back_a"] * 100, 2),
                            "implied_prob_b": round(1 / raw["back_b"] * 100, 2),
                            "overround": round(1/raw["back_a"] + 1/raw["back_b"], 4),
                            "source": "stake_api_live",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        self._current_odds[str(match_id)] = odds
                        await cache.set_odds(match_id, odds)
                        await cache.publish("odds:updates", odds)
                        return
                except Exception as e:
                    logger.warning(f"Exchange scrape failed, falling back to mock: {e}")

            # ── Fallback: reactive mock ───────────────────────────────────
            match_state = await cache.get_match_state(match_id) or {}
            odds = self._generate_reactive_odds(match_state)
            self._current_odds[str(match_id)] = odds
            await cache.set_odds(match_id, odds)
            await cache.publish("odds:updates", odds)
        except Exception as e:
            logger.debug(f"Odds fetch error: {e}")

    def _generate_reactive_odds(self, state: dict) -> dict:
        """
        Generate odds that react to match state.

        Logic:
        - High run rate / low wickets → batting team favoured (lower odds)
        - Wickets falling / low run rate → bowling team favoured
        - Death overs with high required rate → chasing team odds rise
        - Random walk volatility layered on top for realism
        """
        overs = float(state.get("overs", 0))
        runs = int(state.get("total_runs", 0))
        wickets = int(state.get("total_wickets", 0))
        crr = float(state.get("run_rate", 0))
        rrr = float(state.get("required_run_rate", 0))
        innings = int(state.get("innings", 1))
        target = int(state.get("target", 0))

        if overs == 0 and runs == 0:
            # Pre-match / no data — return baseline
            self._odds_a = 1.85
            self._odds_b = 2.10
        else:
            # Calculate team A "strength" signal from match state
            # Positive = team A (batting) doing well
            strength = 0.0

            if innings == 1:
                # First innings: high CRR = batting team strong
                projected = runs + crr * max(0, 20 - overs)
                par = 165
                strength = (projected - par) / 80  # -1 to +1 range roughly
                # Wicket penalty
                strength -= wickets * 0.08
            else:
                # Second innings (chasing)
                if target > 0 and rrr > 0:
                    # Chasing comfortably = batting team strong
                    rr_edge = (crr - rrr) / max(rrr, 1)
                    strength = rr_edge * 0.5
                    strength -= wickets * 0.1
                    # Death overs pressure
                    if overs >= 15:
                        strength -= 0.1

            # Clamp strength
            strength = max(-0.8, min(0.8, strength))

            # Convert strength to odds movement
            # Positive strength → lower odds_a (more favoured)
            target_a = 1.50 + (1.0 - strength) * 1.0  # range ~0.7 to 2.3
            target_b = 1.50 + (1.0 + strength) * 1.0

            # Smooth towards target (don't jump instantly)
            alpha = 0.15  # smoothing factor
            self._odds_a = self._odds_a * (1 - alpha) + target_a * alpha
            self._odds_b = self._odds_b * (1 - alpha) + target_b * alpha

            # Add random walk volatility
            vol_a = self._rng.gauss(0, 0.02)
            vol_b = self._rng.gauss(0, 0.02)
            self._odds_a += vol_a
            self._odds_b += vol_b

        # Clamp to valid range
        self._odds_a = round(max(1.05, min(10.0, self._odds_a)), 2)
        self._odds_b = round(max(1.05, min(10.0, self._odds_b)), 2)

        return {
            "match_id": 1,
            "team_a_odds": self._odds_a,
            "team_b_odds": self._odds_b,
            "implied_prob_a": round((1 / self._odds_a) * 100, 2),
            "implied_prob_b": round((1 / self._odds_b) * 100, 2),
            "overround": round(1 / self._odds_a + 1 / self._odds_b, 4),
            "source": "mock_reactive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_latest_odds(self, match_id: str) -> dict:
        return self._current_odds.get(str(match_id), {})
