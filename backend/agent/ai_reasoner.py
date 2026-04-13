"""
AI Reasoner — Gemini Flash-powered decision reasoning for cricket trading.

Rate limiting: Free tier = 15 RPM, 1M tokens/day.
Strategy:
- Token bucket: max 10 calls/min (safe margin below 15 RPM limit)
- Over cache: skip re-analysis if same over + same signal as last call
- Only called for borderline (40-60% confidence) / conflicting / critical moments
  → In practice ~3-6 Gemini calls per match, well within daily limits
"""
import logging
import json
import time
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Token bucket: max `calls` per `window_secs`."""

    def __init__(self, calls: int = 10, window_secs: int = 60):
        self._max    = calls
        self._window = window_secs
        self._log: deque = deque()  # timestamps of recent calls

    def can_call(self) -> bool:
        now = time.monotonic()
        # Remove calls older than the window
        while self._log and (now - self._log[0]) > self._window:
            self._log.popleft()
        return len(self._log) < self._max

    def record(self):
        self._log.append(time.monotonic())

    def seconds_until_free(self) -> float:
        if self.can_call():
            return 0.0
        now = time.monotonic()
        return max(0.0, self._window - (now - self._log[0]))


class AIReasoner:
    """
    Gemini 2.0 Flash reasoning layer for cricket trading.

    Chosen for:
    - Sub-second latency (< 800ms typical)
    - Free tier: 15 RPM, 1M tokens/day (plenty for match analysis)
    - Superior cricket domain knowledge
    - Native JSON mode
    """

    SYSTEM_PROMPT = """You are an elite cricket trading analyst specializing in IPL T20 markets on RoyalBook exchange.

You have deep expertise in:
- T20 match momentum and phase analysis (powerplay 1-6, middle 7-15, death 16-20)
- RoyalBook markets: Match Odds (back/lay), Bookmaker (100-based prices), Sessions/Fancy
- Kelly criterion and bankroll management for Indian exchanges
- Loss cut timing (when to hedge vs hold through a wicket)
- Bookset opportunities (lock guaranteed profit both sides)
- Session/fancy market value (powerplay runs, over-specific lines)

CRITICAL RULES:
1. Powerplay (overs 1-6): avg IPL powerplay = 52 runs. If score pace > 9 RPO after 3 overs → SESSION YES is value.
2. Death overs (16-20): highest volatility. Only ENTER with 80%+ confidence. BOOKSET aggressively.
3. Loss cut: if backed team odds rose >20% from entry AND wicket just fell → LOSS_CUT immediately.
4. Bookset: odds compressed to 70% of entry or below → BOOKSET to lock guaranteed profit.
5. Bookmaker market: if bookmaker price differs >8% from match odds → BOOKMAKER_EDGE opportunity.
6. Never fight 3+ wicket collapse — always LOSS_CUT or HOLD with very high caution.
7. 2nd innings chasing: if CRR < RRR by >1.5 after over 10 → backing fielding team has value.

