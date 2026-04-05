"""
AI Reasoner — LLM-powered decision reasoning for edge cases.

Uses Groq (Llama 3.3) to provide natural-language reasoning
over complex match situations where rule-based logic is insufficient.

The reasoner is called when:
- Decision confidence is borderline (40-60%)
- Multiple conflicting signals
- Critical moments (death overs, key wickets)
"""
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


class AIReasoner:
    """
    LLM reasoning layer using Groq API.
    
    Provides expert-level cricket trading analysis
    by reasoning over all available signals.
    """

    SYSTEM_PROMPT = """You are an expert cricket trading analyst with 10+ years of experience in T20/IPL markets.

You receive:
- Live match state (score, overs, wickets, run rate)
- Current odds for both teams
- ML model prediction (win probability, momentum)
- Strategy engine signals (loss cut, bookset, session)
- Telegram channel sentiment
- Current position (if any)

Your job:
1. Analyze the situation holistically
2. Consider match phase, momentum, market overreaction
3. Recommend a specific action with reasoning
4. Rate confidence on a 0-100 scale

Respond ONLY in this JSON format:
{
    "action": "ENTER|LOSS_CUT|BOOKSET|SESSION|HOLD",
    "confidence": 0-100,
    "team": "team name or null",
    "reasoning": "2-3 sentence explanation",
    "risk_notes": "any risk concerns",
    "key_factors": ["factor1", "factor2"]
}"""

    def __init__(self, api_key: str = "", model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self._available = False

        if self.api_key:
            self._available = True
            logger.info(f"AI Reasoner initialized (model: {model})")
        else:
            logger.info("AI Reasoner: No GROQ_API_KEY — using rule-based fallback")

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
        Get AI reasoning for current situation.
        
        Returns structured decision with reasoning.
        """
        if not self._available:
            return self._fallback_reasoning(decision_engine_output)

        prompt = self._build_prompt(
            match_state, odds, ml_prediction,
            decision_engine_output, position, telegram_signals
        )

        try:
            response = await self._call_groq(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"AI Reasoner error: {e}")
            return self._fallback_reasoning(decision_engine_output)

    def _build_prompt(
        self, state, odds, ml, decision, position, telegram
    ) -> str:
        """Build context prompt for the LLM"""
        parts = []

        # Match state
        parts.append(f"""CURRENT MATCH STATE:
- {state.get('team_a', 'Team A')} vs {state.get('team_b', 'Team B')}
- Score: {state.get('total_runs', 0)}/{state.get('total_wickets', 0)} in {state.get('overs', 0)} overs
- Innings: {state.get('innings', 1)}
- Run Rate: {state.get('run_rate', 0):.2f}
- Required RR: {state.get('required_run_rate', 0):.2f}
- Target: {state.get('target', 0)}
- Last Ball: {state.get('last_ball', '-')}""")

        # Odds
        parts.append(f"""CURRENT ODDS:
- {state.get('team_a', 'Team A')}: {odds.get('team_a_odds', 0):.2f}
- {state.get('team_b', 'Team B')}: {odds.get('team_b_odds', 0):.2f}""")

        # ML
        parts.append(f"""ML PREDICTION:
- Win Probability (batting team): {ml.get('win_probability', 0.5):.1%}
- Momentum Score: {ml.get('momentum_score', 0.5):.1%}
- Model: {ml.get('model_version', 'unknown')}""")

        # Decision engine
        parts.append(f"""STRATEGY ENGINE SAYS:
- Signal: {decision.get('signal', 'HOLD')}
- Confidence: {decision.get('confidence', 0):.0%}
- Reasoning: {decision.get('reasoning', 'N/A')}
- Urgency: {decision.get('urgency', 'LOW')}""")

        # Position
        if position:
            parts.append(f"""CURRENT POSITION:
- Backed: {position.get('backed_team')} @ {position.get('entry_odds')}
- Stake: ₹{position.get('entry_stake', 0)}
- Unrealized P&L: ₹{position.get('unrealized_pnl', 0):.2f}
- Status: {position.get('status')}""")
        else:
            parts.append("CURRENT POSITION: None (no open position)")

        # Telegram
        if telegram:
            signals_text = "\n".join([
                f"  - {s.get('channel', '?')}: {s.get('sentiment', '?')} ({s.get('text', '')[:80]})"
                for s in (telegram or [])[:5]
            ])
            parts.append(f"TELEGRAM SIGNALS:\n{signals_text}")

        return "\n\n".join(parts) + "\n\nWhat should I do? Analyze and recommend."

    async def _call_groq(self, prompt: str) -> str:
        """Call Groq API"""
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
            )

            if resp.status_code != 200:
                raise Exception(f"Groq API error {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> dict:
        """Parse LLM JSON response"""
        try:
            result = json.loads(response)
            return {
                "source": "ai_reasoner",
                "action": result.get("action", "HOLD"),
                "confidence": min(100, max(0, result.get("confidence", 50))) / 100,
                "team": result.get("team"),
                "reasoning": result.get("reasoning", ""),
                "risk_notes": result.get("risk_notes", ""),
                "key_factors": result.get("key_factors", []),
            }
        except json.JSONDecodeError:
            return self._fallback_reasoning({})

    def _fallback_reasoning(self, decision: dict) -> dict:
        """Fallback when LLM is not available"""
        return {
            "source": "rule_engine",
            "action": decision.get("signal", "HOLD"),
            "confidence": decision.get("confidence", 0),
            "team": decision.get("entry_team"),
            "reasoning": decision.get("reasoning", "Rule-based decision"),
            "risk_notes": "",
            "key_factors": list(decision.get("factors", {}).keys())[:5],
        }
