"""Seed the database with IPL 2025 matches and demo trading data."""
import db
import random
from datetime import datetime, timedelta

db.init_db()

# IPL 2025 current/upcoming matches (May 2025)
matches = [
    {
        "id": "ipl2025_match_60",
        "name": "Mumbai Indians vs Chennai Super Kings",
        "home_team": "Mumbai Indians",
        "away_team": "Chennai Super Kings",
        "venue": "Wankhede Stadium",
        "start_time": "2025-05-08T19:30:00Z",
        "status": "live",
    },
    {
        "id": "ipl2025_match_61",
        "name": "Royal Challengers Bangalore vs Kolkata Knight Riders",
        "home_team": "Royal Challengers Bangalore",
        "away_team": "Kolkata Knight Riders",
        "venue": "M Chinnaswamy Stadium",
        "start_time": "2025-05-09T19:30:00Z",
        "status": "upcoming",
    },
    {
        "id": "ipl2025_match_62",
        "name": "Rajasthan Royals vs Gujarat Titans",
        "home_team": "Rajasthan Royals",
        "away_team": "Gujarat Titans",
        "venue": "Sawai Mansingh Stadium",
        "start_time": "2025-05-10T15:30:00Z",
        "status": "upcoming",
    },
    {
        "id": "ipl2025_match_63",
        "name": "Delhi Capitals vs Sunrisers Hyderabad",
        "home_team": "Delhi Capitals",
        "away_team": "Sunrisers Hyderabad",
        "venue": "Arun Jaitley Stadium",
        "start_time": "2025-05-10T19:30:00Z",
        "status": "upcoming",
    },
    {
        "id": "ipl2025_match_64",
        "name": "Lucknow Super Giants vs Punjab Kings",
        "home_team": "Lucknow Super Giants",
        "away_team": "Punjab Kings",
        "venue": "Ekana Stadium",
        "start_time": "2025-05-11T19:30:00Z",
        "status": "upcoming",
    },
    {
        "id": "ipl2025_match_55",
        "name": "Gujarat Titans vs Mumbai Indians",
        "home_team": "Gujarat Titans",
        "away_team": "Mumbai Indians",
        "venue": "Narendra Modi Stadium",
        "start_time": "2025-05-04T19:30:00Z",
        "status": "completed",
        "result": "Mumbai Indians won by 6 wickets",
    },
    {
        "id": "ipl2025_match_56",
        "name": "Chennai Super Kings vs Royal Challengers Bangalore",
        "home_team": "Chennai Super Kings",
        "away_team": "Royal Challengers Bangalore",
        "venue": "MA Chidambaram Stadium",
        "start_time": "2025-05-05T19:30:00Z",
        "status": "completed",
        "result": "Royal Challengers Bangalore won by 4 wickets",
    },
    {
        "id": "ipl2025_match_57",
        "name": "Kolkata Knight Riders vs Rajasthan Royals",
        "home_team": "Kolkata Knight Riders",
        "away_team": "Rajasthan Royals",
        "venue": "Eden Gardens",
        "start_time": "2025-05-06T19:30:00Z",
        "status": "completed",
        "result": "Kolkata Knight Riders won by 8 wickets",
    },
    {
        "id": "ipl2025_match_58",
        "name": "Sunrisers Hyderabad vs Lucknow Super Giants",
        "home_team": "Sunrisers Hyderabad",
        "away_team": "Lucknow Super Giants",
        "venue": "Rajiv Gandhi Intl",
        "start_time": "2025-05-07T15:30:00Z",
        "status": "completed",
        "result": "Sunrisers Hyderabad won by 12 runs",
    },
    {
        "id": "ipl2025_match_59",
        "name": "Punjab Kings vs Delhi Capitals",
        "home_team": "Punjab Kings",
        "away_team": "Delhi Capitals",
        "venue": "IS Bindra Stadium",
        "start_time": "2025-05-07T19:30:00Z",
        "status": "completed",
        "result": "Delhi Capitals won by 5 wickets",
    },
]

print("Saving matches...")
for m in matches:
    db.save_match(m)
    print(f"  {m['name']} [{m['status']}]")

# Add live score for the live match
print("\nAdding live score for MI vs CSK...")
db.save_live_score({
    "match_id": "ipl2025_match_60",
    "innings": 1,
    "team": "Mumbai Indians",
    "runs": 142,
    "wickets": 3,
    "overs": 14.2,
    "run_rate": 9.93,
    "extras": {"wides": 2, "noballs": 0, "byes": 1, "legbyes": 3},
    "last_6_balls": ["1", "4", "0", "6", "2", "1"],
})

