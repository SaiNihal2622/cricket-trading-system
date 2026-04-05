"""
Session Market Analyzer

Predicts YES/NO for fancy/session markets using:
- Current match state (run rate, wickets, overs)
- Ball-by-ball momentum
- Historical IPL average run rates per phase
- Player strength signals
"""
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


# Historical IPL average runs per over (from cricsheet data, 2019-2024 seasons)
IPL_OVER_AVG = {
    1: 6.3,  2: 6.6,  3: 7.2,  4: 7.5,  5: 7.8,  6: 8.8,   # powerplay
    7: 7.1,  8: 7.3,  9: 7.2, 10: 7.5, 11: 7.6, 12: 7.8,   # middle overs
    13: 8.0, 14: 8.2, 15: 8.5, 16: 9.1, 17: 9.8, 18: 10.3,  # late middle
    19: 11.2, 20: 12.5                                        # death
}

# IPL phase averages
PHASE_AVGS = {
    "powerplay": 50.0,   # 0-6 overs
    "middle":    75.0,   # 7-15 overs
    "death":     55.0,   # 16-20 overs
    "total":     170.0,  # full innings
}

# Venue adjustments (relative to average)
VENUE_FACTOR = {
    "wankhede":   1.08,  # high-scoring
    "chinnaswamy": 1.10,
    "eden gardens": 1.00,
    "chepauk":    0.94,  # slower
    "arun jaitley": 0.98,
    "narendra modi": 1.02,
    "ekana":      0.96,
    "sawai":      1.02,
    "default":    1.00,
}


class SessionRecommendation:
    def __init__(self, label, side, confidence, predicted, line, edge, reasoning, stake_pct=0.02):
        self.label      = label
        self.side       = side           # 'yes' or 'no'
        self.confidence = confidence
        self.predicted  = predicted
        self.line       = line
        self.edge       = edge
        self.reasoning  = reasoning
        self.stake_pct  = stake_pct      # fraction of bankroll to stake

    def to_dict(self) -> dict:
        return {
            "label":      self.label,
            "side":       self.side,
            "confidence": round(self.confidence, 3),
            "predicted":  round(self.predicted, 1),
            "line":       self.line,
            "edge":       round(self.edge, 1),
            "reasoning":  self.reasoning,
            "stake_pct":  self.stake_pct,
        }


