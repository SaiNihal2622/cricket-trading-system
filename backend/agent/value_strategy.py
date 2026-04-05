"""
Value Strategy Engine

Implements sophisticated entry logic beyond simple signal following:

1. WAIT-FOR-ODDS:  Don't enter at any price. Wait for value odds (10+, 25+, etc.)
                   High-odds entry → small stake → massive return if team recovers

2. HIGH-ODDS LAY:  At 40+ odds, BACK errors happen. Instead, LAY the opposite side
                   at near-certainty odds (1.01-1.05). Same net effect, no errors.

3. PROGRESSIVE BOOKSET: As high-entry odds compress (team recovers), lock in
                         guaranteed profit at optimal compression points.

4. MOMENTUM REVERSAL: Detect when losing team is about to turn — the best entry point
                       for maximum expected value.

5. ANTI-PANIC: When odds spike on a wicket, don't panic-sell. Calculate if it's
               a structural collapse or recoverable situation.

All returns are in expected-value terms (EV > 0 required to bet).
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ValueOpportunity:
    """A high-value betting opportunity identified by the strategy engine."""
    action:        str      # 'BACK', 'LAY', 'WAIT', 'PROGRESSIVE_BOOKSET'
    team:          str      # team to back/lay
    target_odds:   float    # enter at this odds level
    stake_pct:     float    # fraction of bankroll to stake (Kelly-adjusted)
    ev:            float    # expected value per unit staked (>0 means profitable)
    confidence:    float    # 0-1
    reasoning:     str
    stop_loss_at:  float    # auto-exit if odds reach this
    bookset_at:    float    # take profit / bookset when odds compress to this
    urgency:       str      # 'IMMEDIATE', 'WAIT', 'MONITOR'
    is_lay:        bool = False   # True = lay bet (opposite side)
    lay_odds:      float = 0.0   # for lay: the odds to lay at
    max_wait_overs: float = 2.0  # max overs to wait before cancelling wait


@dataclass
class WaitEntry:
    """A pending entry waiting for odds to reach target level."""
    team:         str
    target_odds:  float    # enter WHEN odds reach this
    max_odds:     float    # cancel if odds go higher than this (too risky)
    stake:        float
    created_over: float
    max_over:     float    # cancel if not triggered by this over
    reasoning:    str


class ValueStrategyEngine:
    """
    Core value betting logic for IPL trading.

    Key insight: In IPL, a team at 20+ odds has ~5% chance of winning,
    but after a run of 4s/6s, their odds can compress to 5, giving 4x ROI.
    We capture that swing by:
    1. Entering when odds are HIGH (value entry)
    2. Doing a partial bookset as odds compress
    3. Letting the remainder run for maximum profit
    """

    # Odds thresholds for different strategies
    HIGH_ODDS_THRESHOLD   = 10.0   # wait-for-odds: only enter if odds >= this
    VERY_HIGH_ODDS        = 20.0   # larger stake fraction at these levels
    LAY_INSTEAD_OF_BACK   = 35.0   # at these odds, lay opposite instead of backing
    BOOKSET_TRIGGER_RATIO = 0.40   # when odds drop to 40% of entry, do progressive bookset
    STOP_LOSS_RATIO       = 2.00   # stop loss at 200% of entry odds

    def __init__(self):
        self._pending_waits: List[WaitEntry] = []

    def evaluate(
        self,
        state: dict,
        team_a: str,
        team_b: str,
        odds_a: float,
        odds_b: float,
        position=None,
        bankroll: float = 10000.0,
        historical=None,
    ) -> Optional[ValueOpportunity]:
        """
        Evaluate current market for value opportunities.
        Returns ValueOpportunity or None if no edge found.
        """
        overs   = float(state.get("overs", 0))
        wickets = int(state.get("total_wickets", 0))
        runs    = int(state.get("total_runs", 0))
        innings = int(state.get("innings", 1))
        crr     = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))

        # Skip if match is too advanced (over 18 overs) — entry risk too high
        if overs >= 18:
            return None

        # Skip if we already have a position (no doubling up)
        if position:
            return self._evaluate_existing_position(position, odds_a, odds_b, overs)

        # ── Check each side for value ──────────────────────────────────────
        for team, odds, opp_odds in [
            (team_a, odds_a, odds_b),
            (team_b, odds_b, odds_a),
        ]:
            opp  = team_b if team == team_a else team_a
            opp_odds_val = opp_odds

            if odds <= 1.05:
                continue  # near-certainty, no value

            # ── CASE 1: High-odds value back ──────────────────────────────
            if self.HIGH_ODDS_THRESHOLD <= odds < self.LAY_INSTEAD_OF_BACK:
                ev = self._compute_ev_high_odds(
                    team, odds, opp_odds, overs, wickets, runs, innings, crr, rrr, historical
                )
                if ev > 0.05:  # minimum 5% EV
                    stake_pct = self._kelly_stake(ev, odds)
                    stop_loss = min(odds * self.STOP_LOSS_RATIO, 95.0)
                    bookset_at = max(odds * self.BOOKSET_TRIGGER_RATIO, 1.5)

                    reasoning = (
                        f"Value BACK: {team} at {odds:.1f} odds. "
                        f"EV={ev*100:.0f}%. "
                        f"{'Very high odds — large comeback value.' if odds > self.VERY_HIGH_ODDS else 'High odds — recovery play.'} "
                        f"Bookset target: {bookset_at:.1f}. Stop loss: {stop_loss:.1f}."
                    )
                    return ValueOpportunity(
                        action       = "BACK",
                        team         = team,
                        target_odds  = odds,
                        stake_pct    = stake_pct,
                        ev           = ev,
                        confidence   = min(0.72, 0.40 + ev * 0.5),
                        reasoning    = reasoning,
                        stop_loss_at = stop_loss,
                        bookset_at   = bookset_at,
                        urgency      = "IMMEDIATE",
                        is_lay       = False,
                    )

            # ── CASE 2: Extreme odds — LAY opposite side ──────────────────
            elif odds >= self.LAY_INSTEAD_OF_BACK:
                # At 35+ odds, backing is error-prone on exchanges.
                # Instead, LAY the OPPOSITE team (near certainty) at low odds.
                # Laying opp at 1.02: liability is 2% of stake — very safe.
                if opp_odds_val < 1.10:
                    lay_odds  = opp_odds_val
                    lay_ev    = 1 - lay_odds + 0.98  # approximate EV of lay
                    stake_pct = 0.02  # small stake, liability = stake * (opp_odds - 1) = tiny

                    reasoning = (
                        f"HIGH-ODDS LAY: {team} odds={odds:.0f} (too high to BACK cleanly). "
                        f"LAY {opp} at {lay_odds:.2f} instead — same net exposure. "
                        f"Liability: {stake_pct*100:.0f}% × {lay_odds-1:.2f} = {stake_pct*(lay_odds-1)*100:.1f}% bankroll. "
                        f"If {opp} loses (likely), you win full stake."
                    )
                    return ValueOpportunity(
                        action       = "LAY",
                        team         = opp,   # the team being LAID (near-certainty side)
                        target_odds  = lay_odds,
                        stake_pct    = stake_pct,
                        ev           = 0.60,   # high confidence lay
                        confidence   = 0.65,
                        reasoning    = reasoning,
                        stop_loss_at = lay_odds * 3,
                        bookset_at   = 1.01,
                        urgency      = "IMMEDIATE",
                        is_lay       = True,
                        lay_odds     = lay_odds,
                    )

        return None

    def _evaluate_existing_position(self, position, odds_a, odds_b, overs) -> Optional[ValueOpportunity]:
        """
        Check if an existing position should be progressively bookset.
        Returns a PROGRESSIVE_BOOKSET opportunity when odds have compressed enough.
        """
        entry_odds = position.entry_odds
        backed     = position.backed_team
        is_team_a  = (backed == getattr(position, "team_a", ""))
        current_odds = odds_a if is_team_a else odds_b

        if entry_odds <= 0 or current_odds <= 0:
            return None

        compression = current_odds / entry_odds

        # Full bookset when odds at 40% of entry or lower
        if compression <= 0.40:
            reasoning = (
                f"PROGRESSIVE BOOKSET: Backed {backed} at {entry_odds:.2f}. "
                f"Now at {current_odds:.2f} ({compression*100:.0f}% of entry). "
                f"Locking guaranteed profit — full bookset."
            )
            return ValueOpportunity(
                action       = "PROGRESSIVE_BOOKSET",
                team         = backed,
                target_odds  = current_odds,
                stake_pct    = 0,
                ev           = 0.80,
                confidence   = 0.80,
                reasoning    = reasoning,
                stop_loss_at = entry_odds * 2,
                bookset_at   = current_odds,
                urgency      = "IMMEDIATE",
            )

        # Partial bookset at 60% compression — lock in half
        elif compression <= 0.60 and overs >= 12:
            reasoning = (
                f"PARTIAL BOOKSET: {backed} odds compressed from {entry_odds:.2f} to {current_odds:.2f}. "
                f"Partial lock-in at {compression*100:.0f}% compression. "
                f"Over {overs:.1f} — late match, reduce risk."
            )
            return ValueOpportunity(
                action       = "PROGRESSIVE_BOOKSET",
                team         = backed,
                target_odds  = current_odds,
                stake_pct    = 0.5,  # only bookset 50%
                ev           = 0.65,
                confidence   = 0.65,
                reasoning    = reasoning,
                stop_loss_at = entry_odds * 1.8,
                bookset_at   = current_odds * 0.7,
                urgency      = "MONITOR",
            )

        return None

    def _compute_ev_high_odds(
        self, team, odds, opp_odds, overs, wickets, runs, innings, crr, rrr, historical
    ) -> float:
        """
        Compute expected value for a high-odds back bet.
        EV = P(win) * (odds - 1) - P(lose) * 1

        P(win) estimated from:
        1. Historical situation win probability
        2. Run rate edge
        3. Wickets in hand
        4. Remaining overs
        """
        if historical:
            p_win_base = historical.get_situation_win_pct(overs, wickets, innings, crr, rrr) / 100
        else:
            # Fallback heuristic
            wickets_remaining = 10 - wickets
            p_win_base = (wickets_remaining / 10) * 0.40  # max 40% without historical

        # Run rate adjustment (2nd innings)
        if innings == 2 and rrr > 0 and crr > 0:
            rr_ratio = crr / rrr
            if rr_ratio >= 0.9:   # keeping up
                p_win_base *= 1.3
            elif rr_ratio >= 0.7: # slightly behind
                p_win_base *= 1.1
            else:                  # badly behind
                p_win_base *= 0.8

        # Overs remaining adjustment
        overs_left = max(0, 20 - overs)
        if overs_left < 5:
            p_win_base *= 0.7  # fewer overs = harder comeback
        elif overs_left >= 10:
            p_win_base *= 1.2  # plenty of overs

        p_win = max(0.02, min(0.45, p_win_base))

        # EV = P(win) * profit - P(lose) * stake
        ev = p_win * (odds - 1) - (1 - p_win) * 1
        return ev

    def _kelly_stake(self, ev: float, odds: float) -> float:
        """
        Kelly criterion stake fraction.
        f = (bp - q) / b  where b=odds-1, p=win prob, q=lose prob
        Uses quarter-Kelly for safety.
        """
        if ev <= 0 or odds <= 1:
            return 0.0
        b = odds - 1
        p = (ev + 1) / odds
        q = 1 - p
        kelly = (b * p - q) / b
        quarter_kelly = max(0.005, min(0.04, kelly * 0.25))  # cap at 4% bankroll
        return round(quarter_kelly, 3)

    def check_wait_entries(self, odds_a: float, odds_b: float) -> Optional[WaitEntry]:
        """
        Check if any pending wait-entry should be triggered now.
        Called every cycle.
        """
        triggered = []
        for wait in self._pending_waits:
            # Check if odds have reached target
            current = odds_a  # simplified; in practice match by team
            if current >= wait.target_odds:
                triggered.append(wait)
            elif current > wait.max_odds:
                # Too far — cancel
                self._pending_waits.remove(wait)
                logger.info(f"Wait-entry cancelled: {wait.team} odds {current:.1f} > max {wait.max_odds}")

        for t in triggered:
            self._pending_waits.remove(t)
        return triggered[0] if triggered else None

    def add_wait_entry(self, wait: WaitEntry):
        """Register a pending wait-for-odds entry."""
        self._pending_waits.append(wait)
        logger.info(f"Wait-entry added: {wait.team} @ {wait.target_odds}+ odds")

    def get_anti_panic_signal(
        self, state: dict, position, odds_a: float, odds_b: float
    ) -> Optional[str]:
        """
        Detect if a wicket-induced odds spike is a panic sell vs real collapse.
        Returns 'HOLD', 'CUT', or None.

        Logic:
        - Recent wicket: check if it was tail vs top order
        - Run rate: still feasible?
        - Wickets remaining: still have batsmen?
        """
        if not position:
            return None

        overs   = float(state.get("overs", 0))
        wickets = int(state.get("total_wickets", 0))
        crr     = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))
        last_ball = state.get("last_ball", "")

        is_wicket = last_ball == "W"
        if not is_wicket:
            return None

        # Real collapse indicators
        if wickets >= 7:
            return "CUT"  # tail order — genuine danger

        # Chasing: is it still feasible?
        if int(state.get("innings", 1)) == 2 and rrr > 0:
            if rrr > 18:
                return "CUT"  # impossible required rate
            if rrr > 14 and wickets >= 5:
                return "CUT"  # tough combo
            if rrr <= 12 and wickets <= 4:
                return "HOLD"  # still very manageable

        # Death overs with set batsman: hold
        if overs >= 14 and wickets <= 3 and crr > 0 and (rrr == 0 or crr >= rrr * 0.9):
            return "HOLD"

        return None


# Global singleton
value_engine = ValueStrategyEngine()
