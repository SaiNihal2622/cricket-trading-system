"""
Session Engine
Predicts powerplay totals, session scores, and phase-specific targets.
Uses statistical models + ML features for prediction.
"""
import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionPrediction:
    phase: str  # powerplay, middle, death
    predicted_runs: float
    confidence_interval_low: float
    confidence_interval_high: float
    probability_over: float  # P(score > line)
    probability_under: float
    recommended_line: float
    value_signal: str  # OVER, UNDER, NEUTRAL
    reasoning: str


# Historical IPL phase averages (from aggregated data)
PHASE_STATS = {
    "powerplay": {
        "avg_runs": 52.4,
        "std_dev": 10.2,
        "avg_wickets": 1.8,
        "top_venues": {
            "Wankhede Stadium": {"avg": 56.2, "std": 9.8},
            "M. A. Chidambaram Stadium": {"avg": 48.7, "std": 11.1},
            "Eden Gardens": {"avg": 53.1, "std": 10.4},
            "Arun Jaitley Stadium": {"avg": 51.8, "std": 9.6},
            "Rajiv Gandhi International Stadium": {"avg": 54.9, "std": 10.7},
            "default": {"avg": 52.4, "std": 10.2}
        }
    },
    "middle": {  # overs 7-15
        "avg_runs": 58.3,
        "std_dev": 12.5,
        "avg_wickets": 2.4
    },
    "death": {  # overs 16-20
        "avg_runs": 52.1,
        "std_dev": 13.8,
        "avg_wickets": 2.9
    }
}

# Team batting strength adjustments
TEAM_ADJUSTMENTS = {
    "Mumbai Indians": 1.08,
    "Chennai Super Kings": 1.05,
    "Royal Challengers Bangalore": 1.12,
    "Kolkata Knight Riders": 1.03,
    "Delhi Capitals": 1.01,
    "Sunrisers Hyderabad": 0.97,
    "Rajasthan Royals": 0.99,
    "Punjab Kings": 1.02,
    "Gujarat Titans": 1.04,
    "Lucknow Super Giants": 1.00,
}