# Add demo trades
print("\nAdding demo trades...")
demo_trades = [
    {"match_id": "ipl2025_match_55", "market_type": "match_winner", "selection": "Mumbai Indians", "side": "back", "odds": 2.10, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 2.20},
    {"match_id": "ipl2025_match_55", "market_type": "total_runs", "selection": "Over 320.5", "side": "back", "odds": 1.85, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 1.70},
    {"match_id": "ipl2025_match_56", "market_type": "match_winner", "selection": "Royal Challengers Bangalore", "side": "back", "odds": 2.30, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 2.60},
    {"match_id": "ipl2025_match_56", "market_type": "top_batsman", "selection": "Virat Kohli", "side": "back", "odds": 4.50, "stake": 1.0, "mode": "demo", "status": "lost", "pnl": -1.00},
    {"match_id": "ipl2025_match_57", "market_type": "match_winner", "selection": "Kolkata Knight Riders", "side": "back", "odds": 1.75, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 1.50},
    {"match_id": "ipl2025_match_57", "market_type": "total_sixes", "selection": "Over 12.5", "side": "back", "odds": 1.90, "stake": 2.0, "mode": "demo", "status": "lost", "pnl": -2.00},
    {"match_id": "ipl2025_match_58", "market_type": "match_winner", "selection": "Sunrisers Hyderabad", "side": "back", "odds": 1.95, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 1.90},
    {"match_id": "ipl2025_match_58", "market_type": "total_runs", "selection": "Over 340.5", "side": "back", "odds": 1.80, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 1.60},
    {"match_id": "ipl2025_match_59", "market_type": "match_winner", "selection": "Delhi Capitals", "side": "back", "odds": 2.40, "stake": 2.0, "mode": "demo", "status": "won", "pnl": 2.80},
    {"match_id": "ipl2025_match_59", "market_type": "top_bowler", "selection": "Kagiso Rabada", "side": "back", "odds": 5.00, "stake": 1.0, "mode": "demo", "status": "lost", "pnl": -1.00},
    {"match_id": "ipl2025_match_60", "market_type": "match_winner", "selection": "Mumbai Indians", "side": "back", "odds": 1.85, "stake": 2.0, "mode": "demo", "status": "open", "pnl": 0},
    {"match_id": "ipl2025_match_60", "market_type": "total_runs", "selection": "Over 330.5", "side": "back", "odds": 1.90, "stake": 2.0, "mode": "demo", "status": "open", "pnl": 0},
]

for t in demo_trades:
    db.save_trade(t)

print(f"  Added {len(demo_trades)} demo trades")

# Add ensemble decisions
print("\nAdding AI ensemble decisions...")
decisions = [
    {"match_id": "ipl2025_match_60", "market_type": "match_winner", "selection": "Mumbai Indians", "ensemble_prob": 0.62, "consensus_score": 0.85, "models_agreed": 3, "models_total": 4, "decision": "BACK", "edge": 0.08, "kelly_size": 1.8, "reasoning": "MI strong at Wankhede, CSK missing key bowler. 3/4 models agree."},
    {"match_id": "ipl2025_match_60", "market_type": "total_runs", "selection": "Over 330.5", "ensemble_prob": 0.58, "consensus_score": 0.75, "models_agreed": 3, "models_total": 4, "decision": "BACK", "edge": 0.06, "kelly_size": 1.2, "reasoning": "Wankhede high-scoring venue, both teams strong batting lineups."},
    {"match_id": "ipl2025_match_61", "market_type": "match_winner", "selection": "Royal Challengers Bangalore", "ensemble_prob": 0.55, "consensus_score": 0.60, "models_agreed": 2, "models_total": 4, "decision": "SKIP", "edge": 0.02, "kelly_size": 0.0, "reasoning": "Edge too small. RCB home advantage but KKR in good form."},
    {"match_id": "ipl2025_match_55", "market_type": "match_winner", "selection": "Mumbai Indians", "ensemble_prob": 0.65, "consensus_score": 0.90, "models_agreed": 4, "models_total": 4, "decision": "BACK", "edge": 0.12, "kelly_size": 2.5, "reasoning": "Strong consensus across all models. MI superior squad depth."},
    {"match_id": "ipl2025_match_56", "market_type": "match_winner", "selection": "Royal Challengers Bangalore", "ensemble_prob": 0.60, "consensus_score": 0.80, "models_agreed": 3, "models_total": 4, "decision": "BACK", "edge": 0.09, "kelly_size": 2.0, "reasoning": "RCB motivated, CSK struggling with injuries."},
]

for d in decisions:
    db.save_ensemble_decision(d)

print(f"  Added {len(decisions)} ensemble decisions")

# Add model performance
print("\nAdding model performance data...")
conn = db.get_conn()
models_perf = [
    ("NVIDIA Nemotron", "match_winner", 45, 36, 0.80, 0.72),
    ("NVIDIA Nemotron", "total_runs", 30, 22, 0.73, 0.68),
    ("Gemini Flash", "match_winner", 45, 34, 0.76, 0.70),
    ("Gemini Flash", "total_runs", 30, 23, 0.77, 0.71),
    ("Grok 3", "match_winner", 45, 35, 0.78, 0.69),
    ("Grok 3", "total_runs", 30, 21, 0.70, 0.65),
    ("MIMO", "match_winner", 45, 33, 0.73, 0.67),
    ("MIMO", "total_runs", 30, 22, 0.73, 0.66),
]
for model_name, market, total, correct, acc, avg_conf in models_perf:
    conn.execute("""
        INSERT OR REPLACE INTO model_performance 
        (model_name, market_type, total_predictions, correct_predictions, accuracy, avg_confidence)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (model_name, market, total, correct, acc, avg_conf))

conn.commit()
conn.close()
print(f"  Added {len(models_perf)} model performance records")

print("\n✅ Demo data seeded successfully!")
print("   Restart the dashboard to see live matches and trading data.")