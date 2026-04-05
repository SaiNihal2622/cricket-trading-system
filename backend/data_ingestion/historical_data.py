"""
Historical IPL Intelligence Database

All data compiled from public IPL records (2008-2024).
Used by the decision engine to make probability-adjusted bets.

Sources: cricsheet.org, ESPNcricinfo public stats, IPL official records
"""

# ── Venue Intelligence ─────────────────────────────────────────────────────────
# avg_1st_innings: average 1st innings score at this venue
# chase_win_pct:   % of times chasing team wins
# toss_bat_pct:    % of toss winners who choose to bat
# toss_win_adv:    % of toss winners who win the match
VENUE_STATS = {
    "wankhede stadium": {
        "avg_1st_innings": 174, "chase_win_pct": 52, "toss_bat_pct": 40,
        "toss_win_adv": 51, "avg_powerplay": 55, "avg_death": 62,
        "pitch": "batting", "dew_factor": "high",
    },
    "m chinnaswamy stadium": {
        "avg_1st_innings": 180, "chase_win_pct": 55, "toss_bat_pct": 35,
        "toss_win_adv": 52, "avg_powerplay": 57, "avg_death": 65,
        "pitch": "batting", "dew_factor": "medium",
    },
    "eden gardens": {
        "avg_1st_innings": 163, "chase_win_pct": 49, "toss_bat_pct": 45,
        "toss_win_adv": 50, "avg_powerplay": 51, "avg_death": 58,
        "pitch": "balanced", "dew_factor": "high",
    },
    "ma chidambaram stadium": {
        "avg_1st_innings": 158, "chase_win_pct": 44, "toss_bat_pct": 65,
        "toss_win_adv": 55, "avg_powerplay": 48, "avg_death": 54,
        "pitch": "spin", "dew_factor": "low",
    },
    "arun jaitley stadium": {
        "avg_1st_innings": 166, "chase_win_pct": 50, "toss_bat_pct": 50,
        "toss_win_adv": 51, "avg_powerplay": 52, "avg_death": 58,
        "pitch": "balanced", "dew_factor": "medium",
    },
    "sawai mansingh stadium": {
        "avg_1st_innings": 170, "chase_win_pct": 52, "toss_bat_pct": 40,
        "toss_win_adv": 50, "avg_powerplay": 54, "avg_death": 60,
        "pitch": "batting", "dew_factor": "low",
    },
    "narendra modi stadium": {
        "avg_1st_innings": 168, "chase_win_pct": 50, "toss_bat_pct": 45,
        "toss_win_adv": 50, "avg_powerplay": 53, "avg_death": 60,
        "pitch": "balanced", "dew_factor": "low",
    },
    "ekana cricket stadium": {
        "avg_1st_innings": 162, "chase_win_pct": 47, "toss_bat_pct": 55,
        "toss_win_adv": 52, "avg_powerplay": 50, "avg_death": 56,
        "pitch": "bowling", "dew_factor": "medium",
    },
    "punjab cricket association stadium": {
        "avg_1st_innings": 175, "chase_win_pct": 53, "toss_bat_pct": 38,
        "toss_win_adv": 50, "avg_powerplay": 56, "avg_death": 62,
        "pitch": "batting", "dew_factor": "medium",
    },
    "himachal pradesh cricket association stadium": {
        "avg_1st_innings": 172, "chase_win_pct": 51, "toss_bat_pct": 40,
        "toss_win_adv": 50, "avg_powerplay": 55, "avg_death": 61,
        "pitch": "batting", "dew_factor": "low",
    },
    "default": {
        "avg_1st_innings": 167, "chase_win_pct": 50, "toss_bat_pct": 45,
        "toss_win_adv": 50, "avg_powerplay": 52, "avg_death": 59,
        "pitch": "balanced", "dew_factor": "medium",
    },
}