class SessionEngine:
    """
    Predicts cricket session scores using statistical + ML hybrid approach.
    
    Phases:
    - Powerplay (1-6 overs)
    - Middle overs (7-15)
    - Death overs (16-20)
    """

    def __init__(self):
        self.phase_stats = PHASE_STATS
        self.team_adjustments = TEAM_ADJUSTMENTS

    def predict_powerplay(
        self,
        current_over: float,
        current_runs: int,
        current_wickets: int,
        batting_team: str = "",
        venue: str = "",
        batting_quality_score: float = 1.0,  # from ML model
    ) -> SessionPrediction:
        """Predict total powerplay runs (1-6 overs)"""

        if current_over >= 6:
            return self._completed_phase("powerplay", current_runs)

        # Get venue-specific stats
        pp_stats = self.phase_stats["powerplay"]
        venue_data = pp_stats["top_venues"].get(venue, pp_stats["top_venues"]["default"])

        # Remaining balls/overs
        balls_bowled = int(current_over) * 6 + round((current_over % 1) * 10)
        total_pp_balls = 36
        balls_remaining = total_pp_balls - balls_bowled

        # Adjusted run rate for remaining balls
        team_adj = self.team_adjustments.get(batting_team, 1.0)

        # Wicket adjustment: each wicket reduces run rate
        wicket_penalty = max(0.7, 1.0 - (current_wickets * 0.08))

        # Expected runs from remaining balls
        base_rr_per_ball = (venue_data["avg"] / 36) * team_adj * wicket_penalty * batting_quality_score
        expected_remaining = base_rr_per_ball * balls_remaining

        predicted_total = current_runs + expected_remaining

        # Standard deviation scales with remaining balls
        remaining_fraction = balls_remaining / total_pp_balls
        adjusted_std = venue_data["std"] * remaining_fraction

        # Confidence intervals (95%)
        ci_low = max(current_runs, predicted_total - 1.96 * adjusted_std)
        ci_high = predicted_total + 1.96 * adjusted_std

        # Recommended market line
        recommended_line = round(predicted_total / 2.5) * 2.5  # Round to nearest 2.5

        # Over/under probabilities using normal distribution
        try:
            from scipy.stats import norm
            prob_over = float(1 - norm.cdf(recommended_line, predicted_total, adjusted_std))
            prob_under = float(norm.cdf(recommended_line, predicted_total, adjusted_std))
        except ImportError:
            # Fallback without scipy
            prob_over = 0.5 + (0.1 if predicted_total > recommended_line else -0.1)
            prob_under = 1 - prob_over

        value_signal = "NEUTRAL"
        if abs(prob_over - 0.5) > 0.15:
            value_signal = "OVER" if prob_over > 0.5 else "UNDER"

        reasoning = (
            f"Powerplay projection: {current_runs} runs off {current_over:.1f} overs. "
            f"Team adj: {team_adj:.2f}x, Wicket penalty: {wicket_penalty:.2f}x. "
            f"Expected {expected_remaining:.1f} more runs in {balls_remaining} balls."
        )

        return SessionPrediction(
            phase="powerplay",
            predicted_runs=round(predicted_total, 1),
            confidence_interval_low=round(ci_low, 1),
            confidence_interval_high=round(ci_high, 1),
            probability_over=round(prob_over * 100, 1),
            probability_under=round(prob_under * 100, 1),
            recommended_line=recommended_line,
            value_signal=value_signal,
            reasoning=reasoning
        )

    def predict_total_score(
        self,
        current_over: float,
        current_runs: int,
        current_wickets: int,
        batting_team: str = "",
        venue: str = "",
        batting_quality_score: float = 1.0,
    ) -> SessionPrediction:
        """Predict final innings total"""

        if current_over >= 20 or current_wickets >= 10:
            return self._completed_phase("total", current_runs)

        overs_remaining = 20 - current_over
        team_adj = self.team_adjustments.get(batting_team, 1.0)
        wicket_adj = max(0.5, 1.0 - (current_wickets * 0.06))

        # Phase-specific projections
        if current_over < 6:
            # Still in powerplay
            remaining_overs = 20 - current_over
            phase_rr = 8.0 * team_adj * wicket_adj  # 8 RPO base
        elif current_over < 15:
            # Middle overs
            phase_rr = 7.5 * team_adj * wicket_adj
        else:
            # Death overs
            wicket_premium = max(0.7, 1.0 - ((current_wickets - 5) * 0.05)) if current_wickets > 5 else 1.0
            phase_rr = 9.5 * team_adj * wicket_adj * wicket_premium * batting_quality_score

        projected_remaining = phase_rr * overs_remaining
        predicted_total = current_runs + projected_remaining

        # Std dev
        std_dev = 18.0 * (overs_remaining / 20)

        ci_low = max(current_runs, predicted_total - 1.5 * std_dev)
        ci_high = predicted_total + 1.5 * std_dev
        recommended_line = round(predicted_total / 5) * 5

        try:
            from scipy.stats import norm
            prob_over = float(1 - norm.cdf(recommended_line, predicted_total, std_dev))
        except ImportError:
            # Fallback without scipy
            prob_over = 0.5 + (0.1 if predicted_total > recommended_line else -0.1)
        prob_under = 1 - prob_over

        value_signal = "NEUTRAL"
        if abs(prob_over - 0.5) > 0.15:
            value_signal = "OVER" if prob_over > 0.5 else "UNDER"

        reasoning = (
            f"Total projection: {current_runs}/{current_wickets} in {current_over:.1f} overs. "
            f"Projected RR: {phase_rr:.1f}. Est. {projected_remaining:.0f} more runs."
        )

        return SessionPrediction(
            phase="total_score",
            predicted_runs=round(predicted_total, 1),
            confidence_interval_low=round(ci_low, 1),
            confidence_interval_high=round(ci_high, 1),
            probability_over=round(prob_over * 100, 1),
            probability_under=round(prob_under * 100, 1),
            recommended_line=recommended_line,
            value_signal=value_signal,
            reasoning=reasoning
        )

    def predict_phase_score(
        self,
        phase: str,
        current_over: float,
        current_runs: int,
        current_wickets: int,
        batting_team: str = ""
    ) -> SessionPrediction:
        """Generic phase prediction dispatcher"""
        if phase == "powerplay":
            return self.predict_powerplay(
                current_over, current_runs, current_wickets, batting_team
            )
        elif phase == "total":
            return self.predict_total_score(
                current_over, current_runs, current_wickets, batting_team
            )
        return self._completed_phase(phase, current_runs)

    def _completed_phase(self, phase: str, final_runs: int) -> SessionPrediction:
        return SessionPrediction(
            phase=phase,
            predicted_runs=float(final_runs),
            confidence_interval_low=float(final_runs),
            confidence_interval_high=float(final_runs),
            probability_over=0,
            probability_under=100,
            recommended_line=float(final_runs),
            value_signal="NEUTRAL",
            reasoning=f"Phase complete. Final: {final_runs}"
        )
