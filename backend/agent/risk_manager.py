"""
Risk Manager — Bankroll management, exposure limits, circuit breakers.

Controls:
- Stake sizing (Kelly criterion / fixed fraction)
- Max exposure per match and total
- Daily loss limits
- Consecutive loss circuit breaker
- Drawdown protection
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskEvent:
    """A recorded risk event (trigger, override, etc.)"""
    event_type: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict = field(default_factory=dict)


class RiskManager:
    """
    Enforces all risk limits before any trade execution.
    
    Must be consulted BEFORE every trade. Returns approval or rejection.
    """

    def __init__(
        self,
        initial_bankroll: float = 1200.0,
        max_stake_per_trade: float = 1200.0,
        max_exposure: float = 1200.0,
        max_daily_loss: float = 1200.0,
        max_consecutive_losses: int = 5,
        max_drawdown_pct: float = 100.0, # allow full budget draw
        kelly_fraction: float = 0.50, 
    ):
        self.daily_profit_target = 3000.0
        self.initial_bankroll = initial_bankroll
        self.current_bankroll = initial_bankroll
        self.max_stake_per_trade = max_stake_per_trade
        self.max_exposure = max_exposure
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_drawdown_pct = max_drawdown_pct
        self.kelly_fraction = kelly_fraction

        # State
        self.peak_bankroll = initial_bankroll
        self.daily_pnl = 0.0
        self.daily_reset_date = datetime.now(timezone.utc).date()
        self.consecutive_losses = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        self._events: List[RiskEvent] = []
        self._trade_history: List[dict] = []

    # ── Pre-Trade Checks ────────────────────────────────────────────────────

    def approve_trade(
        self,
        proposed_stake: float,
        current_exposure: float,
        win_probability: float,
        confidence: float,
        odds: float,
    ) -> dict:
        """
        Check all risk limits before allowing a trade.
        
        Returns:
            {
                "approved": bool,
                "adjusted_stake": float,  # may be reduced
                "rejections": [str],      # reasons if rejected
                "warnings": [str],
            }
        """
        self._check_daily_reset()

        rejections = []
        warnings = []
        adjusted_stake = proposed_stake

        # 1. Circuit breaker
        if self.circuit_breaker_active:
            rejections.append(f"Circuit breaker active: {self.circuit_breaker_reason}")
            return self._result(False, 0, rejections, warnings)

        # 2. Bankroll check
        if self.current_bankroll <= 0:
            rejections.append("Bankroll depleted")
            return self._result(False, 0, rejections, warnings)

        # 3. Max stake limit
        if adjusted_stake > self.max_stake_per_trade:
            adjusted_stake = self.max_stake_per_trade
            warnings.append(f"Stake capped at max ₹{self.max_stake_per_trade}")

        # 4. Can't stake more than bankroll
        if adjusted_stake > self.current_bankroll:
            adjusted_stake = self.current_bankroll * 0.5  # max half of remaining
            warnings.append(f"Stake reduced to ₹{adjusted_stake:.0f} (50% of remaining bankroll)")

        # 5. Exposure limit
        if current_exposure + adjusted_stake > self.max_exposure:
            max_allowed = max(0, self.max_exposure - current_exposure)
            if max_allowed <= 0:
                rejections.append(f"Max exposure reached (₹{current_exposure:.0f}/₹{self.max_exposure:.0f})")
                return self._result(False, 0, rejections, warnings)
            adjusted_stake = min(adjusted_stake, max_allowed)
            warnings.append(f"Stake limited by exposure cap: ₹{adjusted_stake:.0f}")

        # 6. Daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            rejections.append(f"Daily loss limit hit: ₹{self.daily_pnl:.0f}")
            self._trigger_circuit_breaker("Daily loss limit exceeded")
            return self._result(False, 0, rejections, warnings)

        # 6.5 Daily profit target
        if hasattr(self, 'daily_profit_target') and self.daily_pnl >= self.daily_profit_target:
            rejections.append(f"Daily profit target hit: ₹{self.daily_pnl:.0f}!")
            self._trigger_circuit_breaker("Victory! Daily profit target achieved.")
            return self._result(False, 0, rejections, warnings)

        # 7. Drawdown protection
        drawdown_pct = ((self.peak_bankroll - self.current_bankroll) / self.peak_bankroll) * 100
        if drawdown_pct >= self.max_drawdown_pct:
            rejections.append(f"Max drawdown {drawdown_pct:.1f}% >= {self.max_drawdown_pct}%")
            self._trigger_circuit_breaker(f"Drawdown protection: {drawdown_pct:.1f}%")
            return self._result(False, 0, rejections, warnings)

        # 8. Minimum confidence check
        if confidence < 0.5:
            rejections.append(f"Confidence too low: {confidence:.0%}")
            return self._result(False, 0, rejections, warnings)

        # 9. Kelly criterion sizing or Fixed % for small accounts
        if self.current_bankroll < 2000:
            # Small account aggressive mode (20% fixed stake per quality signal)
            sizing_stake = self.current_bankroll * 0.20
        else:
            sizing_stake = self._kelly_size(win_probability, odds)

        if sizing_stake < adjusted_stake:
            adjusted_stake = sizing_stake
            warnings.append(f"Adjusted for bankroll to ₹{adjusted_stake:.0f}")

        # 10. Minimum viable stake — increased for visibility
        if adjusted_stake < 100:
            if self.current_bankroll >= 150:
                adjusted_stake = 100.0
                warnings.append("Stake boosted to ₹100 min")
            else:
                rejections.append(f"Stake too small: ₹{adjusted_stake:.0f}")
                return self._result(False, 0, rejections, warnings)

        return self._result(True, round(adjusted_stake, 2), rejections, warnings)

    def _result(self, approved, stake, rejections, warnings):
        return {
            "approved": approved,
            "adjusted_stake": stake,
            "rejections": rejections,
            "warnings": warnings,
        }

    # ── Kelly Criterion ─────────────────────────────────────────────────────

    def _kelly_size(self, win_prob: float, odds: float) -> float:
        """
        Quarter-Kelly stake sizing.
        
        Kelly formula: f* = (bp - q) / b
        where b = odds - 1, p = win_prob, q = 1 - p
        """
        b = odds - 1
        if b <= 0:
            return 0
        p = max(0.01, min(0.99, win_prob))
        q = 1 - p
        kelly_pct = (b * p - q) / b
        kelly_pct = max(0, kelly_pct) * self.kelly_fraction  # quarter-Kelly

        return round(kelly_pct * self.current_bankroll, 2)

    # ── Post-Trade Updates ──────────────────────────────────────────────────

    def record_trade_result(self, pnl: float, trade_info: dict = None):
        """Update bankroll and risk state after a trade completes"""
        self.current_bankroll += pnl
        self.daily_pnl += pnl
        self.peak_bankroll = max(self.peak_bankroll, self.current_bankroll)

        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self._trigger_circuit_breaker(
                    f"{self.consecutive_losses} consecutive losses"
                )
        else:
            self.consecutive_losses = 0

        self._trade_history.append({
            "pnl": pnl,
            "bankroll_after": self.current_bankroll,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(trade_info or {}),
        })

        logger.info(
            f"💰 Trade result: ₹{pnl:+.2f} | Bankroll: ₹{self.current_bankroll:.2f} | "
            f"Daily: ₹{self.daily_pnl:+.2f} | Streak: {self.consecutive_losses}"
        )

    # ── Circuit Breaker ─────────────────────────────────────────────────────

    def _trigger_circuit_breaker(self, reason: str):
        """Stop all trading"""
        self.circuit_breaker_active = True
        self.circuit_breaker_reason = reason
        self._events.append(RiskEvent("CIRCUIT_BREAKER", reason))
        logger.warning(f"🚨 CIRCUIT BREAKER: {reason}")

    def reset_circuit_breaker(self):
        """Manually reset circuit breaker"""
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        self.consecutive_losses = 0
        self._events.append(RiskEvent("CIRCUIT_RESET", "Manual reset"))
        logger.info("✅ Circuit breaker reset")

    def _check_daily_reset(self):
        """Reset daily counters at midnight UTC"""
        today = datetime.now(timezone.utc).date()
        if today > self.daily_reset_date:
            self.daily_pnl = 0.0
            self.daily_reset_date = today
            # Don't auto-reset circuit breaker — require manual reset

    # ── Status ──────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        drawdown = self.peak_bankroll - self.current_bankroll
        drawdown_pct = (drawdown / self.peak_bankroll * 100) if self.peak_bankroll > 0 else 0

        return {
            "bankroll": round(self.current_bankroll, 2),
            "initial_bankroll": self.initial_bankroll,
            "peak_bankroll": round(self.peak_bankroll, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_pnl": round(self.current_bankroll - self.initial_bankroll, 2),
            "drawdown": round(drawdown, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "consecutive_losses": self.consecutive_losses,
            "circuit_breaker_active": self.circuit_breaker_active,
            "circuit_breaker_reason": self.circuit_breaker_reason,
            "total_trades": len(self._trade_history),
            "winning_trades": sum(1 for t in self._trade_history if t["pnl"] > 0),
            "losing_trades": sum(1 for t in self._trade_history if t["pnl"] < 0),
            "max_stake_per_trade": self.max_stake_per_trade,
            "max_exposure": self.max_exposure,
            "max_daily_loss": self.max_daily_loss,
        }

    def get_recent_events(self, n: int = 20) -> List[dict]:
        return [
            {"type": e.event_type, "message": e.message, "timestamp": e.timestamp}
            for e in self._events[-n:]
        ]
