"""
Value Strategy Engine

Strategy: Enter at ANY odds where we have positive expected value and
sufficient confidence. No minimum-odds gate. High odds are a bonus (more
upside) but we'll also take 1.5x, 2x, 3x opportunities when the model
has strong conviction.

Bet sizing scales with confidence and available EV:
- Low odds (1.1–2.0):  small stake, tight bookset — scalp plays
- Mid odds (2–10):     standard Kelly — momentum plays
- High odds (10–35):   larger Kelly — recovery plays
- Very high (35+):     LAY opposite side — same net, avoids exchange errors

Progressive Bookset:
- 40% compression → full bookset (lock guaranteed profit)
- 60% compression + over ≥12 → partial bookset (lock half, let rest run)

Anti-Panic: Wicket fell? Check collapse vs recoverable, hold if manageable.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ValueOpportunity:
    """A value betting opportunity at any odds level."""
    action:        str      # 'BACK', 'LAY', 'PROGRESSIVE_BOOKSET'
    team:          str
    target_odds:   float
    stake_pct:     float    # fraction of bankroll (Kelly-adjusted)
    ev:            float    # expected value per unit staked (>0 = profitable)
    confidence:    float    # 0–1
    reasoning:     str
    stop_loss_at:  float
    bookset_at:    float
    urgency:       str      # 'IMMEDIATE', 'WAIT', 'MONITOR'
    is_lay:        bool = False
    lay_odds:      float = 0.0
    odds_tier:     str = "mid"  # 'scalp' | 'mid' | 'high' | 'very_high'


class ValueStrategyEngine:
    """
    Core value betting logic — odds-agnostic entry.

    EV = P(win) × (odds − 1) − P(lose) × 1

    We enter whenever EV > threshold (varies by confidence tier).
    Stake size is Kelly-adjusted and capped per tier.
    """

    # Odds tiers — define behaviour, not gates
    SCALP_MAX    = 2.5    # quick-flip plays
    MID_MAX      = 10.0   # standard momentum plays
    HIGH_MAX     = 35.0   # recovery plays (BACK)
    # >= HIGH_MAX → LAY opposite side

    # EV thresholds per tier (lower odds → need stronger edge to justify)
    EV_THRESHOLD_SCALP  = 0.03   # 3% EV for scalp at low odds
    EV_THRESHOLD_MID    = 0.05   # 5% EV for mid odds
    EV_THRESHOLD_HIGH   = 0.04   # 4% EV for high odds (more upside)

    # Bookset triggers
    BOOKSET_FULL_RATIO    = 0.40  # odds compressed to 40% of entry → full bookset
    BOOKSET_PARTIAL_RATIO = 0.60  # odds at 60%, over≥12 → partial bookset
    STOP_LOSS_RATIO       = 2.00  # exit if odds rise to 200% of entry

    def __init__(self):
        self._pending_waits: List = []

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
        overs   = float(state.get("overs", 0))
        wickets = int(state.get("total_wickets", 0))
        runs    = int(state.get("total_runs", 0))
        innings = int(state.get("innings", 1))
        crr     = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))

        # Don't enter in last 2 overs — too late, high variance
        if overs >= 18:
            return None

        # If we have a position, check for bookset opportunity
        if position:
            return self._evaluate_existing_position(position, odds_a, odds_b, overs)

        best: Optional[ValueOpportunity] = None

        for team, odds, opp_odds in [
            (team_a, odds_a, odds_b),
            (team_b, odds_b, odds_a),
        ]:
            opp = team_b if team == team_a else team_a

            # Skip near-certainty (exchange minimum)
            if odds <= 1.05:
                continue

            # ── Very high odds (35+): LAY the near-certain side ──────────────
            if odds >= self.HIGH_MAX:
                if opp_odds < 1.10:
                    opp = opp
                    lay_odds = opp_odds
                    # EV of laying at 1.02: liability is tiny, win probability ~95%+
                    p_opp_wins = 1 - self._estimate_p_win(
                        team, odds, overs, wickets, innings, crr, rrr, historical
                    )
                    lay_ev = p_opp_wins * 1 - (1 - p_opp_wins) * (lay_odds - 1)
                    if lay_ev > 0.02:
                        stake_pct = 0.02  # tiny stake; liability = stake × (opp_odds−1) ≈ 2%
                        reasoning = (
                            f"HIGH-ODDS LAY: {team} at {odds:.0f} (exchange error-prone at 35+). "
                            f"LAY {opp} at {lay_odds:.2f} — same net exposure. "
                            f"P({opp} wins)={p_opp_wins*100:.0f}%. "
                            f"EV={lay_ev*100:.1f}%."
                        )
                        opp_opp = ValueOpportunity(
                            action="LAY", team=opp,
                            target_odds=lay_odds, stake_pct=stake_pct,
                            ev=lay_ev, confidence=min(0.85, p_opp_wins),
                            reasoning=reasoning,
                            stop_loss_at=lay_odds * 3, bookset_at=1.01,
                            urgency="IMMEDIATE", is_lay=True, lay_odds=lay_odds,
                            odds_tier="very_high",
                        )
                        if best is None or opp_opp.ev > best.ev:
                            best = opp_opp
                continue  # handled above

            # ── Standard BACK at any odds ────────────────────────────────────
            p_win = self._estimate_p_win(
                team, odds, overs, wickets, innings, crr, rrr, historical
            )
            ev = p_win * (odds - 1) - (1 - p_win) * 1

            # Determine tier and its EV threshold
            if odds < self.SCALP_MAX:
                tier = "scalp"
                ev_thresh = self.EV_THRESHOLD_SCALP
            elif odds < self.MID_MAX:
                tier = "mid"
                ev_thresh = self.EV_THRESHOLD_MID
            else:
                tier = "high"
                ev_thresh = self.EV_THRESHOLD_HIGH

            if ev < ev_thresh:
                continue  # not enough edge for this tier

            stake_pct = self._kelly_stake(ev, odds, tier)
            stop_loss = min(odds * self.STOP_LOSS_RATIO, 95.0)
            bookset_at = max(odds * self.BOOKSET_FULL_RATIO, 1.05)

            # Confidence: base on win prob and EV strength
            confidence = min(0.90, 0.35 + p_win * 0.5 + ev * 0.3)

            tier_labels = {
                "scalp": f"Scalp play at {odds:.2f} — tight entry, quick bookset.",
                "mid":   f"Momentum play at {odds:.2f} — standard entry.",
                "high":  f"Recovery play at {odds:.2f} — high upside if comeback.",
            }
            reasoning = (
                f"BACK {team} @ {odds:.2f} odds. "
                f"{tier_labels[tier]} "
                f"P(win)={p_win*100:.0f}%, EV={ev*100:.1f}%. "
                f"Bookset target: {bookset_at:.2f}. Stop loss: {stop_loss:.1f}. "
                f"Stake: {stake_pct*100:.1f}% bankroll."
            )

            opp_entry = ValueOpportunity(
                action="BACK", team=team,
                target_odds=odds, stake_pct=stake_pct,
                ev=ev, confidence=confidence,
                reasoning=reasoning,
                stop_loss_at=stop_loss, bookset_at=bookset_at,
                urgency="IMMEDIATE", is_lay=False,
                odds_tier=tier,
            )
            if best is None or opp_entry.ev > best.ev:
                best = opp_entry

        return best

    def _evaluate_existing_position(self, position, odds_a, odds_b, overs) -> Optional[ValueOpportunity]:
        entry_odds = position.entry_odds
        backed     = position.backed_team
        is_team_a  = (backed == getattr(position, "team_a", ""))
        current_odds = odds_a if is_team_a else odds_b

        if entry_odds <= 0 or current_odds <= 0:
            return None

        compression = current_odds / entry_odds

        if compression <= self.BOOKSET_FULL_RATIO:
            reasoning = (
                f"PROGRESSIVE BOOKSET: Backed {backed} at {entry_odds:.2f}. "
                f"Now {current_odds:.2f} ({compression*100:.0f}% of entry). "
                f"Full bookset — locking guaranteed profit."
            )
            return ValueOpportunity(
                action="PROGRESSIVE_BOOKSET", team=backed,
                target_odds=current_odds, stake_pct=0,
                ev=0.80, confidence=0.80,
                reasoning=reasoning,
                stop_loss_at=entry_odds * 2, bookset_at=current_odds,
                urgency="IMMEDIATE",
            )

        if compression <= self.BOOKSET_PARTIAL_RATIO and overs >= 12:
            reasoning = (
                f"PARTIAL BOOKSET: {backed} compressed {entry_odds:.2f}→{current_odds:.2f} "
                f"({compression*100:.0f}%). Over {overs:.1f} — locking half profit."
            )
            return ValueOpportunity(
                action="PROGRESSIVE_BOOKSET", team=backed,
                target_odds=current_odds, stake_pct=0.5,
                ev=0.65, confidence=0.65,
                reasoning=reasoning,
                stop_loss_at=entry_odds * 1.8, bookset_at=current_odds * 0.7,
                urgency="MONITOR",
            )

        return None

    def _estimate_p_win(
        self, team, odds, overs, wickets, innings, crr, rrr, historical
    ) -> float:
        """Estimate win probability from historical data or heuristics."""
        if historical:
            p_win = historical.get_situation_win_pct(overs, wickets, innings, crr, rrr) / 100
        else:
            # Implied probability from odds (adjusted for bookmaker margin)
            implied = 1 / odds
            # Heuristic: wickets remaining is a strong signal
            wickets_remaining = 10 - wickets
            situation_factor = (wickets_remaining / 10) * 0.8
            p_win = max(implied * 0.85, situation_factor * 0.5)

        # Run rate adjustment in 2nd innings
        if innings == 2 and rrr > 0 and crr > 0:
            rr_ratio = crr / rrr
            if rr_ratio >= 1.0:
                p_win = min(p_win * 1.3, 0.85)
            elif rr_ratio >= 0.85:
                p_win *= 1.1
            elif rr_ratio < 0.6:
                p_win *= 0.75

        # Overs remaining
        overs_left = max(0, 20 - overs)
        if overs_left < 3:
            p_win *= 0.6
        elif overs_left >= 12:
            p_win *= 1.15

        return max(0.02, min(0.90, p_win))

    def _kelly_stake(self, ev: float, odds: float, tier: str) -> float:
        """
        Kelly criterion stake, scaled by tier.
        Scalp: cap 2% (low odds, tight margin)
        Mid:   cap 4%
        High:  cap 6% (high upside justifies larger bet)
        """
        if ev <= 0 or odds <= 1:
            return 0.0
        b = odds - 1
        p = (ev + 1) / odds
        q = 1 - p
        kelly = (b * p - q) / b if b > 0 else 0

        caps = {"scalp": (0.005, 0.02), "mid": (0.005, 0.04), "high": (0.005, 0.06)}
        lo, hi = caps.get(tier, (0.005, 0.04))
        return round(max(lo, min(hi, kelly * 0.25)), 3)  # quarter-Kelly

    def get_anti_panic_signal(self, state: dict, position, odds_a: float, odds_b: float) -> Optional[str]:
        """Returns 'HOLD', 'CUT', or None after a wicket."""
        if not position:
            return None

        last_ball = state.get("last_ball", "")
        if last_ball != "W":
            return None

        overs   = float(state.get("overs", 0))
        wickets = int(state.get("total_wickets", 0))
        crr     = float(state.get("run_rate", 0))
        rrr     = float(state.get("required_run_rate", 0))

        if wickets >= 7:
            return "CUT"  # tail order

        if int(state.get("innings", 1)) == 2 and rrr > 0:
            if rrr > 18:
                return "CUT"
            if rrr > 14 and wickets >= 5:
                return "CUT"
            if rrr <= 12 and wickets <= 4:
                return "HOLD"

        if overs >= 14 and wickets <= 3 and crr > 0 and (rrr == 0 or crr >= rrr * 0.9):
            return "HOLD"

        return None


# Global singleton
value_engine = ValueStrategyEngine()
