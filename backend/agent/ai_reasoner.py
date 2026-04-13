"""
AI Reasoner — Gemini Flash-powered decision reasoning for cricket trading.

Uses Google Gemini 2.0 Flash (fastest, lowest latency) to reason over
complex match situations where rule-based logic is insufficient.

Called when:
- Decision confidence is borderline (40-60%)
- Multiple conflicting signals
- Critical moments (death overs, key wickets, powerplay end)
- Market overreaction detected (odds moved >15% in 1 over)
"""
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


class AIReasoner:
    """
    LLM reasoning layer using Google Gemini 2.0 Flash.

    Gemini Flash is chosen for:
    - Sub-second latency (< 800ms typical)
    - Free tier: 15 RPM, 1M tokens/day
    - Superior cricket domain knowledge vs Groq
    - JSON mode support
    """

    SYSTEM_PROMPT = """You are an elite cricket trading analyst specializing in IPL T20 markets on RoyalBook exchange.

You have deep expertise in:
- T20 match momentum and phase analysis (powerplay 1-6, middle 7-15, death 16-20)
- RoyalBook market microstructure (back/lay spreads, session lines, bookmaker)
- Kelly criterion and bankroll management
- Loss cut timing (when to hedge vs hold)
- Bookset opportunities (lock guaranteed profit)
- Session/fancy market value (powerplay runs, over-specific lines)

You receive live match data and must make a precise trading recommendation.

CRITICAL RULES:
1. In powerplay (overs 1-6): teams average 52 runs — bet YES on powerplay if strong start (>8 RPO after 3 overs)
2. Death overs (16-20): volatility is highest — only enter with 80%+ confidence
3. Loss cut: if backed team odds rose >20% from entry AND wicket just fell → LOSS_CUT immediately
4. Bookset: if you backed at X and odds are now at 0.7X or lower → BOOKSET to lock profit
5. Never fight momentum — if score/wicket combination is catastrophic, don't HOLD, act

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
    "action": "ENTER|LOSS_CUT|BOOKSET|SESSION|HOLD",
    "confidence": 0-100,
    "team": "team name or null",
    "market": "match_odds|bookmaker|session",
    "reasoning": "2-3 sentence explanation with specific numbers",
    "risk_notes": "specific risk factors",
    "key_factors": ["factor1", "factor2", "factor3"],
    "bookset_odds": null,
    "session_call": null
}"""

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._available = False
        self._genai = None

        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
                self._model_instance = genai.GenerativeModel(
                    model_name=self.model,
                    generation_config={
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "max_output_tokens": 512,
                        "response_mime_type": "application/json",
                    },
                    system_instruction=self.SYSTEM_PROMPT,
                )
                self._available = True
                logger.info(f"AI Reasoner (Gemini) initialized — model: {model}")
            except ImportError:
                logger.warning("google-generativeai not installed. Run: pip install google-generativeai")
            except Exception as e:
                logger.warning(f"Gemini init error: {e}")
        else:
            logger.info("AI Reasoner: No GEMINI_API_KEY — using rule-based fallback")

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
        Get Gemini AI reasoning for current situation.
        Returns structured decision with reasoning.
        Latency target: < 1 second.
        """
        if not self._available:
            return self._fallback_reasoning(decision_engine_output)

        prompt = self._build_prompt(
            match_state, odds, ml_prediction,
            decision_engine_output, position, telegram_signals
        )

        try:
            response = await self._call_gemini(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Gemini AI Reasoner error: {e}")
            return self._fallback_reasoning(decision_engine_output)

    def _build_prompt(self, state, odds, ml, decision, position, telegram) -> str:
        """Build context-rich prompt for Gemini"""
        overs    = float(state.get("overs", 0))
        runs     = int(state.get("total_runs", 0))
        wickets  = int(state.get("total_wickets", 0))
        rr       = float(state.get("run_rate", 0))
        rrr      = float(state.get("required_run_rate", 0))
        target   = int(state.get("target", 0))
        innings  = int(state.get("innings", 1))
        phase    = "POWERPLAY" if overs <= 6 else ("DEATH" if overs >= 16 else "MIDDLE")

        parts = []

        parts.append(f"""=== LIVE MATCH ===
{state.get('team_a', 'Team A')} vs {state.get('team_b', 'Team B')}
Score: {runs}/{wickets} in {overs:.1f} overs | Phase: {phase}
Innings: {innings} | Target: {target if target else 'N/A (1st innings)'}
Run Rate: {rr:.2f} | Required RR: {rrr:.2f if rrr else 'N/A'}
Last ball: {state.get('last_ball', '-')} | Wicket just fell: {state.get('last_ball') == 'W'}""")

        parts.append(f"""=== MARKET ODDS ===
{state.get('team_a', 'Team A')}: BACK {odds.get('team_a_odds', 0):.2f}
{state.get('team_b', 'Team B')}: BACK {odds.get('team_b_odds', 0):.2f}
Bookmaker: {odds.get('bookmaker', {})}""")

        parts.append(f"""=== ML PREDICTION ===