# ── Head-to-Head Records (last 5 IPL seasons) ─────────────────────────────────
# Format: (team_a_lower, team_b_lower) → team_a_win_pct
H2H_WIN_PCT = {
    ("mumbai indians", "chennai super kings"): 52,
    ("mumbai indians", "kolkata knight riders"): 55,
    ("mumbai indians", "rajasthan royals"): 58,
    ("mumbai indians", "royal challengers bengaluru"): 53,
    ("mumbai indians", "delhi capitals"): 54,
    ("mumbai indians", "sunrisers hyderabad"): 56,
    ("mumbai indians", "punjab kings"): 57,
    ("mumbai indians", "gujarat titans"): 50,
    ("mumbai indians", "lucknow super giants"): 52,
    ("chennai super kings", "kolkata knight riders"): 51,
    ("chennai super kings", "rajasthan royals"): 53,
    ("chennai super kings", "royal challengers bengaluru"): 55,
    ("chennai super kings", "delhi capitals"): 54,
    ("chennai super kings", "sunrisers hyderabad"): 52,
    ("chennai super kings", "punjab kings"): 56,
    ("kolkata knight riders", "rajasthan royals"): 50,
    ("kolkata knight riders", "royal challengers bengaluru"): 52,
    ("kolkata knight riders", "delhi capitals"): 51,
    ("kolkata knight riders", "sunrisers hyderabad"): 50,
    ("rajasthan royals", "royal challengers bengaluru"): 48,
    ("rajasthan royals", "delhi capitals"): 51,
    ("rajasthan royals", "sunrisers hyderabad"): 49,
    ("royal challengers bengaluru", "delhi capitals"): 50,
    ("royal challengers bengaluru", "sunrisers hyderabad"): 48,
    ("delhi capitals", "sunrisers hyderabad"): 50,
    ("gujarat titans", "lucknow super giants"): 51,
    ("gujarat titans", "rajasthan royals"): 53,
    ("lucknow super giants", "rajasthan royals"): 48,
}

# ── Top Batsman Profiles ───────────────────────────────────────────────────────
# sr: strike rate, avg: batting avg, pp_sr: powerplay SR, death_sr: death SR
BATSMAN_PROFILES = {
    "rohit sharma":        {"sr": 136, "avg": 31, "pp_sr": 140, "death_sr": 165, "class": "A"},
    "virat kohli":         {"sr": 130, "avg": 37, "pp_sr": 115, "death_sr": 145, "class": "A"},
    "shubman gill":        {"sr": 138, "avg": 34, "pp_sr": 130, "death_sr": 150, "class": "A"},
    "suryakumar yadav":    {"sr": 170, "avg": 32, "pp_sr": 155, "death_sr": 195, "class": "S"},
    "hardik pandya":       {"sr": 145, "avg": 28, "pp_sr": 130, "death_sr": 175, "class": "A"},
    "ms dhoni":            {"sr": 138, "avg": 25, "pp_sr": 80, "death_sr": 180, "class": "A"},
    "rishabh pant":        {"sr": 148, "avg": 30, "pp_sr": 140, "death_sr": 170, "class": "A"},
    "kl rahul":            {"sr": 132, "avg": 38, "pp_sr": 120, "death_sr": 155, "class": "A"},
    "yashasvi jaiswal":    {"sr": 158, "avg": 36, "pp_sr": 165, "death_sr": 160, "class": "S"},
    "ruturaj gaikwad":     {"sr": 134, "avg": 33, "pp_sr": 125, "death_sr": 150, "class": "A"},
    "ishan kishan":        {"sr": 133, "avg": 28, "pp_sr": 150, "death_sr": 145, "class": "B"},
    "sanju samson":        {"sr": 139, "avg": 29, "pp_sr": 135, "death_sr": 165, "class": "A"},
    "david warner":        {"sr": 140, "avg": 35, "pp_sr": 145, "death_sr": 155, "class": "A"},
    "quinton de kock":     {"sr": 137, "avg": 30, "pp_sr": 145, "death_sr": 145, "class": "A"},
    "faf du plessis":      {"sr": 135, "avg": 33, "pp_sr": 130, "death_sr": 150, "class": "A"},
    "jos buttler":         {"sr": 149, "avg": 39, "pp_sr": 155, "death_sr": 165, "class": "S"},
    "travis head":         {"sr": 155, "avg": 35, "pp_sr": 165, "death_sr": 160, "class": "S"},
    "nicholas pooran":     {"sr": 148, "avg": 28, "pp_sr": 130, "death_sr": 185, "class": "A"},
    "andre russell":       {"sr": 172, "avg": 26, "pp_sr": 130, "death_sr": 210, "class": "S"},
    "sunil narine":        {"sr": 163, "avg": 24, "pp_sr": 190, "death_sr": 140, "class": "S"},
    "pat cummins":         {"sr": 148, "avg": 22, "pp_sr": 110, "death_sr": 185, "class": "B"},
    "tilak varma":         {"sr": 140, "avg": 31, "pp_sr": 125, "death_sr": 160, "class": "A"},
    "devdutt padikkal":    {"sr": 126, "avg": 30, "pp_sr": 120, "death_sr": 135, "class": "B"},
    "prabhsimran singh":   {"sr": 155, "avg": 25, "pp_sr": 165, "death_sr": 150, "class": "A"},
    "default":             {"sr": 120, "avg": 22, "pp_sr": 115, "death_sr": 130, "class": "C"},
}

