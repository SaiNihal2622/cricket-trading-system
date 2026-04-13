"""
IPL Historical Database — PostgreSQL-backed.

One-time setup:
  python -m data_ingestion.ipl_db --load /path/to/matches.csv /path/to/deliveries.csv

Runtime:
  from data_ingestion.ipl_db import get_ipl_db
  db = await get_ipl_db()
  stats = await db.venue_stats("Wankhede Stadium")

Kaggle dataset: "IPL Complete Dataset (2008-2024)"
  https://www.kaggle.com/datasets/patrickb1912/ipl-complete-dataset-20082020
  Files: matches.csv, deliveries.csv
"""
import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ipl_venue_stats (
    venue           TEXT PRIMARY KEY,
    matches         INT  DEFAULT 0,
    avg_1st_innings REAL DEFAULT 167,
    chase_win_pct   REAL DEFAULT 50,
    avg_powerplay   REAL DEFAULT 52,
    avg_death       REAL DEFAULT 59,
    toss_bat_pct    REAL DEFAULT 45,
    toss_win_adv    REAL DEFAULT 50,
    pitch_type      TEXT DEFAULT 'balanced',
    dew_factor      TEXT DEFAULT 'medium',
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ipl_h2h (
    team_a      TEXT,
    team_b      TEXT,
    matches     INT  DEFAULT 0,
    team_a_wins INT  DEFAULT 0,
    win_pct     REAL DEFAULT 50,
    PRIMARY KEY (team_a, team_b)
);

CREATE TABLE IF NOT EXISTS ipl_batsman (
    name        TEXT PRIMARY KEY,
    innings     INT  DEFAULT 0,
    runs        INT  DEFAULT 0,
    balls       INT  DEFAULT 0,
    avg         REAL DEFAULT 22,
    sr          REAL DEFAULT 120,
    pp_runs     INT  DEFAULT 0,
    pp_balls    INT  DEFAULT 0,
    pp_sr       REAL DEFAULT 115,
    death_runs  INT  DEFAULT 0,
    death_balls INT  DEFAULT 0,
    death_sr    REAL DEFAULT 130,
    class       TEXT DEFAULT 'C',
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ipl_situation (
    over_bucket INT,
    wickets     INT,
    innings     INT,
    matches     INT  DEFAULT 0,
    batting_won INT  DEFAULT 0,
    win_pct     REAL DEFAULT 50,
    PRIMARY KEY (over_bucket, wickets, innings)
);

CREATE TABLE IF NOT EXISTS ipl_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# ── Canonical team name mapping ───────────────────────────────────────────────
TEAM_CANON = {
    "mumbai indians": "mumbai indians",
    "mi": "mumbai indians",
    "chennai super kings": "chennai super kings",
    "csk": "chennai super kings",
    "kolkata knight riders": "kolkata knight riders",
    "kkr": "kolkata knight riders",
    "royal challengers bangalore": "royal challengers bengaluru",
    "royal challengers bengaluru": "royal challengers bengaluru",
    "rcb": "royal challengers bengaluru",
    "sunrisers hyderabad": "sunrisers hyderabad",
    "srh": "sunrisers hyderabad",
    "delhi capitals": "delhi capitals",
    "delhi daredevils": "delhi capitals",
    "dc": "delhi capitals",
    "dd": "delhi capitals",
    "rajasthan royals": "rajasthan royals",
    "rr": "rajasthan royals",
    "punjab kings": "punjab kings",
    "kings xi punjab": "punjab kings",
    "pbks": "punjab kings",
    "kxip": "punjab kings",
    "gujarat titans": "gujarat titans",
    "gt": "gujarat titans",
    "lucknow super giants": "lucknow super giants",
    "lsg": "lucknow super giants",
    "rising pune supergiant": "rising pune supergiant",
    "rising pune supergiants": "rising pune supergiant",
    "pune warriors": "pune warriors",
    "kochi tuskers kerala": "kochi tuskers kerala",
    "deccan chargers": "deccan chargers",
}

def _canon(name: str) -> str:
    n = name.lower().strip()
    return TEAM_CANON.get(n, n)


class IPLDatabase:
    """
    Async PostgreSQL interface for IPL historical stats.
    Falls back gracefully if DB is unavailable.
    """

    def __init__(self, db_url: str):
        self._url = db_url
        self._pool = None
        self._ready = False

    async def init(self):
        """Create connection pool and ensure schema exists."""
        try:
            import asyncpg
            # asyncpg needs postgresql:// not postgresql+asyncpg://
            url = self._url.replace("postgresql+asyncpg://", "postgresql://")
            self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
            self._ready = True
            logger.info("IPL DB: connected and schema ready")
        except Exception as e:
            logger.warning(f"IPL DB unavailable: {e} — using hardcoded fallback")
            self._ready = False

    async def is_populated(self) -> bool:
        if not self._ready:
            return False
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM ipl_meta WHERE key='loaded'")
            return row is not None and row["value"] == "true"

    async def venue_stats(self, venue: str) -> Optional[dict]:
        if not self._ready:
            return None
        venue_lower = venue.lower().strip()
        async with self._pool.acquire() as conn:
            # Partial match: try contains
            rows = await conn.fetch(
                "SELECT * FROM ipl_venue_stats WHERE LOWER(venue) LIKE $1 ORDER BY matches DESC LIMIT 1",
                f"%{venue_lower}%"
            )
            if not rows:
                # Try word-level match
                words = [w for w in venue_lower.split() if len(w) > 4]
                for w in words:
                    rows = await conn.fetch(
                        "SELECT * FROM ipl_venue_stats WHERE LOWER(venue) LIKE $1 ORDER BY matches DESC LIMIT 1",
                        f"%{w}%"
                    )
                    if rows:
                        break
            if rows:
                r = rows[0]
                return {
                    "avg_1st_innings": round(r["avg_1st_innings"]),
                    "chase_win_pct":   round(r["chase_win_pct"]),
                    "avg_powerplay":   round(r["avg_powerplay"]),
                    "avg_death":       round(r["avg_death"]),
                    "toss_bat_pct":    round(r["toss_bat_pct"]),
                    "toss_win_adv":    round(r["toss_win_adv"]),
                    "pitch":           r["pitch_type"],
                    "dew_factor":      r["dew_factor"],
                    "matches":         r["matches"],
                }
        return None

    async def h2h(self, team_a: str, team_b: str) -> Optional[float]:
        if not self._ready:
            return None
        a, b = _canon(team_a), _canon(team_b)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT win_pct FROM ipl_h2h WHERE team_a=$1 AND team_b=$2", a, b
            )
            if row:
                return float(row["win_pct"])
            row = await conn.fetchrow(
                "SELECT win_pct FROM ipl_h2h WHERE team_a=$1 AND team_b=$2", b, a
            )
            if row:
                return 100.0 - float(row["win_pct"])
        return None

    async def batsman(self, name: str) -> Optional[dict]:
        if not self._ready:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ipl_batsman WHERE LOWER(name) LIKE $1 ORDER BY innings DESC LIMIT 1",
                f"%{name.lower().strip()}%"
            )
            if row:
                return {
                    "sr": round(row["sr"]),
                    "avg": round(row["avg"], 1),
                    "pp_sr": round(row["pp_sr"]),
                    "death_sr": round(row["death_sr"]),
                    "innings": row["innings"],
                    "class": row["class"],
                }
        return None

    async def situation_win_pct(self, overs: float, wickets: int, innings: int, crr: float = 0, rrr: float = 0) -> Optional[float]:
        if not self._ready:
            return None
        bucket = min(20, max(5, int(overs // 5) * 5 + (5 if overs % 5 >= 2.5 else 0)))
        wkt = min(7, wickets)
        inn = min(2, max(1, innings))
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT win_pct, matches FROM ipl_situation WHERE over_bucket=$1 AND wickets=$2 AND innings=$3",
                bucket, wkt, inn
            )
            if row and row["matches"] >= 10:
                base = float(row["win_pct"])
                if inn == 2 and rrr > 0 and crr > 0:
                    rr_edge = (crr - rrr) / max(rrr, 1)
                    base += rr_edge * 50
                    base = max(5, min(95, base))
                return base
        return None

    async def load_from_csvs(self, matches_csv: str, deliveries_csv: str):
        """
        One-time load: parse Kaggle IPL CSVs and populate all tables.
        Safe to re-run (UPSERT).
        """
        import csv, math
        from collections import defaultdict

        logger.info(f"Loading IPL CSVs: {matches_csv}, {deliveries_csv}")

        # ── Read matches ──────────────────────────────────────────────────────
        matches = {}  # match_id → row
        with open(matches_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mid = row.get("id") or row.get("match_id") or row.get("ID")
                if mid:
                    matches[mid] = row

        logger.info(f"  Matches loaded: {len(matches)}")

        # ── Venue stats aggregation ────────────────────────────────────────
        venue_data = defaultdict(lambda: {
            "matches": 0, "scores_1st": [], "chase_wins": 0,
            "pp_totals": [], "death_totals": [], "toss_bat": 0, "toss_wins": 0
        })

        h2h_data = defaultdict(lambda: {"matches": 0, "a_wins": 0})

        for mid, m in matches.items():
            venue = (m.get("venue") or m.get("Venue") or "").strip()
            if not venue:
                continue
            v = venue_data[venue]
            v["matches"] += 1

            winner   = (m.get("winner") or m.get("Winner") or "").strip()
            team1    = (m.get("team1") or m.get("Team1") or "").strip()
            team2    = (m.get("team2") or m.get("Team2") or "").strip()
            toss_w   = (m.get("toss_winner") or m.get("TossWinner") or "").strip()
            toss_d   = (m.get("toss_decision") or m.get("TossDecision") or "").strip()

            if toss_d.lower() == "bat":
                v["toss_bat"] += 1
            if toss_w and toss_w == winner:
                v["toss_wins"] += 1

            # H2H
            a, b = _canon(team1), _canon(team2)
            if a > b:
                a, b = b, a
            key = (a, b)
            h2h_data[key]["matches"] += 1
            if _canon(winner) == _canon(team1):
                h2h_data[(_canon(team1), _canon(team2))]["a_wins"] += 1
            elif _canon(winner) == _canon(team2):
                h2h_data[(_canon(team2), _canon(team1))]["a_wins"] += 1

        # ── Deliveries aggregation ─────────────────────────────────────────
        batsman_data = defaultdict(lambda: {
            "inn": 0, "runs": 0, "balls": 0,
            "pp_runs": 0, "pp_balls": 0,
            "death_runs": 0, "death_balls": 0,
        })

        situation_data = defaultdict(lambda: {"matches": set(), "batting_won": 0})

        venue_inning_scores = defaultdict(lambda: defaultdict(int))  # venue→match_id→runs
        venue_pp_scores     = defaultdict(lambda: defaultdict(int))  # venue→match_id→pp_runs
        venue_death_scores  = defaultdict(lambda: defaultdict(int))
        chase_wins          = defaultdict(int)  # venue→chase wins
        first_innings_teams = {}  # match_id → batting team in 1st innings

        with open(deliveries_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mid    = row.get("match_id") or row.get("ID") or ""
                inn    = int(row.get("inning") or row.get("innings") or 1)
                over   = int(row.get("over") or row.get("overs") or 0)
                bat_t  = (row.get("batting_team") or row.get("BattingTeam") or "").strip()
                bowl_t = (row.get("bowling_team") or row.get("BowlingTeam") or "").strip()
                batter = (row.get("batter") or row.get("batsman") or "").strip().lower()
                tr     = int(row.get("total_runs") or row.get("runs_total") or row.get("runs_off_bat", 0) or 0)
                br     = int(row.get("runs_off_bat") or row.get("batsman_runs") or 0)
                extras = int(row.get("extras") or 0)
                is_wkt = bool(row.get("player_dismissed") or row.get("wicket_type") or row.get("is_wicket", 0))

                if mid not in matches:
                    continue

                venue = (matches[mid].get("venue") or matches[mid].get("Venue") or "").strip()
                winner = (matches[mid].get("winner") or matches[mid].get("Winner") or "").strip()

                # Track 1st innings batting team
                if inn == 1:
                    first_innings_teams[mid] = _canon(bat_t)
                    venue_inning_scores[venue][mid] += tr
                    if over <= 6:
                        venue_pp_scores[venue][mid] += tr
                    if over >= 16:
                        venue_death_scores[venue][mid] += tr
                elif inn == 2:
                    # Chase win?
                    if _canon(winner) == _canon(bat_t):
                        chase_wins[venue] = chase_wins.get(venue, 0)
                        # Mark per match
                        pass

                # Batsman stats
                if batter and br >= 0 and inn <= 2:
                    d = batsman_data[batter]
                    d["runs"]  += br
                    d["balls"] += 1
                    if over <= 6:
                        d["pp_runs"]  += br
                        d["pp_balls"] += 1
                    if over >= 16:
                        d["death_runs"]  += br
                        d["death_balls"] += 1

                # Situation win%
                bucket = min(20, max(5, int(over // 5) * 5 + (5 if over % 5 >= 3 else 0)))
                wkt_bucket = 0  # we don't have cumulative wickets per ball easily
                key = (bucket, wkt_bucket, inn)
                situation_data[key]["matches"].add(mid)

        # ── Compute venue chase win% ───────────────────────────────────────
        venue_chase = defaultdict(lambda: {"chases": 0, "chase_wins": 0})
        for mid, m in matches.items():
            venue  = (m.get("venue") or m.get("Venue") or "").strip()
            winner = (m.get("winner") or m.get("Winner") or "").strip()
            team1  = (m.get("team1") or m.get("Team1") or "").strip()
            team2  = (m.get("team2") or m.get("Team2") or "").strip()
            result = (m.get("result") or "").strip()
            if result == "no result" or not winner:
                continue
            # Determine who batted 2nd — assume team that lost toss batted 1st unless toss_decision=field
            toss_w = (m.get("toss_winner") or "").strip()
            toss_d = (m.get("toss_decision") or "").lower()
            if toss_d == "field":
                batting_first = team2 if toss_w == team1 else team1
            else:
                batting_first = toss_w
            chasing_team = team2 if batting_first == team1 else team1
            venue_chase[venue]["chases"] += 1
            if _canon(winner) == _canon(chasing_team):
                venue_chase[venue]["chase_wins"] += 1

        # ── Write to DB ────────────────────────────────────────────────────
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Venue stats
                for venue, vd in venue_data.items():
                    n = vd["matches"]
                    if n < 3:
                        continue
                    scores = venue_inning_scores[venue]
                    avg_1st = sum(scores.values()) / max(len(scores), 1) if scores else 167
                    pp_list = [v for v in venue_pp_scores[venue].values()]
                    death_list = [v for v in venue_death_scores[venue].values()]
                    avg_pp = sum(pp_list) / max(len(pp_list), 1) if pp_list else 52
                    avg_death = sum(death_list) / max(len(death_list), 1) if death_list else 59
                    vc = venue_chase[venue]
                    chase_pct = (vc["chase_wins"] / max(vc["chases"], 1)) * 100 if vc["chases"] else 50
                    toss_bat_pct = (vd["toss_bat"] / n) * 100
                    toss_win_adv = (vd["toss_wins"] / n) * 100

                    # Heuristic pitch type
                    if avg_1st >= 175:
                        pitch = "batting"
                    elif avg_1st <= 155:
                        pitch = "bowling"
                    else:
                        pitch = "balanced"

                    await conn.execute("""
                        INSERT INTO ipl_venue_stats
                            (venue, matches, avg_1st_innings, chase_win_pct, avg_powerplay, avg_death,
                             toss_bat_pct, toss_win_adv, pitch_type, dew_factor)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        ON CONFLICT (venue) DO UPDATE SET
                            matches=EXCLUDED.matches,
                            avg_1st_innings=EXCLUDED.avg_1st_innings,
                            chase_win_pct=EXCLUDED.chase_win_pct,
                            avg_powerplay=EXCLUDED.avg_powerplay,
                            avg_death=EXCLUDED.avg_death,
                            toss_bat_pct=EXCLUDED.toss_bat_pct,
                            toss_win_adv=EXCLUDED.toss_win_adv,
                            pitch_type=EXCLUDED.pitch_type,
                            updated_at=NOW()
                    """, venue, n, avg_1st, chase_pct, avg_pp, avg_death,
                         toss_bat_pct, toss_win_adv, pitch, "medium")

                logger.info(f"  Venue stats written: {len(venue_data)} venues")

                # H2H
                h2h_count = 0
                for (a, b), d in h2h_data.items():
                    if d["matches"] < 2:
                        continue
                    wp = (d["a_wins"] / d["matches"]) * 100
                    await conn.execute("""
                        INSERT INTO ipl_h2h (team_a, team_b, matches, team_a_wins, win_pct)
                        VALUES ($1,$2,$3,$4,$5)
                        ON CONFLICT (team_a, team_b) DO UPDATE SET
                            matches=EXCLUDED.matches,
                            team_a_wins=EXCLUDED.team_a_wins,
                            win_pct=EXCLUDED.win_pct
                    """, a, b, d["matches"], d["a_wins"], wp)
                    h2h_count += 1
                logger.info(f"  H2H records written: {h2h_count}")

                # Batsmen
                bat_count = 0
                for name, d in batsman_data.items():
                    if d["balls"] < 50 or not name or name == "default":
                        continue
                    sr       = (d["runs"] / max(d["balls"], 1)) * 100
                    avg      = d["runs"] / max(d["inn"], 1)
                    pp_sr    = (d["pp_runs"] / max(d["pp_balls"], 1)) * 100
                    death_sr = (d["death_runs"] / max(d["death_balls"], 1)) * 100

                    if sr >= 160:    cls = "S"
                    elif sr >= 135:  cls = "A"
                    elif sr >= 115:  cls = "B"
                    else:            cls = "C"

                    await conn.execute("""
                        INSERT INTO ipl_batsman
                            (name, innings, runs, balls, avg, sr, pp_runs, pp_balls, pp_sr,
                             death_runs, death_balls, death_sr, class)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                        ON CONFLICT (name) DO UPDATE SET
                            innings=EXCLUDED.innings, runs=EXCLUDED.runs, balls=EXCLUDED.balls,
                            avg=EXCLUDED.avg, sr=EXCLUDED.sr, pp_sr=EXCLUDED.pp_sr,
                            death_sr=EXCLUDED.death_sr, class=EXCLUDED.class, updated_at=NOW()
                    """, name, d["inn"], d["runs"], d["balls"],
                         avg, sr, d["pp_runs"], d["pp_balls"], pp_sr,
                         d["death_runs"], d["death_balls"], death_sr, cls)
                    bat_count += 1
                logger.info(f"  Batsman profiles written: {bat_count}")

                # Mark loaded
                await conn.execute("""
                    INSERT INTO ipl_meta (key, value) VALUES ('loaded', 'true')
                    ON CONFLICT (key) DO UPDATE SET value='true'
                """)

        logger.info("IPL CSV load complete.")


# ── Singleton ──────────────────────────────────────────────────────────────────
_instance: Optional[IPLDatabase] = None

async def get_ipl_db() -> Optional[IPLDatabase]:
    global _instance
    if _instance is None:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            return None
        _instance = IPLDatabase(db_url)
        await _instance.init()
    return _instance if _instance._ready else None


# ── CLI loader ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if "--load" in sys.argv:
        idx = sys.argv.index("--load")
        matches_csv    = sys.argv[idx + 1]
        deliveries_csv = sys.argv[idx + 2]

        async def _main():
            db = await get_ipl_db()
            if db is None:
                print("ERROR: DATABASE_URL not set or DB unreachable")
                sys.exit(1)
            await db.load_from_csvs(matches_csv, deliveries_csv)
            print("Done.")

        asyncio.run(_main())