Respond ONLY in this exact JSON (no markdown):
{
    "action": "ENTER|LOSS_CUT|BOOKSET|SESSION|HOLD",
    "confidence": 0-100,
    "team": "team name or null",
    "market": "match_odds|bookmaker|session",
    "reasoning": "2-3 sentences with specific numbers",
    "risk_notes": "specific risk factors",
    "key_factors": ["factor1", "factor2", "factor3"],
    "bookset_odds": null,
    "session_call": null
}"""

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model   = model
        self._available = False
        self._model_instance = None

        # Rate limiter: 10 calls/min (free tier is 15 RPM — 33% safety margin)
        self._limiter = _RateLimiter(calls=10, window_secs=60)

        # Over-based cache: skip re-analysis if same over + same signal in last 60s
        self._last_over: float = -1.0
        self._last_signal: str = ""
        self._last_call_ts: float = 0.0
        self._cache_ttl: float = 45.0  # don't re-analyze same over within 45s

        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._model_instance = genai.GenerativeModel(
                    model_name=model,
                    generation_config={
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "max_output_tokens": 512,
                        "response_mime_type": "application/json",
                    },
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._available = True
                logger.info(f"Gemini AI Reasoner ready — model: {model} | limit: 10 RPM")
            except ImportError:
                logger.warning("google-generativeai not installed. pip install google-generativeai")
            except Exception as e:
                logger.warning(f"Gemini init error: {e}")
        else:
            logger.info("AI Reasoner: No GEMINI_API_KEY — rule-based fallback active")

    @property
    def is_available(self) -> bool:
        return self._available

    async def reason(
        self,
        match_state: dict,
        odds: dict,
        ml_prediction: dict,
        decision_engine_output: dict,
        position: Optional[dict] = None,
        telegram_signals: list = None,
    ) -> dict:
        """
        Analyze situation and return a structured trading recommendation.
        Respects rate limits — returns rule-engine fallback if rate limited.
        """
        if not self._available:
            return self._fallback_reasoning(decision_engine_output)

        current_over = float(match_state.get("overs", 0))
        current_sig  = decision_engine_output.get("signal", "HOLD")
        now          = time.monotonic()

        # Cache: same over + same signal within 45s → no need to call Gemini again
        if (
            abs(current_over - self._last_over) < 0.2
            and current_sig == self._last_signal
            and (now - self._last_call_ts) < self._cache_ttl
        ):
            logger.debug(f"Gemini cache hit (over {current_over:.1f}, {current_sig}) — skipping API call")
            return self._fallback_reasoning(decision_engine_output)

        # Rate limit check
        if not self._limiter.can_call():
            wait = self._limiter.seconds_until_free()
            logger.warning(f"Gemini rate limit reached — fallback (free in {wait:.0f}s)")
            return self._fallback_reasoning(decision_engine_output)

        prompt = self._build_prompt(
            match_state, odds, ml_prediction,
            decision_engine_output, position, telegram_signals
        )

        try:
            self._limiter.record()
            response = await self._model_instance.generate_content_async(prompt)
            result   = self._parse_response(response.text)

            # Update cache
            self._last_over    = current_over
            self._last_signal  = current_sig
            self._last_call_ts = now

            logger.info(
                f"Gemini → {result['action']} ({result['confidence']:.0%}) "
                f"| {result['reasoning'][:80]} "
                f"| rate bucket: {10 - len(self._limiter._log)}/10 remaining"
            )
            return result

        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return self._fallback_reasoning(decision_engine_output)

    def _build_prompt(self, state, odds, ml, decision, position, telegram) -> str:
        overs   = float(state.get("overs", 0))
        runs    = int(state.get("total_runs", 0))
        wickets = int(state.get("total_wickets", 0))
        rr      = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))
        target  = int(state.get("target", 0))
        phase   = "POWERPLAY" if overs <= 6 else ("DEATH" if overs >= 16 else "MIDDLE")

        parts = []

        parts.append(
            f"=== LIVE MATCH ===\n"
            f"{state.get('team_a','Team A')} vs {state.get('team_b','Team B')}\n"
            f"Score: {runs}/{wickets} in {overs:.1f} overs | Phase: {phase}\n"
            f"Innings: {state.get('innings',1)} | Target: {target or 'N/A (1st innings)'}\n"
            f"CRR: {rr:.2f} | RRR: {rrr:.2f if rrr else 'N/A'}\n"
            f"Last ball: {state.get('last_ball','-')} | Wicket just fell: {state.get('last_ball')=='W'}"
        )

        bm = odds.get("bookmaker", {})
        bm_str = ""
        if bm:
            bm_str = "\nBookmaker: " + ", ".join(
                f"{k}: {v.get('back','-')}" for k, v in bm.items() if isinstance(v, dict)
            )
        parts.append(
            f"=== ODDS ===\n"
            f"{state.get('team_a','Team A')}: BACK {odds.get('team_a_odds',0):.2f}\n"
            f"{state.get('team_b','Team B')}: BACK {odds.get('team_b_odds',0):.2f}"
            f"{bm_str}"
        )

        parts.append(
            f"=== ML PREDICTION ===\n"
            f"Win Prob (batting team): {ml.get('win_probability',0.5):.1%}\n"
            f"Momentum: {ml.get('momentum_score',0.5):.1%} | Confidence: {ml.get('confidence',0.5):.1%}"
        )

        parts.append(
            f"=== RULE ENGINE ===\n"
            f"Signal: {decision.get('signal','HOLD')} | Confidence: {decision.get('confidence',0):.0%}\n"
            f"Urgency: {decision.get('urgency','LOW')}\n"
            f"Reasoning: {decision.get('reasoning','N/A')}"
        )

        if position:
            entry  = position.get("entry_odds", 0)
            curr_o = odds.get("team_a_odds", 0) if position.get("backed_team") == state.get("team_a") else odds.get("team_b_odds", 0)
            chg    = ((curr_o - entry) / entry * 100) if entry > 0 else 0
            parts.append(
                f"=== OPEN POSITION ===\n"
                f"Backed: {position.get('backed_team')} @ {entry:.2f}\n"
                f"Stake: ₹{position.get('entry_stake',0)} | Current: {curr_o:.2f} ({chg:+.1f}%)\n"
                f"Unrealized P&L: ₹{position.get('unrealized_pnl',0):.0f}"
            )
        else:
            parts.append("=== POSITION: Flat (no open position) ===")

        if telegram:
            tg = "\n".join(
                f"  [{s.get('channel','?')}] {s.get('signal_type','?')}: {s.get('raw_text','')[:70]}"
                for s in (telegram or [])[:4]
            )
            parts.append(f"=== TELEGRAM TIPS ===\n{tg}")

        parts.append("Analyze and recommend. Output JSON only.")
        return "\n\n".join(parts)

    def _parse_response(self, text: str) -> dict:
        try:
            t = text.strip()
            if t.startswith("```"):
                t = t.split("```")[1]
                if t.startswith("json"):
                    t = t[4:]
            r = json.loads(t)
            return {
                "source":       "gemini",
                "action":       r.get("action", "HOLD"),
                "confidence":   min(100, max(0, r.get("confidence", 50))) / 100,
                "team":         r.get("team"),
                "market":       r.get("market", "match_odds"),
                "reasoning":    r.get("reasoning", ""),
                "risk_notes":   r.get("risk_notes", ""),
                "key_factors":  r.get("key_factors", []),
                "bookset_odds": r.get("bookset_odds"),
                "session_call": r.get("session_call"),
            }
        except Exception as e:
            logger.warning(f"Gemini parse error: {e} | raw: {text[:150]}")
            return self._fallback_reasoning({})

    def _fallback_reasoning(self, decision: dict) -> dict:
        return {
            "source":       "rule_engine",
            "action":       decision.get("signal", "HOLD"),
            "confidence":   decision.get("confidence", 0),
            "team":         decision.get("entry_team"),
            "market":       "match_odds",
            "reasoning":    decision.get("reasoning", "Rule-based decision"),
            "risk_notes":   "",
            "key_factors":  list(decision.get("factors", {}).keys())[:5],
            "bookset_odds": None,
            "session_call": None,
        }
