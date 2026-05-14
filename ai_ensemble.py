"""Multi-model AI ensemble for cricket match predictions.

Uses NVIDIA Nemotron (via MIMO), Gemini, and Grok to generate predictions.
Each model independently analyzes the match data and returns a probability.
The ensemble combines them using weighted averaging based on historical accuracy.
"""
import json
import asyncio
import httpx
import re
from typing import Optional
from config import (
    NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    GROK_API_KEY, GROK_BASE_URL, GROK_MODEL,
    OPENAI_API_KEY,
    MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL,
    NVIDIA_FALLBACK_MODELS,
)

# Model weights (updated dynamically based on performance)
MODEL_WEIGHTS = {
    "nvidia_nemotron": 0.25,
    "gemini_flash": 0.25,
    "grok_3": 0.25,
    "mimo_omni": 0.25,
}

SYSTEM_PROMPT = """You are an expert cricket betting analyst for IPL matches. 
Given match data, odds, and context, provide a precise probability estimate.

You MUST respond in this exact JSON format:
{
    "probability": 0.XX (number between 0 and 1),
    "confidence": 0.XX (number between 0 and 1),
    "reasoning": "brief explanation",
    "key_factors": ["factor1", "factor2", "factor3"]
}

Rules:
- probability = your estimated true probability of the outcome occurring
- confidence = how confident you are in your estimate (0.5 = guessing, 1.0 = certain)
- Consider: team form, venue stats, head-to-head, player matchups, pitch conditions, toss impact
- For team totals: consider venue averages, bowling attack quality, batting lineup depth
- For session/powerplay markets: historical powerplay scores at venue
- Be calibrated: if you say 70%, it should win ~70% of the time
- Higher accuracy = higher confidence. If data is limited, lower your confidence.
"""


async def call_nvidia(prompt: str) -> Optional[dict]:
    """Call NVIDIA API with model fallback chain: deepseek-v4-pro → mistral-large → nemotron."""
    if not NVIDIA_API_KEY:
        return None
    
    models_to_try = [NVIDIA_MODEL] + NVIDIA_FALLBACK_MODELS
    
    for model_id in models_to_try:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_id,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    short_name = model_id.split("/")[-1][:20]
                    print(f"[NVIDIA] Using {model_id}")
                    return _parse_response(content, "nvidia_nemotron")
                else:
                    print(f"[NVIDIA] {model_id} returned {resp.status_code}, trying next...")
                    continue
        except Exception as e:
            print(f"[NVIDIA] {model_id} error: {e}, trying next...")
            continue
    
    print(f"[NVIDIA] All models failed")
    return None


async def call_gemini(prompt: str) -> Optional[dict]:
    """Call Gemini via Google AI API."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
        resp = await asyncio.to_thread(
            model.generate_content, full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3, max_output_tokens=500
            )
        )
        return _parse_response(resp.text, "gemini_flash")
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


async def call_grok(prompt: str) -> Optional[dict]:
    """Call Grok via xAI API."""
    if not GROK_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GROK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROK_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_response(content, "grok_3")
    except Exception as e:
        print(f"[Grok] Error: {e}")
        return None


async def call_mimo(prompt: str) -> Optional[dict]:
    """Call Xiaomi MiMo v2 Omni via API."""
    if not MIMO_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{MIMO_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {MIMO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MIMO_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_response(content, "mimo_omni")
    except Exception as e:
        print(f"[MiMo] Error: {e}")
        return None


async def call_openai(prompt: str) -> Optional[dict]:
    """Call OpenAI as fallback."""
    if not OPENAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_response(content, "openai_gpt4o_mini")
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return None


def _parse_response(content: str, model_name: str) -> Optional[dict]:
    """Parse AI response into structured prediction."""
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*"probability"[^{}]*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            parsed = json.loads(content)
        
        prob = float(parsed.get("probability", 0.5))
        conf = float(parsed.get("confidence", 0.5))
        
        # Clamp values
        prob = max(0.01, min(0.99, prob))
        conf = max(0.1, min(1.0, conf))
        
        return {
            "model_name": model_name,
            "predicted_prob": prob,
            "confidence": conf,
            "reasoning": parsed.get("reasoning", ""),
            "key_factors": parsed.get("key_factors", []),
        }
    except Exception as e:
        # Try to extract probability from text
        prob_match = re.search(r'probability["\s:]+(\d+\.?\d*)', content)
        if prob_match:
            prob = float(prob_match.group(1))
            if prob > 1:
                prob = prob / 100
            return {
                "model_name": model_name,
                "predicted_prob": max(0.01, min(0.99, prob)),
                "confidence": 0.5,
                "reasoning": content[:200],
                "key_factors": [],
            }
        print(f"[{model_name}] Parse error: {e}")
        return None


def build_prediction_prompt(
    match_name: str,
    home_team: str,
    away_team: str,
    venue: str,
    market_type: str,
    selection: str,
    odds: float,
    line: Optional[float] = None,
    live_score: Optional[dict] = None,
    venue_stats: Optional[dict] = None,
    team_stats: Optional[dict] = None,
) -> str:
    """Build a detailed prompt for the AI models."""
    
    implied_prob = 1.0 / odds if odds > 0 else 0.5
    
    prompt = f"""MATCH: {match_name}
