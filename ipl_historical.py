"""IPL Historical Data Module - 18 seasons of IPL data (2008-2025).

Downloads and caches ball-by-ball data from Cricsheet.org.
Provides team stats, venue stats, head-to-head records, and player stats
to enrich AI model prompts for higher accuracy predictions.
"""
import os
import io
import csv
import json
import zipfile
import logging
from collections import defaultdict
from typing import Optional
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CRICSHEET_URL = "https://cricsheet.org/downloads/ipl_csv2.zip"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(DATA_DIR, "ipl_all_matches.csv")
STATS_CACHE = os.path.join(DATA_DIR, "ipl_stats.json")


def download_ipl_data(force: bool = False) -> str:
    """Download IPL ball-by-ball data from Cricsheet.org (18 seasons)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if os.path.exists(CACHE_FILE) and not force:
        logger.info(f"Using cached IPL data: {CACHE_FILE}")
        return CACHE_FILE
    
    logger.info(f"Downloading IPL data from {CRICSHEET_URL}...")
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        resp = client.get(CRICSHEET_URL)
        resp.raise_for_status()
    
    logger.info(f"Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")
    
    # Extract and merge all CSVs
    all_rows = []
    headers = None
    
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_files = [f for f in zf.infolist() if f.filename.endswith(".csv") and not f.is_dir()]
        logger.info(f"Found {len(csv_files)} match CSV files")
        
        for csv_file in csv_files:
            try:
                content = zf.read(csv_file.filename).decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
                
                # Add match_id from filename
                match_id = os.path.splitext(os.path.basename(csv_file.filename))[0]
                for row in rows:
                    row["match_id"] = match_id
                
                if rows:
                    if headers is None:
                        headers = list(rows[0].keys())
                    all_rows.extend(rows)
            except Exception as e:
                logger.warning(f"Skipping {csv_file.filename}: {e}")
    
    # Write merged CSV
    if all_rows and headers:
        with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_rows)
        logger.info(f"Merged {len(all_rows)} rows from {len(csv_files)} matches → {CACHE_FILE}")
    
    return CACHE_FILE


def build_stats(force_rebuild: bool = False) -> dict:
    """Build comprehensive IPL statistics from historical data."""
    if os.path.exists(STATS_CACHE) and not force_rebuild:
        with open(STATS_CACHE, "r") as f:
            return json.load(f)
    
    # Download data if needed
    csv_path = download_ipl_data()
    
    logger.info("Building IPL historical statistics...")
    
    # Stats accumulators
    team_wins = defaultdict(int)
    team_matches = defaultdict(int)
    team_total_runs = defaultdict(int)
    team_total_innings = defaultdict(int)
    venue_scores = defaultdict(list)
    venue_powerplay = defaultdict(list)
    h2h = defaultdict(lambda: defaultdict(int))  # team_a -> team_b -> wins
    h2h_total = defaultdict(lambda: defaultdict(int))
    team_at_venue = defaultdict(lambda: defaultdict(list))
    season_team_runs = defaultdict(lambda: defaultdict(list))
    
    # Parse ball-by-ball data
    matches = defaultdict(lambda: defaultdict(list))  # match_id -> innings -> balls
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            match_id = row.get("match_id", "")
            innings = row.get("innings", "1")
            matches[match_id][innings].append(row)
    
    # Process each match
    for match_id, innings_data in matches.items():
        # Get match-level info from first ball
        first_ball = list(innings_data.values())[0][0] if innings_data else {}
        team1 = first_ball.get("batting_team", "")
        team2 = first_ball.get("bowling_team", "")
        venue = first_ball.get("venue", "")
        season = first_ball.get("season", "")
        
        if not team1 or not team2:
            continue
        
        team_matches[team1] += 1
        team_matches[team2] += 1
        
        # Calculate innings scores
        innings_scores = {}
        for innings_num, balls in innings_data.items():
            total_runs = sum(int(b.get("runs_off_bat", 0) or 0) + 
                          int(b.get("extras", 0) or 0) for b in balls)
            innings_scores[innings_num] = {
                "runs": total_runs,
                "batting_team": balls[0].get("batting_team", "") if balls else "",
                "bowling_team": balls[0].get("bowling_team", "") if balls else "",
            }
            
            batting_team = innings_scores[innings_num]["batting_team"]
            team_total_runs[batting_team] += total_runs
            team_total_innings[batting_team] += 1
            
            if venue:
                venue_scores[venue].append(total_runs)
                team_at_venue[batting_team][venue].append(total_runs)
            
            if season:
                season_team_runs[season][batting_team].append(total_runs)
            
            # Powerplay (first 36 balls = 6 overs)
            pp_balls = balls[:36]
            pp_runs = sum(int(b.get("runs_off_bat", 0) or 0) + 
                         int(b.get("extras", 0) or 0) for b in pp_balls)
            if venue:
                venue_powerplay[venue].append(pp_runs)
        
        # Determine winner (team with higher score)
        if len(innings_scores) >= 2:
            scores = list(innings_scores.values())
            if scores[0]["runs"] > scores[1]["runs"]:
                winner = scores[0]["batting_team"]
            elif scores[1]["runs"] > scores[0]["runs"]:
                winner = scores[1]["batting_team"]
            else:
                winner = "tie"
            
            if winner != "tie":
                team_wins[winner] += 1
                h2h[winner][team2 if winner == team1 else team1] += 1
            
            h2h_total[team1][team2] += 1
            h2h_total[team2][team1] += 1
    
    # Build stats dict
    stats = {
        "team_stats": {},
        "venue_stats": {},
        "head_to_head": {},
        "team_at_venue": {},
        "total_matches": len(matches),
        "seasons_covered": sorted(set(
            list(innings_data.values())[0][0].get("season", "")
            for match_id, innings_data in matches.items()
            if innings_data
        )),
    }
    
    # Team stats
    for team in team_matches:
        matches_played = team_matches[team]
        wins = team_wins.get(team, 0)
        total_runs = team_total_runs.get(team, 0)
        total_innings = team_total_innings.get(team, 1)
        stats["team_stats"][team] = {
            "matches": matches_played,
            "wins": wins,
            "losses": matches_played - wins,
            "win_rate": round(wins / matches_played, 3) if matches_played > 0 else 0,
            "avg_score": round(total_runs / total_innings, 1) if total_innings > 0 else 0,
        }
    
    # Venue stats
    for venue, scores in venue_scores.items():
        stats["venue_stats"][venue] = {
            "matches": len(scores) // 2,  # 2 innings per match
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "avg_powerplay": round(
                sum(venue_powerplay.get(venue, [0])) / max(len(venue_powerplay.get(venue, [1])), 1), 1
            ),
            "high_score": max(scores) if scores else 0,
            "low_score": min(scores) if scores else 0,
        }
    
    # Head-to-head
    for team_a in h2h_total:
        stats["head_to_head"][team_a] = {}
        for team_b in h2h_total[team_a]:
            total = h2h_total[team_a][team_b]
            wins_a = h2h.get(team_a, {}).get(team_b, 0)
            stats["head_to_head"][team_a][team_b] = {
                "matches": total,
                "wins": wins_a,
                "losses": total - wins_a,
                "win_rate": round(wins_a / total, 3) if total > 0 else 0,
            }
    
    # Team at venue
    for team in team_at_venue:
        stats["team_at_venue"][team] = {}
        for venue, scores in team_at_venue[team].items():
            stats["team_at_venue"][team][venue] = {
                "matches": len(scores),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "high_score": max(scores) if scores else 0,
            }
    
    # Cache stats
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATS_CACHE, "w") as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Built stats: {stats['total_matches']} matches, "
                f"{len(stats['team_stats'])} teams, "
                f"{len(stats['venue_stats'])} venues, "
                f"seasons: {stats['seasons_covered']}")
    
    return stats


def get_team_stats(team_name: str, stats: Optional[dict] = None) -> dict:
    """Get historical stats for a team."""
    if stats is None:
        stats = build_stats()
    return stats.get("team_stats", {}).get(team_name, {})


def get_venue_stats(venue: str, stats: Optional[dict] = None) -> dict:
    """Get historical stats for a venue."""
    if stats is None:
        stats = build_stats()
    return stats.get("venue_stats", {}).get(venue, {})


def get_head_to_head(team_a: str, team_b: str, stats: Optional[dict] = None) -> dict:
    """Get head-to-head record between two teams."""
    if stats is None:
        stats = build_stats()
    return stats.get("head_to_head", {}).get(team_a, {}).get(team_b, {})


def get_team_at_venue(team: str, venue: str, stats: Optional[dict] = None) -> dict:
    """Get team's historical performance at a specific venue."""
    if stats is None:
        stats = build_stats()
    return stats.get("team_at_venue", {}).get(team, {}).get(venue, {})


def enrich_prompt_context(
    home_team: str,
    away_team: str,
    venue: str,
    stats: Optional[dict] = None,
) -> dict:
    """Get all historical context for a match to enrich AI prompts."""
    if stats is None:
        stats = build_stats()
    
    return {
        "home_team_stats": get_team_stats(home_team, stats),
        "away_team_stats": get_team_stats(away_team, stats),
        "venue_stats": get_venue_stats(venue, stats),
        "head_to_head": get_head_to_head(home_team, away_team, stats),
        "home_at_venue": get_team_at_venue(home_team, venue, stats),
        "away_at_venue": get_team_at_venue(away_team, venue, stats),
        "total_matches_in_db": stats.get("total_matches", 0),
        "seasons_covered": stats.get("seasons_covered", []),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Downloading and building IPL historical stats...")
    stats = build_stats(force_rebuild=True)
    print(f"\nTotal matches: {stats['total_matches']}")
    print(f"Seasons: {stats['seasons_covered']}")
    print(f"\nTeam stats:")
    for team, s in sorted(stats["team_stats"].items(), key=lambda x: -x[1]["win_rate"]):
        print(f"  {team}: {s['wins']}/{s['matches']} ({s['win_rate']:.1%}) avg={s['avg_score']}")