class SessionAnalyzer:
    """
    Analyzes session/fancy markets to find value bets.

    Uses three signals:
    1. Statistical: historical IPL over-by-over averages
    2. Momentum: current match run rate vs expected
    3. Situational: wickets remaining, phase, venue
    """

    MIN_CONFIDENCE = 0.52   # don't bet below this
    MIN_EDGE       = 1.5    # minimum predicted vs line difference (runs)

    def analyze_sessions(
        self,
        state: dict,
        sessions: list,
        venue: str = "",
        player_form: Optional[dict] = None,
    ) -> List[SessionRecommendation]:
        """
        Analyze all session markets and return ranked recommendations.

        Args:
            state:       match state dict from Redis
            sessions:    list from royalbook.scrape_match_odds()["sessions"]
            venue:       stadium name for venue factor
            player_form: optional dict of current batsman form

        Returns:
            List of SessionRecommendation sorted by confidence desc
        """
        recommendations = []
        venue_factor = self._venue_factor(venue)

        for session in sessions:
            try:
                rec = self._analyze_single(state, session, venue_factor, player_form)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                logger.debug(f"Session analysis error for {session.get('label')}: {e}")

        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        return recommendations

    def _analyze_single(
        self, state, session, venue_factor, player_form
    ) -> Optional[SessionRecommendation]:
        label    = session.get("label", "")
        yes_line = session.get("yes")   # run threshold for YES bet
        no_line  = session.get("no")
        yes_odds = session.get("yes_odds", 1.83)
        no_odds  = session.get("no_odds", 1.97)

        if not label or not (yes_line or no_line):
            return None

        # Use midpoint as the line
        line = None
        if yes_line and no_line:
            line = (yes_line + no_line) / 2
        elif yes_line:
            line = yes_line
        else:
            line = no_line

        if line is None or line <= 0:
            return None

        # Parse what this session is about
        predicted = self._predict_session(state, label, line, venue_factor, player_form)
        if predicted is None:
            return None

        edge = predicted - line
        abs_edge = abs(edge)

        if abs_edge < self.MIN_EDGE:
            return None

        side = "yes" if edge > 0 else "no"

        # Confidence: based on edge magnitude and situational clarity
        base_confidence = min(0.75, 0.5 + abs_edge / 25)

        # Adjust for wickets (more wickets = less confident in run totals)
        wickets = int(state.get("total_wickets", 0))
        conf_adj = -0.05 * (wickets // 3)  # penalize 5% per 3 wickets lost
        confidence = max(0.40, min(0.80, base_confidence + conf_adj))

        if confidence < self.MIN_CONFIDENCE:
            return None

        # Stake: size by confidence (1-3% of bankroll)
        stake_pct = 0.01 + (confidence - 0.5) * 0.04

        reasoning = (
            f"Predicted {predicted:.0f} runs vs line {line:.0f} → "
            f"{'OVER' if side == 'yes' else 'UNDER'} by {abs_edge:.1f}. "
            f"Confidence: {confidence:.0%}"
        )

        return SessionRecommendation(
            label=label,
            side=side,
            confidence=confidence,
            predicted=predicted,
            line=line,
            edge=edge,
            reasoning=reasoning,
            stake_pct=round(stake_pct, 3),
        )

    def _predict_session(
        self, state, label, line, venue_factor, player_form
    ) -> Optional[float]:
        """
        Predict the session outcome.
        Handles: 'X Over Runs', 'Powerplay', 'Total Runs', etc.
        """
        overs      = float(state.get("overs", 0))
        runs       = int(state.get("total_runs", 0))
        wickets    = int(state.get("total_wickets", 0))
        crr        = float(state.get("run_rate", 0))
        innings    = int(state.get("innings", 1))
        label_low  = label.lower()

        # ── "X Over Runs Team" ───────────────────────────────────────────
        over_match = re.search(r'(\d+)\s*over', label_low)
        if over_match:
            target_over = int(over_match.group(1))
            return self._predict_over_runs(
                target_over, overs, runs, wickets, crr, venue_factor, innings
            )

        # ── Powerplay (0-6 overs) ────────────────────────────────────────
        if "powerplay" in label_low or ("6 over" in label_low and "runs" in label_low):
            if overs < 6:
                projected = runs + crr * (6 - overs)
                return projected * venue_factor
            return None  # powerplay done

        # ── Total / Innings runs ─────────────────────────────────────────
        if "total" in label_low or "innings" in label_low or "match" in label_low:
            remaining = max(0, 20 - overs)
            # Projected runs = current + expected in remaining overs
            avg_remaining = sum(
                IPL_OVER_AVG.get(int(overs) + i + 1, 8.5)
                for i in range(int(remaining))
            )
            # Adjust for current CRR momentum
            momentum = max(0.6, min(1.4, crr / 8.0)) if crr > 0 else 1.0
            # Wicket deduction factor
            wicket_factor = max(0.7, 1.0 - wickets * 0.03)
            projected = runs + avg_remaining * momentum * wicket_factor * venue_factor
            return projected

        # ── "Session" or generic fancy ───────────────────────────────────
        if "session" in label_low:
            # Generic: assume it's a next-N-overs target
            remaining = max(0, 20 - overs)
            if remaining <= 0:
                return None
            next_5 = sum(IPL_OVER_AVG.get(int(overs) + i + 1, 8.0) for i in range(5))
            momentum = max(0.6, min(1.4, crr / 8.0)) if crr > 0 else 1.0
            return next_5 * momentum * venue_factor

        return None

    def _predict_over_runs(
        self, target_over, current_over, runs, wickets, crr, venue_factor, innings
    ) -> Optional[float]:
        """Predict cumulative runs by target_over."""
        if target_over <= current_over:
            return None  # this over has passed

        # Sum expected runs from now to target_over
        expected_additional = 0.0
        for o in range(int(current_over) + 1, target_over + 1):
            avg = IPL_OVER_AVG.get(o, 8.0)
            # Momentum blend
            if crr > 0:
                momentum = max(0.6, min(1.5, crr / avg))
                avg = avg * 0.6 + avg * momentum * 0.4
            # Wicket impact
            wicket_factor = max(0.65, 1.0 - wickets * 0.04)
            expected_additional += avg * wicket_factor * venue_factor

        # Current over partial contribution
        partial_over_frac = current_over % 1
        if partial_over_frac > 0:
            current_over_avg = IPL_OVER_AVG.get(int(current_over), 8.0)
            expected_additional -= current_over_avg * (1 - partial_over_frac)

        return runs + max(0, expected_additional)

    def _venue_factor(self, venue: str) -> float:
        venue_low = venue.lower()
        for key, factor in VENUE_FACTOR.items():
            if key in venue_low:
                return factor
        return VENUE_FACTOR["default"]

    def get_best_session_trade(
        self,
        state: dict,
        sessions: list,
        bankroll: float = 10000.0,
        venue: str = "",
    ) -> Optional[dict]:
        """
        Returns the single best session trade opportunity, or None.
        Includes stake amount recommendation.
        """
        recs = self.analyze_sessions(state, sessions, venue)
        if not recs:
            return None
        best = recs[0]
        stake = round(bankroll * best.stake_pct / 10) * 10  # round to nearest 10
        stake = max(50.0, stake)

        result = best.to_dict()
        result["recommended_stake"] = stake
        return result
