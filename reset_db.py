"""Reset database - remove all dummy data."""
import db

db.init_db()
conn = db.get_conn()
try:
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM ensemble_decisions")
    conn.execute("DELETE FROM model_performance")
    conn.execute("DELETE FROM matches")
    conn.execute("DELETE FROM predictions")
    conn.execute("DELETE FROM odds_snapshots")
    conn.execute("DELETE FROM live_scores")
    conn.commit()
    print("All dummy data cleared from database.")
finally:
    conn.close()