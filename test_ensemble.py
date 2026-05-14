"""Test the full AI ensemble."""
import asyncio
import sys
import os

# Ensure env is loaded
from dotenv import load_dotenv
load_dotenv()

print(f"NVIDIA key: {os.getenv('NVIDIA_API_KEY', 'NOT SET')[:15]}...")
print(f"MiMo key: {os.getenv('MIMO_API_KEY', 'NOT SET')[:15]}...")
print(f"MiMo model: {os.getenv('MIMO_MODEL', 'NOT SET')}")
print(f"NVIDIA model: {os.getenv('NVIDIA_MODEL', 'NOT SET')}")

from ai_ensemble import get_ensemble_prediction

async def test():
    print("\n--- Testing AI Ensemble: CSK vs MI (Match Winner) ---")
    result = await get_ensemble_prediction(
        match_name="IPL 2026: CSK vs MI",
        home_team="Chennai Super Kings",
        away_team="Mumbai Indians",
        venue="MA Chidambaram Stadium",
        market_type="match_winner",
        selection="Chennai Super Kings",
        odds=1.92,
        venue_stats={"avg_1st": 165, "powerplay": 48, "death": 45},
        team_stats={"home_avg": 172, "away_avg": 168, "h2h": "CSK 18-14 MI"},
    )
    if result:
        prob = result.get("ensemble_prob")
        consensus = result.get("consensus_score", "?")
        agreed = result.get("models_agreed", 0)
        total = result.get("models_total", 0)
        edge = result.get("edge", "?")
        print(f"Ensemble prob: {prob}")
        print(f"Consensus score: {consensus}")
        print(f"Models agreed: {agreed}/{total}")
        print(f"Edge vs market: {edge}")
        preds = result.get("predictions", [])
        for p in preds:
            print(f"  [{p['model_name']}] prob={p['predicted_prob']:.3f}, conf={p['confidence']:.2f}")
    else:
        print("No ensemble result")
    
    print("\nDone!")

asyncio.run(test())