TEAMS: {home_team} vs {away_team}
VENUE: {venue}

MARKET: {market_type}
SELECTION: {selection}
CURRENT ODDS: {odds} (implied probability: {implied_prob:.1%})
"""
    
    if line is not None:
        prompt += f"LINE: {line}\n"
    
    if venue_stats:
        prompt += f"""
VENUE STATS:
- Average 1st innings: {venue_stats.get('avg_1st', 'N/A')}
- Powerplay avg: {venue_stats.get('powerplay', 'N/A')}
- Death overs avg: {venue_stats.get('death', 'N/A')}
- Spin friendly: {venue_stats.get('spin_friendly', 'N/A')}
"""
    
    if team_stats:
        prompt += f"""
TEAM STATS:
- {home_team} avg score: {team_stats.get('home_avg', 'N/A')}
- {away_team} avg score: {team_stats.get('away_avg', 'N/A')}
- Head-to-head: {team_stats.get('h2h', 'N/A')}
"""
    
    if live_score:
        prompt += f"""
LIVE SCORE:
- {live_score.get('team', '')}: {live_score.get('runs', 0)}/{live_score.get('wickets', 0)} 
  in {live_score.get('overs', 0)} overs (RR: {live_score.get('run_rate', 0)})
- Last 6 balls: {live_score.get('last_6_balls', 'N/A')}
"""
    
    prompt += f"""
TASK: Estimate the TRUE probability that "{selection}" occurs in the "{market_type}" market.
The bookmaker odds imply {implied_prob:.1%}. Is there an edge?

Consider all factors and provide your JSON response."""
    
    return prompt


async def get_ensemble_prediction(
    match_name: str,
    home_team: str,
    away_team: str,
    venue: str,
    market_type: str,
    selection: str,
    odds: float,
    line: Optional[float] = None,
    live_score: Optional[dict] = None,
    venue_stats: Optional[dict] = None,
    team_stats: Optional[dict] = None,
) -> dict:
    """Get predictions from all available models and combine them."""
    
    prompt = build_prediction_prompt(
        match_name, home_team, away_team, venue,
        market_type, selection, odds, line,
        live_score, venue_stats, team_stats,
    )
    
    # Call all models in parallel
    tasks = [
        call_nvidia(prompt),
        call_gemini(prompt),
        call_grok(prompt),
        call_mimo(prompt),
        call_openai(prompt),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    predictions = []
    for r in results:
        if isinstance(r, dict) and r is not None:
            predictions.append(r)
    
    if not predictions:
        # Fallback: use statistical model only
        return {
            "ensemble_prob": implied_prob,
            "consensus_score": 0.0,
            "models_agreed": 0,
            "models_total": 0,
            "predictions": [],
            "reasoning": "No AI models available, using implied probability",
        }
    
    # Weighted ensemble
    total_weight = 0
    weighted_prob = 0
    for pred in predictions:
        w = MODEL_WEIGHTS.get(pred["model_name"], 0.25) * pred["confidence"]
        weighted_prob += pred["predicted_prob"] * w
        total_weight += w
    
    ensemble_prob = weighted_prob / total_weight if total_weight > 0 else 0.5
    
    # Consensus: how much models agree (inverse of std dev)
    probs = [p["predicted_prob"] for p in predictions]
    if len(probs) > 1:
        mean_p = sum(probs) / len(probs)
        variance = sum((p - mean_p) ** 2 for p in probs) / len(probs)
        std_dev = variance ** 0.5
        consensus = max(0, 1 - std_dev * 4)  # 0.25 std = 0 consensus
    else:
        consensus = 0.5
    
    # Count agreements (within 10% of ensemble)
    agreed = sum(1 for p in probs if abs(p - ensemble_prob) < 0.10)
    
    implied_prob = 1.0 / odds if odds > 0 else 0.5
    edge = ensemble_prob - implied_prob
    
    # Combine reasoning
    reasoning_parts = []
    for pred in predictions:
        reasoning_parts.append(f"[{pred['model_name']}] {pred.get('reasoning', '')[:100]}")
    
    return {
        "ensemble_prob": round(ensemble_prob, 4),
        "consensus_score": round(consensus, 4),
        "models_agreed": agreed,
        "models_total": len(predictions),
        "predictions": predictions,
        "edge": round(edge, 4),
        "reasoning": " | ".join(reasoning_parts),
    }


def update_model_weights(performance: dict):
    """Update model weights based on historical accuracy."""
    global MODEL_WEIGHTS
    total_acc = 0
    for model, stats in performance.items():
        acc = stats.get("accuracy", 0.5)
        MODEL_WEIGHTS[model] = max(0.1, acc)
        total_acc += MODEL_WEIGHTS[model]
    
    # Normalize
    for model in MODEL_WEIGHTS:
        MODEL_WEIGHTS[model] /= total_acc