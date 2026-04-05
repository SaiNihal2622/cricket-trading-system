"""
Bookset Engine
Calculates stakes for equal profit on both outcomes (dutch book / bookset).

Formula: stake_A × odds_A = stake_B × odds_B
Ensures guaranteed profit regardless of match outcome.
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BooksetResult:
    is_profitable: bool
    stake_a: float
    stake_b: float
    odds_a: float
    odds_b: float
    guaranteed_profit: float
    profit_percentage: float
    total_investment: float
    implied_prob_a: float
    implied_prob_b: float
    overround: float  # >1 = bookmaker margin, <1 = arb opportunity
    explanation: str


class BooksetEngine:
    """
    Bookset / Dutch Book Calculator.
    
    Given two opposing outcomes with their odds, calculate stakes
    to guarantee equal profit on both outcomes.
    
    Bookset condition: stake_A × odds_A = stake_B × odds_B
    
    Arbitrage exists when: (1/odds_A) + (1/odds_B) < 1
    """

    def __init__(self, min_profit_threshold: float = 0.02):
        self.min_profit_threshold = min_profit_threshold  # 2% minimum

    def calculate(
        self,
        odds_a: float,
        odds_b: float,
        total_stake: float = 1000.0,
        target_profit_a: Optional[float] = None
    ) -> BooksetResult:
        """
        Calculate bookset stakes for given odds.
        
        Args:
            odds_a: Decimal odds for Team A winning
            odds_b: Decimal odds for Team B winning  
            total_stake: Total capital to deploy
            target_profit_a: If set, stake_a to achieve this profit
        """
        if odds_a <= 1 or odds_b <= 1:
            return self._invalid_result(odds_a, odds_b, "Odds must be > 1")

        # Implied probabilities
        implied_a = 1 / odds_a
        implied_b = 1 / odds_b
        overround = implied_a + implied_b

        # For equal profit on both outcomes:
        # stake_a * (odds_a - 1) = stake_b * (odds_b - 1)  [equal net profit]
        # stake_a + stake_b = total_stake
        # Solving simultaneously:
        # stake_a = total_stake * (odds_b - 1) / ((odds_a - 1) + (odds_b - 1))
        # OR for equal RETURN (not profit):
        # stake_a = total_stake / odds_a / (1/odds_a + 1/odds_b)

        # Equal return method (classic bookset)
        if target_profit_a:
            stake_a = target_profit_a
            # stake_A × odds_A = stake_B × odds_B
            # → stake_B = (stake_A × odds_A) / odds_B
            stake_b = (stake_a * odds_a) / odds_b
            total = stake_a + stake_b
        else:
            # Distribute total_stake proportionally
            stake_a = (total_stake * implied_a) / overround
            stake_b = (total_stake * implied_b) / overround

        stake_a = round(stake_a, 2)
        stake_b = round(stake_b, 2)

        # Calculate returns
        return_a = stake_a * odds_a
        return_b = stake_b * odds_b
        total_investment = stake_a + stake_b

        # Profit (guaranteed outcome: min of both returns - total staked)
        # Both returns should be equal in perfect bookset
        avg_return = (return_a + return_b) / 2
        profit = avg_return - total_investment
        profit_pct = (profit / total_investment) * 100

        is_profitable = overround < 1 and profit > (self.min_profit_threshold * total_investment)

        # Explanation
        if overround < 1:
            explanation = (
                f"ARB OPPORTUNITY: Overround {overround:.4f} < 1. "
                f"Guaranteed profit: {profit:.2f} ({profit_pct:.2f}%)"
            )
        elif overround == 1:
            explanation = "Fair book: No profit but no loss guaranteed."
        else:
            explanation = (
                f"No arb: Overround {overround:.4f}. "
                f"Using bookset for risk management."
            )

        return BooksetResult(
            is_profitable=is_profitable,
            stake_a=stake_a,
            stake_b=stake_b,
            odds_a=odds_a,
            odds_b=odds_b,
            guaranteed_profit=round(profit, 2),
            profit_percentage=round(profit_pct, 2),
            total_investment=round(total_investment, 2),
            implied_prob_a=round(implied_a * 100, 2),
            implied_prob_b=round(implied_b * 100, 2),
            overround=round(overround, 4),
            explanation=explanation
        )

    def partial_bookset(
        self,
        original_stake: float,
        original_odds: float,
        current_odds_a: float,
        current_odds_b: float,
        partial_pct: float = 0.5
    ) -> dict:
        """
        Calculate partial bookset (hedge only a % of position).
        Useful for locking in partial profit while keeping exposure.
        """
        hedge_stake = original_stake * partial_pct
        result = self.calculate(current_odds_a, current_odds_b, total_stake=hedge_stake)

        guaranteed = result.guaranteed_profit
        remaining_exposure = original_stake * (1 - partial_pct)

        return {
            "hedge_stake": hedge_stake,
            "hedge_profit": guaranteed,
            "remaining_stake": remaining_exposure,
            "stake_b": result.stake_b,
            "total_locked_profit": guaranteed,
            "max_upside": (original_stake * original_odds) - original_stake - hedge_stake,
            "max_downside": -remaining_exposure + guaranteed,
            "explanation": f"Partial {partial_pct*100:.0f}% bookset"
        }

    def find_optimal_bookset_moment(
        self,
        odds_history: list[dict],
        entry_odds: float,
        stake: float
    ) -> dict:
        """
        Scan odds history to identify when bookset would have been optimal.
        Useful for backtesting and real-time monitoring.
        """
        best = {"profit": -float("inf"), "timestamp": None, "odds_snapshot": None}

        for snap in odds_history:
            oa = snap.get("team_a_odds", 0)
            ob = snap.get("team_b_odds", 0)
            if oa <= 1 or ob <= 1:
                continue
            result = self.calculate(oa, ob, stake)
            if result.guaranteed_profit > best["profit"]:
                best = {
                    "profit": result.guaranteed_profit,
                    "timestamp": snap.get("timestamp"),
                    "odds_a": oa,
                    "odds_b": ob,
                    "result": result
                }

        return best

    def _invalid_result(self, odds_a, odds_b, reason) -> BooksetResult:
        return BooksetResult(
            is_profitable=False,
            stake_a=0, stake_b=0,
            odds_a=odds_a, odds_b=odds_b,
            guaranteed_profit=0, profit_percentage=0,
            total_investment=0,
            implied_prob_a=0, implied_prob_b=0,
            overround=0, explanation=reason
        )
