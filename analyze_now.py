"""
One-shot live analysis: RoyalBook odds + Cricbuzz + 18yr H2H data + Gemma 3
Run: python analyze_now.py
"""
import sys, os, asyncio, httpx
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ── Fetch live Cricbuzz score ─────────────────────────────────────────────────
async def get_cricbuzz_state():
    try:
        from data_ingestion.cricket_stats import cricket_stats
        return await cricket_stats.get_live_score_cricbuzz()
    except Exception as e:
        return {"error": str(e)}

# ── Fetch live odds from Redis / OddsScraper ──────────────────────────────────
async def get_live_odds():
    try:
        from database.redis_client import get_redis, RedisCache
        from dotenv import load_dotenv
        load_dotenv()
        redis = await get_redis()
        cache = RedisCache(redis)
        odds = await cache.get_odds(1) or {}
        return odds
    except Exception as e:
        return {}

# ── Historical H2H ────────────────────────────────────────────────────────────
def get_h2h(team_a, team_b, venue=""):
    try:
        from data_ingestion.historical_data import HistoricalDataEngine
        engine = HistoricalDataEngine()
        return engine.compute_pre_match_probability(team_a, team_b, venue=venue)
    except Exception as e:
        return {"error": str(e)}

# ── Gemma 3 analysis ──────────────────────────────────────────────────────────
def ask_gemma(prompt):
    try:
        r = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma3:12b", "prompt": prompt, "stream": False},
            timeout=90.0
        )
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"Gemma error: {e}"

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    SEP = "=" * 58
    print(f"\n{SEP}")
    print(f"  IPL LIVE ANALYSIS  |  {datetime.now().strftime('%H:%M:%S')}")
    print(SEP)

    score, odds = await asyncio.gather(get_cricbuzz_state(), get_live_odds())

    team_a = (score or {}).get("team_a", "Team A")
    team_b = (score or {}).get("team_b", "Team B")
    venue  = (score or {}).get("venue", "")

    odds_a = float(odds.get("team_a_odds", 0) or 0)
    odds_b = float(odds.get("team_b_odds", 0) or 0)
    odds_a_lay = float(odds.get("team_a_lay", 0) or 0)
    odds_b_lay = float(odds.get("team_b_lay", 0) or 0)
    bk = odds.get("bookmaker", {})
    bk_a = float(bk.get("team_a_odds", 0) or 0) if bk else 0
    bk_b = float(bk.get("team_b_odds", 0) or 0) if bk else 0

    # Score section
    print(f"\nMATCH : {team_a} vs {team_b}")
    print(f"VENUE : {venue or 'N/A'}")
    if score and not score.get("error"):
        print(f"SCORE : {score.get('total_runs','?')}/{score.get('total_wickets','?')} "
              f"({score.get('overs','?')} ov) | Innings {score.get('innings','?')}")
        print(f"CRR   : {score.get('run_rate','?')}  |  "
              f"RRR: {score.get('required_run_rate','?')}"
              + (f"  |  Target: {score.get('target')}" if score.get('target') else ""))
        print(f"BAT   : {score.get('batting_team','?')}")

    # Odds section
    print(f"\nODDS (RoyalBook Exchange):")
    if odds_a:
        print(f"  {team_a:<22} Back {odds_a:.2f}  Lay {odds_a_lay or '-'}")
    if odds_b:
        print(f"  {team_b:<22} Back {odds_b:.2f}  Lay {odds_b_lay or '-'}")
    if bk_a or bk_b:
        print(f"  Bookmaker >> {team_a}: {bk_a}  |  {team_b}: {bk_b}")

    # H2H
    h2h = get_h2h(team_a, team_b, venue)
    print(f"\nH2H (18-yr IPL data):")
    if h2h and not h2h.get("error"):
        print(f"  {team_a}: {h2h.get('team_a_win_pct')}%  |  {team_b}: {h2h.get('team_b_win_pct')}%")
        for f in h2h.get("factors", []):
            print(f"  - {f}")
    else:
        print(f"  {h2h}")

    # Implied probabilities
    imp_a = round(1/odds_a*100, 1) if odds_a > 1 else 0
    imp_b = round(1/odds_b*100, 1) if odds_b > 1 else 0
    h2h_a = h2h.get("team_a_win_pct", 50) if h2h and not h2h.get("error") else 50
    h2h_b = h2h.get("team_b_win_pct", 50) if h2h and not h2h.get("error") else 50

    if imp_a or imp_b:
        print(f"\nMARKET IMPLIED PROB:")
        if imp_a: print(f"  {team_a}: {imp_a}%  (H2H says {h2h_a}%) -> edge {round(h2h_a - imp_a, 1):+}%")
        if imp_b: print(f"  {team_b}: {imp_b}%  (H2H says {h2h_b}%) -> edge {round(h2h_b - imp_b, 1):+}%")

    # Gemma 3
    prompt = f"""You are an expert IPL betting analyst with deep knowledge of cricket.
Analyze this live data and give a SINGLE best value bet.

MATCH: {team_a} vs {team_b}
VENUE: {venue or 'Unknown'}
LIVE SCORE: {score.get('total_runs','?')}/{score.get('total_wickets','?')} in {score.get('overs','?')} overs (Innings {score.get('innings','?')})
CRR: {score.get('run_rate','?')} | RRR: {score.get('required_run_rate','?')} | Target: {score.get('target',0) or 'N/A'}
Batting team: {score.get('batting_team','?')}

ROYALBOOK ODDS:
{team_a}: Back {odds_a} / Lay {odds_a_lay} (implied {imp_a}%)
{team_b}: Back {odds_b} / Lay {odds_b_lay} (implied {imp_b}%)
Bookmaker: {team_a}={bk_a} | {team_b}={bk_b}

18-YEAR IPL H2H:
{team_a} wins {h2h_a}% | {team_b} wins {h2h_b}%
Factors: {', '.join(h2h.get('factors', []) if h2h and not h2h.get('error') else [])}

Give ONLY this format, nothing else:

BET: BACK/LAY [team] @ [odds]
EDGE: [market implied]% vs [H2H]% = [+/-X]% edge
CONFIDENCE: HIGH / MEDIUM / LOW
STAKE: X% of bankroll
REASONING: [2 sentences max, focus on current match situation and odds value]
AVOID: [one key risk]"""

    print(f"\nGEMMA 3 CALL:")
    print("-" * 50)
    print(ask_gemma(prompt))
    print(f"\n{SEP}\n")

if __name__ == "__main__":
    asyncio.run(main())
