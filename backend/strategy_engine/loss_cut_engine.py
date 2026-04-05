"""
Loss Cut Engine
Calculates hedge positions and triggers loss cut signals
based on odds movements, wickets, and match events.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class LossCutResult:
    should_trigger: bool
    hedge_amount: float
    hedge_profit: float
    loss_reduction: float
    trigger_reason: str
    urgency: str  # LOW, MEDIUM, HIGH, CRITICAL


class LossCutEngine:
    """
    Core loss cut strategy engine.
    
    Formula:
        hedge = (stake × entry_odds) / current_odds
        guaranteed_return = stake × entry_odds
        profit = guaranteed_return - (stake + hedge)
    
    Triggers:
        - Odds drop beyond threshold
        - Wicket in key over
        - Powerplay momentum shift
        - Run rate collapse
    """

    def __init__(self):
        self.odds_drop_threshold = settings.ODDS_DROP_THRESHOLD
        self.critical_over_ranges = [(1, 6), (15, 20)]  # Powerplay + Death overs

    def calculate_hedge(
        self,
        stake: float,
        entry_odds: float,
        current_odds: float
    ) -> tuple[float, float]:
        """
        Calculate hedge stake and resulting profit/loss.
        
        Returns: (hedge_amount, net_profit)
        """
        if current_odds <= 0 or entry_odds <= 0:
            return 0.0, 0.0

        hedge = (stake * entry_odds) / current_odds
        # Net profit = guaranteed return - total staked
        guaranteed_return = stake * entry_odds
        total_staked = stake + hedge
        profit = guaranteed_return - total_staked

        return round(hedge, 2), round(profit, 2)

    def evaluate(
        self,
        stake: float,
        entry_odds: float,
        current_team_odds: float,  # odds for team you backed
        current_over: float,
        wickets_fallen: int,
        run_rate: float,
        required_rr: float,
        is_wicket_just_fell: bool = False,
        win_probability: float = 0.5,
    ) -> LossCutResult:
        """
        Evaluate whether a loss cut should be executed.
        """
        triggers = []
        urgency = "LOW"

        # 1. Odds drift check
        if entry_odds > 0:
            odds_change_pct = (current_team_odds - entry_odds) / entry_odds
            # If our team's odds have shortened (gone DOWN) = bad for backer
            if odds_change_pct < -self.odds_drop_threshold:
                triggers.append(
                    f"Odds dropped {abs(odds_change_pct)*100:.1f}% "
                    f"({entry_odds:.2f} → {current_team_odds:.2f})"
                )
                urgency = "HIGH" if odds_change_pct < -0.25 else "MEDIUM"

        # 2. Wicket in critical over
        if is_wicket_just_fell:
            if any(start <= current_over <= end for start, end in self.critical_over_ranges):
                triggers.append(f"Wicket fallen in critical over {current_over:.1f}")
                urgency = "HIGH"
            elif wickets_fallen >= 5:
                triggers.append(f"5+ wickets down ({wickets_fallen} wkts)")
                urgency = "MEDIUM" if urgency != "HIGH" else "HIGH"

        # 3. Run rate collapse (chasing)
        if required_rr > 0 and run_rate > 0:
            rr_gap = required_rr - run_rate
            if rr_gap > 3.0:
                triggers.append(
                    f"RR collapse: need {required_rr:.1f}, scoring {run_rate:.1f} "
                    f"(gap: {rr_gap:.1f})"
                )
                urgency = "CRITICAL" if rr_gap > 5.0 else "HIGH"

        # 4. Win probability threshold
        if win_probability < 0.25:
            triggers.append(f"Win probability critical: {win_probability*100:.1f}%")
            urgency = "CRITICAL"

        # 5. Late-game collapse (over 15, wickets > 6)
        if current_over >= 15 and wickets_fallen >= 7:
            triggers.append(f"Late collapse: {wickets_fallen} wkts in over {current_over:.1f}")
            urgency = "CRITICAL"

        should_trigger = len(triggers) > 0

        # Calculate hedge
        hedge_amount, hedge_profit = self.calculate_hedge(
            stake, entry_odds, current_team_odds
        ) if should_trigger else (0.0, 0.0)

        # Calculate loss reduction
        original_loss = -stake  # worst case without hedge
        loss_with_hedge = -stake + hedge_profit if hedge_profit > 0 else original_loss
        loss_reduction = abs(loss_with_hedge - original_loss) if hedge_profit > 0 else 0

        return LossCutResult(
            should_trigger=should_trigger,
            hedge_amount=hedge_amount,
            hedge_profit=hedge_profit,
            loss_reduction=loss_reduction,
            trigger_reason=" | ".join(triggers) if triggers else "No trigger",
            urgency=urgency
        )

    def get_optimal_exit_point(
        self,
        entry_odds: float,
        current_odds: float,
        win_probability: float,
        over_number: float
    ) -> dict:
        """
        Recommend optimal exit strategy based on position.
        """
        breakeven_odds = entry_odds  # approximate breakeven
        value_odds = 1 / win_probability if win_probability > 0 else current_odds
        
        position = "AHEAD" if current_odds > entry_odds else "BEHIND"
        implied_prob = 1 / current_odds if current_odds > 0 else 0

        recommendation = "HOLD"
        if implied_prob < win_probability * 0.8:
            recommendation = "CASH_OUT"
        elif implied_prob > win_probability * 1.2 and over_number > 15:
            recommendation = "PARTIAL_CASH_OUT"

        return {
            "position": position,
            "value_odds": round(value_odds, 2),
            "breakeven_odds": round(breakeven_odds, 2),
            "implied_prob": round(implied_prob * 100, 1),
            "model_prob": round(win_probability * 100, 1),
            "recommendation": recommendation,
            "edge": round((win_probability - implied_prob) * 100, 2)
        }