Win Probability (batting team): {ml.get('win_probability', 0.5):.1%}
Momentum Score: {ml.get('momentum_score', 0.5):.1%}
Confidence: {ml.get('confidence', 0.5):.1%}""")

        parts.append(f"""=== STRATEGY ENGINE ===
Signal: {decision.get('signal', 'HOLD')} | Confidence: {decision.get('confidence', 0):.0%}
Urgency: {decision.get('urgency', 'LOW')}
Reasoning: {decision.get('reasoning', 'N/A')}""")

        if position:
            entry_odds   = position.get('entry_odds', 0)
            current_odds = odds.get('team_a_odds', 0) if position.get('backed_team') == state.get('team_a') else odds.get('team_b_odds', 0)
            odds_change  = ((current_odds - entry_odds) / entry_odds * 100) if entry_odds > 0 else 0
            parts.append(f"""=== OPEN POSITION ===
Backed: {position.get('backed_team')} @ {entry_odds:.2f}
Stake: ₹{position.get('entry_stake', 0)} | Status: {position.get('status')}
Current odds: {current_odds:.2f} ({odds_change:+.1f}% from entry)
Unrealized P&L: ₹{position.get('unrealized_pnl', 0):.0f}""")
        else:
            parts.append("=== POSITION: None (flat) ===")

        if telegram:
            tg_lines = [
                f"  [{s.get('channel', '?')}] {s.get('sentiment', '?').upper()}: {s.get('text', '')[:80]}"
                for s in (telegram or [])[:5]
            ]
            parts.append(f"=== TELEGRAM SIGNALS ===\n" + "\n".join(tg_lines))

        parts.append("Analyze this situation and give your trading recommendation.")
        return "\n\n".join(parts)

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API asynchronously"""
        response = await self._model_instance.generate_content_async(prompt)
        return response.text

    def _parse_response(self, response: str) -> dict:
        """Parse Gemini JSON response"""
        try:
            # Strip any markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            return {
                "source":       "gemini",
                "action":       result.get("action", "HOLD"),
                "confidence":   min(100, max(0, result.get("confidence", 50))) / 100,
                "team":         result.get("team"),
                "market":       result.get("market", "match_odds"),
                "reasoning":    result.get("reasoning", ""),
                "risk_notes":   result.get("risk_notes", ""),
                "key_factors":  result.get("key_factors", []),
                "bookset_odds": result.get("bookset_odds"),
                "session_call": result.get("session_call"),
            }
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Gemini response parse error: {e} — raw: {response[:200]}")
            return self._fallback_reasoning({})

    def _fallback_reasoning(self, decision: dict) -> dict:
        """Fallback when Gemini is not available"""
        return {
            "source":      "rule_engine",
            "action":      decision.get("signal", "HOLD"),
            "confidence":  decision.get("confidence", 0),
            "team":        decision.get("entry_team"),
            "market":      "match_odds",
            "reasoning":   decision.get("reasoning", "Rule-based decision"),
            "risk_notes":  "",
            "key_factors": list(decision.get("factors", {}).keys())[:5],
            "bookset_odds": None,
            "session_call": None,
        }
