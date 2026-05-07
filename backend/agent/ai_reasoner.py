import logging
import json
import asyncio
from typing import Optional, List, Dict
import httpx

logger = logging.getLogger(__name__)

class AIReasoner:
    """
    Heterogeneous AI Consensus Reasoner.
    Uses Gemini, Groq, and NVIDIA for a 3-family vote.
    """

    SYSTEM_PROMPT = """You are an expert cricket trading analyst.
Provide a clear trading decision (ENTER|LOSS_CUT|BOOKSET|SESSION|HOLD).
Be data-driven. Weigh risk vs reward.
Respond ONLY in JSON:
{
    "action": "ENTER|LOSS_CUT|BOOKSET|SESSION|HOLD",
    "confidence": 0-1.0,
    "team": "team name or null",
    "reasoning": "1 sentence explanation"
}"""

    def __init__(self, api_key: str = "", model: str = ""):
        # Compatibility signature, we pull keys from settings in the loop if needed
        # but for now we rely on the caller passing the initialized settings or similar.
        self._available = True # Will check keys dynamically in get_heterogeneous_consensus
        from config.settings import settings
        self.settings = settings
        self.groq_key = settings.GROQ_API_KEY
        self.nvidia_key = settings.NVIDIA_API_KEY
        self.gemini_key = settings.GEMINI_API_KEY
        self.mimo_key = settings.MIMO_API_KEY

    @property
    def is_available(self) -> bool:
        return any([self.mimo_key, self.nvidia_key, self.gemini_key, self.groq_key])

    async def multi_pass_reason(self, **kwargs) -> dict:
        """Alias for compatibility with existing code, routing to consensus."""
        return await self.get_heterogeneous_consensus(**kwargs)

    async def get_heterogeneous_consensus(
        self,
        match_state: dict,
        odds: dict,
        ml_prediction: dict,
        decision_engine_output: dict,
        position: Optional[dict] = None,
        telegram_signals: list = None,
    ) -> dict:
        """Parallel call to all enabled providers and consensus logic."""
        if not self.is_available:
            return {"action": "HOLD", "confidence": 0, "reasoning": "AI Unavailable", "source": "rule_engine"}

        context = self._build_context_str(match_state, odds, ml_prediction, decision_engine_output, position, telegram_signals)
        
        tasks = []
        if self.mimo_key:
            tasks.append(self._call_mimo(context))
        if self.nvidia_key:
            tasks.append(self._call_nvidia(context))
        
        # User requested Mimo/Nvidia, using Gemini/Groq as secondary/consensus voters if available
        if self.gemini_key:
            tasks.append(self._call_gemini(context))
        if self.groq_key:
            tasks.append(self._call_groq(context))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []
        for r in results:
            if isinstance(r, dict) and "action" in r:
                valid_results.append(r)
            else:
                logger.debug(f"AI Provider failed: {r}")

        if not valid_results:
            return {"action": "HOLD", "confidence": 0, "reasoning": "All AI providers failed", "source": "rule_engine"}

        # Consensus Logic
        actions = [r["action"] for r in valid_results]
        majority_action = max(set(actions), key=actions.count)
        
        # Unanimity check for ENTER (Sniper Mode)
        if majority_action == "ENTER" and len(valid_results) > 1:
            if any(r["action"] != "ENTER" for r in valid_results):
                return {
                    "action": "HOLD",
                    "confidence": 0.5,
                    "reasoning": f"Rejected: No consensus for ENTER. Votes: {actions}",
                    "source": "heterogeneous_consensus"
                }

        avg_conf = sum(float(r.get("confidence", 0)) for r in valid_results) / len(valid_results)
        combined_reasoning = " | ".join([r.get("reasoning", "") for r in valid_results[:2]])

        return {
            "source": "heterogeneous_consensus",
            "action": majority_action,
            "confidence": avg_conf,
            "team": valid_results[0].get("team"),
            "reasoning": combined_reasoning,
            "providers": len(valid_results)
        }

    async def _call_groq(self, context: str) -> dict:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.settings.GROQ_MODEL,
            "messages": [{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": context}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        return await self._http_post(url, headers, payload)

    async def _call_nvidia(self, context: str) -> dict:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.nvidia_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.settings.NVIDIA_MODEL,
            "messages": [{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": context}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        return await self._http_post(url, headers, payload)

    async def _call_gemini(self, context: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions?key={self.gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self.settings.GEMINI_MODEL,
            "messages": [{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": context}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        return await self._http_post(url, headers, payload)

    async def _call_mimo(self, context: str) -> dict:
        """Call custom MIMO model endpoint."""
        # Ensure url has chat/completions
        base = self.settings.MIMO_BASE_URL.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.mimo_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.settings.MIMO_MODEL,
            "messages": [{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": context}],
            "temperature": 0.2
        }
        # Note: Mimo might not support response_format json_object natively in some versions, 
        # but our SYSTEM_PROMPT enforces JSON.
        return await self._http_post(url, headers, payload)

    async def _http_post(self, url, headers, payload) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return json.loads(resp.json()["choices"][0]["message"]["content"])
                return {}
            except Exception as e:
                logger.error(f"HTTP Post error: {e}")
                return {}

    def _build_context_str(self, state, odds, ml, decision, position, telegram) -> str:
        return f"""
Match: {state.get('team_a')} vs {state.get('team_b')}
Score: {state.get('total_runs')}/{state.get('total_wickets')} ({state.get('overs')} ov)
Odds: A={odds.get('team_a_odds')} B={odds.get('team_b_odds')}
ML Prob: {ml.get('win_probability')}
Signals: {decision.get('signal')} ({decision.get('reasoning')})
Telegram: {len(telegram or [])} signals active.
"""