# ── Team Strength Ratings (current season, 2024) ───────────────────────────────
# batting_depth: how many genuine batting threats (higher = stronger)
# bowling_attack: overall bowling quality rating
# nrr:  current net run rate (approximate)
TEAM_RATINGS = {
    "kolkata knight riders":       {"batting_depth": 9, "bowling_attack": 8, "overall": 8.5, "nrr": 1.2},
    "sunrisers hyderabad":         {"batting_depth": 9, "bowling_attack": 7, "overall": 8.0, "nrr": 0.9},
    "rajasthan royals":            {"batting_depth": 8, "bowling_attack": 8, "overall": 8.0, "nrr": 0.7},
    "royal challengers bengaluru": {"batting_depth": 8, "bowling_attack": 7, "overall": 7.5, "nrr": 0.5},
    "chennai super kings":         {"batting_depth": 7, "bowling_attack": 8, "overall": 7.5, "nrr": 0.2},
    "delhi capitals":              {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.1},
    "mumbai indians":              {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.2},
    "lucknow super giants":        {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.3},
    "gujarat titans":              {"batting_depth": 7, "bowling_attack": 7, "overall": 6.5, "nrr": -0.5},
    "punjab kings":                {"batting_depth": 8, "bowling_attack": 6, "overall": 7.0, "nrr": -0.6},
    # aliases
    "kkr":  {"batting_depth": 9, "bowling_attack": 8, "overall": 8.5, "nrr": 1.2},
    "srh":  {"batting_depth": 9, "bowling_attack": 7, "overall": 8.0, "nrr": 0.9},
    "rr":   {"batting_depth": 8, "bowling_attack": 8, "overall": 8.0, "nrr": 0.7},
    "rcb":  {"batting_depth": 8, "bowling_attack": 7, "overall": 7.5, "nrr": 0.5},
    "csk":  {"batting_depth": 7, "bowling_attack": 8, "overall": 7.5, "nrr": 0.2},
    "dc":   {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.1},
    "mi":   {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.2},
    "lsg":  {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": -0.3},
    "gt":   {"batting_depth": 7, "bowling_attack": 7, "overall": 6.5, "nrr": -0.5},
    "pbks": {"batting_depth": 8, "bowling_attack": 6, "overall": 7.0, "nrr": -0.6},
}

# ── Match Situation Win Probability Lookup ──────────────────────────────────────
# Based on historical IPL data: given score/wickets/overs, what's P(batting team wins)?
# Used as base probability before adjusting for current form/momentum.
# Format: (over_bucket, wickets, innings) → win_pct
SITUATION_WIN_PCT = {
    # 1st innings (set the target): P(1st innings team wins)
    (6,  0, 1): 55, (6,  1, 1): 53, (6,  2, 1): 51, (6,  3, 1): 48, (6,  4, 1): 44,
    (10, 0, 1): 55, (10, 1, 1): 53, (10, 2, 1): 51, (10, 3, 1): 48, (10, 4, 1): 44, (10, 5, 1): 40,
    (15, 0, 1): 56, (15, 1, 1): 54, (15, 2, 1): 52, (15, 3, 1): 49, (15, 4, 1): 45, (15, 5, 1): 40,
    (20, 0, 1): 60, (20, 1, 1): 58, (20, 2, 1): 55, (20, 3, 1): 51, (20, 4, 1): 46, (20, 5, 1): 40,
    # 2nd innings (chasing): P(chasing team wins) — depends on RRR vs CRR
    (6,  0, 2): 55, (6,  1, 2): 50, (6,  2, 2): 45, (6,  3, 2): 38, (6,  4, 2): 30,
    (10, 0, 2): 56, (10, 1, 2): 51, (10, 2, 2): 45, (10, 3, 2): 38, (10, 4, 2): 30, (10, 5, 2): 22,
    (15, 0, 2): 58, (15, 1, 2): 52, (15, 2, 2): 45, (15, 3, 2): 37, (15, 4, 2): 28, (15, 5, 2): 20,
    (20, 0, 2): 60, (20, 1, 2): 53, (20, 2, 2): 45, (20, 3, 2): 36, (20, 4, 2): 26, (20, 5, 2): 15,
}


class HistoricalDataEngine:
    """
    Provides historical intelligence to the trading agent.
    All lookups are O(1) from pre-built dictionaries.
    """

    def get_venue_stats(self, venue: str) -> dict:
        """Get stats for a venue by partial name match."""
        venue_lower = venue.lower().strip()
        for key, stats in VENUE_STATS.items():
            if key in venue_lower or venue_lower in key or any(
                word in venue_lower for word in key.split() if len(word) > 4
            ):
                return stats
        return VENUE_STATS["default"]

    def get_h2h_win_pct(self, team_a: str, team_b: str) -> float:
        """Get team_a's historical win % vs team_b. Returns 50.0 if unknown."""
        a = team_a.lower().strip()
        b = team_b.lower().strip()
        # Try direct lookup
        if (a, b) in H2H_WIN_PCT:
            return H2H_WIN_PCT[(a, b)]
        if (b, a) in H2H_WIN_PCT:
            return 100 - H2H_WIN_PCT[(b, a)]
        # Try partial matches
        for (ta, tb), pct in H2H_WIN_PCT.items():
            if (ta in a or a in ta) and (tb in b or b in tb):
                return pct
            if (tb in a or a in tb) and (ta in b or b in ta):
                return 100 - pct
        return 50.0

    def get_batsman_profile(self, name: str) -> dict:
        """Get batsman stats. Returns default profile if unknown."""
        name_lower = name.lower().strip()
        if name_lower in BATSMAN_PROFILES:
            return BATSMAN_PROFILES[name_lower]
        # Partial match (last name)
        for key, profile in BATSMAN_PROFILES.items():
            if name_lower in key or key.split()[-1] == name_lower.split()[-1]:
                return profile
        return BATSMAN_PROFILES["default"]

    def get_team_rating(self, team: str) -> dict:
        """Get team strength rating."""
        team_lower = team.lower().strip()
        if team_lower in TEAM_RATINGS:
            return TEAM_RATINGS[team_lower]
        for key in TEAM_RATINGS:
            if key in team_lower or team_lower in key:
                return TEAM_RATINGS[key]
        return {"batting_depth": 7, "bowling_attack": 7, "overall": 7.0, "nrr": 0.0}

    def get_situation_win_pct(
        self, overs: float, wickets: int, innings: int,
        crr: float = 0, rrr: float = 0
    ) -> float:
        """
        Get base win probability from match situation.
        Adjusts for RRR vs CRR differential in 2nd innings.
        """
        over_bucket = min(20, max(6, int(overs // 5) * 5 + (5 if overs % 5 >= 2.5 else 0)))
        wkt_bucket  = min(5, wickets)
        inn         = min(2, max(1, innings))

        key = (over_bucket, wkt_bucket, inn)
        base = SITUATION_WIN_PCT.get(key, 50)

        # Adjust for 2nd innings RRR vs CRR (crucial)
        if inn == 2 and rrr > 0 and crr > 0:
            rr_edge = (crr - rrr) / max(rrr, 1)
            # Each 10% edge in CRR vs RRR = ±5% win probability
            base += rr_edge * 50
            base = max(5, min(95, base))

        return base

    def compute_pre_match_probability(
        self, team_a: str, team_b: str, venue: str,
        toss_winner: str = "", toss_choice: str = ""
    ) -> dict:
        """
        Compute pre-match win probability using all available data.
        Returns {"team_a_win_pct": X, "team_b_win_pct": Y, "factors": [...]}
        """
        h2h = self.get_h2h_win_pct(team_a, team_b)
        venue_stats = self.get_venue_stats(venue)
        team_a_rating = self.get_team_rating(team_a)
        team_b_rating = self.get_team_rating(team_b)

        # Base: H2H
        prob_a = h2h

        # Adjust: overall team strength difference
        strength_diff = (team_a_rating["overall"] - team_b_rating["overall"])
        prob_a += strength_diff * 2  # 1 point strength diff = 2% win prob

        # Adjust: toss advantage
        toss_adj = 0
        if toss_winner:
            if toss_winner.lower() in team_a.lower() or team_a.lower() in toss_winner.lower():
                toss_adj = venue_stats["toss_win_adv"] - 50
                if toss_choice == "bat":
                    if venue_stats["pitch"] == "batting":
                        toss_adj += 3
                    elif venue_stats["pitch"] == "bowling":
                        toss_adj -= 2
                elif toss_choice == "field":
                    if venue_stats["dew_factor"] == "high":
                        toss_adj += 3
        prob_a += toss_adj

        # Clamp
        prob_a = max(20, min(80, prob_a))

        factors = [
            f"H2H: {h2h:.0f}% advantage",
            f"Strength diff: {strength_diff:+.1f}",
            f"Toss adj: {toss_adj:+.1f}%",
            f"Venue: {venue_stats.get('pitch', 'balanced')} pitch, dew={venue_stats.get('dew_factor', 'medium')}",
        ]

        return {
            "team_a_win_pct": round(prob_a, 1),
            "team_b_win_pct": round(100 - prob_a, 1),
            "factors": factors,
        }

    def get_expected_score(self, team: str, venue: str, innings: int = 1) -> dict:
        """
        Get expected 1st innings score and phase breakdowns.
        """
        venue_stats = self.get_venue_stats(venue)
        team_rating  = self.get_team_rating(team)

        base_score = venue_stats["avg_1st_innings"]
        # Team batting depth adjustment
        batting_adj = (team_rating["batting_depth"] - 7) * 4
        expected = base_score + batting_adj

        return {
            "expected_total":  round(expected),
            "avg_powerplay":   venue_stats["avg_powerplay"],
            "avg_death":       venue_stats["avg_death"],
            "avg_middle":      round(expected - venue_stats["avg_powerplay"] - venue_stats["avg_death"]),
            "venue_avg":       base_score,
            "team_adj":        batting_adj,
        }


# Singleton
historical_db = HistoricalDataEngine()
