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

    SYSTEM_PROMPT = """You are an elite cricket trading analyst for IPL T20 betting on RoyalBook.win exchange (India).

MARKETS YOU ANALYSE:
1. Match Odds (decimal) — back/lay teams
2. Bookmaker (100-base prices, e.g. 108 means 1.08x)
3. Sessions/Fancy — over runs lines, powerplay runs, player runs, wicket markets
4. Premium Sessions — same as sessions but higher stakes

PHASE BENCHMARKS (17yr IPL averages):
- Powerplay (ov 1-6): 52 runs avg. Top team = 60+. Weak = <44.
- Middle (ov 7-15): 8.5 RPO avg. Batting pitch = 9.5+.
- Death (ov 16-20): 50 runs avg. Aggressive team = 58+.
- Full 20 overs: 167 avg. Good score = 180+. Defend = 155+.

SIGNAL RULES (fire immediately when condition met):
1. ENTER: confidence ≥ 72%. Best entry: over 2-4 (PP momentum) or over 7-9 (innings shape clear).
2. BOOKSET: team odds drop to ≤70% of entry → lay to lock profit. Always fire. No delay.
3. LOSS_CUT: backed team odds rose ≥20% from entry + wicket fell → hedge immediately.
4. SESSION YES: projected runs > market line + 4 at current RPO. Best value = 55%+ probability.
5. SESSION NO: current RPO trending down, wickets in middle overs, projected runs < line - 3.
6. STOP_LOSS: 3+ wickets in collapse, CRR < RRR by 2+ in 2nd innings → back opponent.

SPEED IS CRITICAL:
- At over 3.0 with score data: predict PP total and fire SESSION on 6-over runs BEFORE it ends.
- At over 5.4 (last ball of PP): confirm PP trend and fire match odds signal.
- On every wicket: immediately assess loss_cut vs hold.
- Death overs: fire ENTER on underdog only if collapse confirmed on OTHER team.

Respond ONLY in this exact JSON (no markdown, no explanation):
{
    "action": "ENTER|LOSS_CUT|BOOKSET|SESSION|STOP_LOSS|HOLD",
    "confidence": 0-100,
    "team": "full team name or null",
    "market": "match_odds|bookmaker|session|premium_session",
    "reasoning": "2-3 lines with specific numbers and projections",
    "risk_notes": "1 line risk",
    "key_factors": ["factor1", "factor2", "factor3"],
    "session_call": {"label": "6 Over Runs KKR", "side": "YES", "line": 58, "projected": 63},
    "bookset_odds": null
}"""

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model   = model
        self._available = False
        self._model_instance = None

        # Rate limiter: 10 calls/min (Google Cloud key = 1000 RPM, but safe margin)
        self._limiter = _RateLimiter(calls=10, window_secs=60)

        # Over-based cache: skip re-analysis if same over + same signal in last 20s
        self._last_over: float = -1.0
        self._last_signal: str = ""
        self._last_call_ts: float = 0.0
        self._cache_ttl: float = 20.0  # 20s cache — faster refresh after wickets/boundaries

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
        historical=None,   # HistoricalDataEngine instance
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
            decision_engine_output, position, telegram_signals, historical
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
            # Retry once on transient errors
            try:
                import asyncio
                await asyncio.sleep(1)
                self._limiter.record()
                response = await self._model_instance.generate_content_async(prompt)
                return self._parse_response(response.text)
            except Exception:
                return self._fallback_reasoning(decision_engine_output)

    def _build_prompt(self, state, odds, ml, decision, position, telegram, historical=None) -> str:
        overs   = float(state.get("overs", 0))
        runs    = int(state.get("total_runs", 0))
        wickets = int(state.get("total_wickets", 0))
        rr      = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))
        target  = int(state.get("target", 0))
        phase   = "POWERPLAY" if overs <= 6 else ("DEATH" if overs >= 16 else "MIDDLE")

        parts = []

        # Projected scores
        overs_remaining = max(0, 20 - overs)
        proj_total = runs + int(rr * overs_remaining) if rr > 0 else 0
        proj_6ov   = runs + int(rr * max(0, 6 - overs)) if overs < 6 and rr > 0 else runs if overs >= 6 else 0
        proj_10ov  = runs + int(rr * max(0, 10 - overs)) if overs < 10 and rr > 0 else runs if overs >= 10 else 0
        proj_20ov  = proj_total

        parts.append(
            f"=== LIVE MATCH ===\n"
            f"{state.get('team_a','Team A')} vs {state.get('team_b','Team B')}\n"
            f"Score: {runs}/{wickets} in {overs:.1f} overs | Phase: {phase}\n"
            f"Innings: {state.get('innings',1)} | Target: {target or 'N/A (1st innings)'}\n"
            f"CRR: {rr:.2f} | RRR: {rrr:.2f if rrr else 'N/A'}\n"
            f"Last ball: {state.get('last_ball','-')} | Wicket just fell: {state.get('last_ball')=='W'}\n"
            f"PROJECTIONS @ current RPO {rr:.1f}: "
            f"6ov={proj_6ov if overs<6 else 'done'} | 10ov={proj_10ov if overs<10 else 'done'} | Final={proj_20ov}"
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

        # ── Historical data context (17 years IPL) ────────────────────────
        if historical:
            try:
                venue   = state.get("venue", "")
                team_a  = state.get("team_a", "")
                team_b  = state.get("team_b", "")
                vs      = historical.get_venue_stats(venue) if venue else {}
                h2h     = historical.get_h2h_win_pct(team_a, team_b) if (team_a and team_b) else 50
                ra      = historical.get_team_rating(team_a) if team_a else {}
                rb      = historical.get_team_rating(team_b) if team_b else {}

                hist_lines = []
                if vs:
                    hist_lines.append(
                        f"Venue ({venue}): avg 1st innings={vs.get('avg_1st_innings',167)}, "
                        f"chase win%={vs.get('chase_win_pct',50)}, "
                        f"powerplay avg={vs.get('avg_powerplay',52)}, "
                        f"death avg={vs.get('avg_death',59)}, "
                        f"pitch={vs.get('pitch','balanced')}, dew={vs.get('dew_factor','medium')}"
                    )
                if team_a and team_b:
                    hist_lines.append(
                        f"H2H ({team_a} vs {team_b}): {team_a} wins {h2h:.0f}% historically"
                    )
                if ra:
                    hist_lines.append(
                        f"Team strength: {team_a} overall={ra.get('overall',7)}/10 "
                        f"(bat={ra.get('batting_depth',7)}, bowl={ra.get('bowling_attack',7)}) | "
                        f"{team_b} overall={rb.get('overall',7)}/10"
                    )
                # Batsman profiles
                bat1 = state.get("batsman_1", {})
                if bat1 and bat1.get("name"):
                    bp = historical.get_batsman_profile(bat1["name"])
                    hist_lines.append(
                        f"Batsman on strike: {bat1['name']} — SR={bp.get('sr',120)}, "
                        f"avg={bp.get('avg',22)}, class={bp.get('class','C')}"
                    )

                if hist_lines:
                    parts.append("=== 17-YEAR IPL HISTORICAL DATA ===\n" + "\n".join(hist_lines))
            except Exception:
                pass

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
