"""Database layer for cricket trading system."""
import sqlite3
import json
import time
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        name TEXT,
        home_team TEXT,
        away_team TEXT,
        venue TEXT,
        start_time TEXT,
        status TEXT DEFAULT 'upcoming',
        result TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    
    CREATE TABLE IF NOT EXISTS odds_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        market_type TEXT,
        selections_json TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (match_id) REFERENCES matches(id)
    );
    
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        market_type TEXT,
        selection TEXT,
        model_name TEXT,
        predicted_prob REAL,
        confidence REAL,
        reasoning TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (match_id) REFERENCES matches(id)
    );
    
    CREATE TABLE IF NOT EXISTS ensemble_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        market_type TEXT,
        selection TEXT,
        ensemble_prob REAL,
        consensus_score REAL,
        models_agreed INTEGER,
        models_total INTEGER,
        decision TEXT,
        edge REAL,
        kelly_size REAL,
        reasoning TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        market_type TEXT,
        selection TEXT,
        side TEXT,
        odds REAL,
        stake REAL,
        mode TEXT DEFAULT 'demo',
        cloudbet_ref TEXT,
        status TEXT DEFAULT 'pending',
        pnl REAL DEFAULT 0,
        settled_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    
    CREATE TABLE IF NOT EXISTS live_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        innings INTEGER,
        team TEXT,
        runs INTEGER,
        wickets INTEGER,
        overs REAL,
        run_rate REAL,
        extras TEXT,
        last_6_balls TEXT,
        fetched_at TEXT DEFAULT (datetime('now'))
    );
    
    CREATE TABLE IF NOT EXISTS model_performance (
        model_name TEXT,
        market_type TEXT,
        total_predictions INTEGER DEFAULT 0,
        correct_predictions INTEGER DEFAULT 0,
        accuracy REAL DEFAULT 0,
        avg_confidence REAL DEFAULT 0,
        last_updated TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (model_name, market_type)
    );
    """)
    conn.commit()
    conn.close()


def save_match(match_data: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO matches (id, name, home_team, away_team, venue, start_time, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        match_data["id"], match_data["name"],
        match_data.get("home_team", ""), match_data.get("away_team", ""),
        match_data.get("venue", ""), match_data.get("start_time", ""),
        match_data.get("status", "upcoming")
    ))
    conn.commit()
    conn.close()


def save_odds(match_id: str, market_type: str, selections: list):
    conn = get_conn()
    conn.execute("""
        INSERT INTO odds_snapshots (match_id, market_type, selections_json)
        VALUES (?, ?, ?)
    """, (match_id, market_type, json.dumps(selections)))
    conn.commit()
    conn.close()


def save_prediction(pred: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO predictions (match_id, market_type, selection, model_name, 
                                predicted_prob, confidence, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        pred["match_id"], pred["market_type"], pred["selection"],
        pred["model_name"], pred["predicted_prob"], pred["confidence"],
        pred.get("reasoning", "")
    ))
    conn.commit()
    conn.close()


def save_ensemble_decision(decision: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO ensemble_decisions (match_id, market_type, selection, ensemble_prob,
                                        consensus_score, models_agreed, models_total,
                                        decision, edge, kelly_size, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        decision["match_id"], decision["market_type"], decision["selection"],
        decision["ensemble_prob"], decision["consensus_score"],
        decision["models_agreed"], decision["models_total"],
        decision["decision"], decision["edge"], decision["kelly_size"],
        decision.get("reasoning", "")
    ))
    conn.commit()
    conn.close()


def save_trade(trade: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO trades (match_id, market_type, selection, side, odds, stake, mode, cloudbet_ref, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade["match_id"], trade["market_type"], trade["selection"],
        trade["side"], trade["odds"], trade["stake"],
        trade.get("mode", "demo"), trade.get("cloudbet_ref", ""),
        trade.get("status", "pending")
    ))
    conn.commit()
    conn.close()


def settle_trade(trade_id: int, pnl: float, status: str = "settled"):
    conn = get_conn()
    conn.execute("""
        UPDATE trades SET pnl = ?, status = ?, settled_at = datetime('now')
        WHERE id = ?
    """, (pnl, status, trade_id))
    conn.commit()
    conn.close()


def save_live_score(score: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO live_scores (match_id, innings, team, runs, wickets, overs, run_rate, extras, last_6_balls)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        score["match_id"], score.get("innings", 1), score.get("team", ""),
        score.get("runs", 0), score.get("wickets", 0), score.get("overs", 0),
        score.get("run_rate", 0), json.dumps(score.get("extras", {})),
        json.dumps(score.get("last_6_balls", []))
    ))
    conn.commit()
    conn.close()


def get_recent_odds(match_id: str, market_type: str, limit: int = 5):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM odds_snapshots 
        WHERE match_id = ? AND market_type = ?
        ORDER BY fetched_at DESC LIMIT ?
    """, (match_id, market_type, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_predictions(match_id: str, market_type: str = None):
    conn = get_conn()
    if market_type:
        rows = conn.execute("""
            SELECT * FROM predictions WHERE match_id = ? AND market_type = ?
            ORDER BY created_at DESC
        """, (match_id, market_type)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM predictions WHERE match_id = ?
            ORDER BY created_at DESC
        """, (match_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trades(match_id: str = None, status: str = None, limit: int = 50):
    conn = get_conn()
    query = "SELECT * FROM trades WHERE 1=1"
    params = []
    if match_id:
        query += " AND match_id = ?"
        params.append(match_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_trades(limit: int = 200):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM trades ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_stats():
    conn = get_conn()
    stats = {}
    for mode in ["demo", "live"]:
        row = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN pnl = 0 AND status = 'settled' THEN 1 ELSE 0 END) as pushes,
                SUM(pnl) as total_pnl,
                AVG(CASE WHEN status = 'settled' THEN pnl END) as avg_pnl
            FROM trades WHERE mode = ?
        """, (mode,)).fetchone()
        stats[mode] = dict(row) if row else {}
    
    # Model accuracy
    rows = conn.execute("SELECT * FROM model_performance ORDER BY accuracy DESC").fetchall()
    stats["model_performance"] = [dict(r) for r in rows]
    
    conn.close()
    return stats


def get_latest_score(match_id: str):
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM live_scores WHERE match_id = ?
        ORDER BY fetched_at DESC LIMIT 1
    """, (match_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ensemble_decisions(match_id: str = None, limit: int = 20):
    conn = get_conn()
    if match_id:
        rows = conn.execute("""
            SELECT * FROM ensemble_decisions WHERE match_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (match_id, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM ensemble_decisions ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_stats(mode: str = None):
    """Get trading session statistics."""
    conn = get_conn()
    if mode is None:
        mode = "demo"
    
    row = conn.execute("""
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as won,
            SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as lost,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open,
            SUM(CASE WHEN status = 'won' THEN pnl ELSE 0 END) as total_won_pnl,
            SUM(CASE WHEN status = 'lost' THEN stake ELSE 0 END) as total_lost_stake
        FROM trades WHERE mode = ?
    """, (mode,)).fetchone()
    
    conn.close()
    
    if not row:
        return {"total_trades": 0, "won": 0, "lost": 0, "open": 0, "pnl": 0, "accuracy": 0}
    
    total = row["total_trades"] or 0
    won = row["won"] or 0
    lost = row["lost"] or 0
    pnl = (row["total_won_pnl"] or 0) - (row["total_lost_stake"] or 0)
    accuracy = won / (won + lost) if (won + lost) > 0 else 0
    
    return {
        "total_trades": total,
        "won": won,
        "lost": lost,
        "open": row["open"] or 0,
        "pnl": pnl,
        "accuracy": accuracy,
    }
