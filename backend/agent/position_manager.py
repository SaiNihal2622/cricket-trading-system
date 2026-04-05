"""
Position Manager — Tracks all open/closed trading positions.

Manages:
- Open position lifecycle (entry → loss_cut/bookset → close)
- Unrealized & realized P&L
- Portfolio-level exposure
- Position persistence
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    HEDGED = "HEDGED"      # loss cut executed, partially protected
    BOOKSET = "BOOKSET"    # both sides covered, guaranteed profit
    CLOSED = "CLOSED"      # fully exited
    EXPIRED = "EXPIRED"    # match ended


class PositionSide(str, Enum):
    BACK = "BACK"
    LAY = "LAY"


@dataclass
class Trade:
    """A single execution (entry, hedge, bookset leg)"""
    trade_id: str
    position_id: str
    side: PositionSide
    team: str
    odds: float
    stake: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trade_type: str = "ENTRY"  # ENTRY, HEDGE, BOOKSET_A, BOOKSET_B


@dataclass
class Position:
    """A complete trading position on a match"""
    position_id: str
    match_id: str
    team_a: str
    team_b: str
    backed_team: str
    entry_odds: float
    entry_stake: float
    status: PositionStatus = PositionStatus.OPEN
    current_odds_a: float = 0.0
    current_odds_b: float = 0.0
    hedge_stake: float = 0.0
    hedge_odds: float = 0.0
    bookset_stake_a: float = 0.0
    bookset_stake_b: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: Optional[str] = None
    close_reason: str = ""

    @property
    def total_exposure(self) -> float:
        """Total capital at risk"""
        if self.status == PositionStatus.BOOKSET:
            return 0.0  # fully hedged
        return self.entry_stake - self.hedge_stake

    @property
    def potential_profit(self) -> float:
        """Max profit if backed team wins"""
        return (self.entry_stake * self.entry_odds) - self.entry_stake

    def update_odds(self, odds_a: float, odds_b: float):
        """Update current odds and recalculate unrealized P&L"""
        self.current_odds_a = odds_a
        self.current_odds_b = odds_b

        if self.status == PositionStatus.OPEN:
            # unrealized = what we'd get if we hedged right now
            current = odds_a if self.backed_team == self.team_a else odds_b
            if current > 0:
                hedge_now = (self.entry_stake * self.entry_odds) / current
                self.unrealized_pnl = (self.entry_stake * self.entry_odds) - (self.entry_stake + hedge_now)

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "match_id": self.match_id,
            "team_a": self.team_a,
            "team_b": self.team_b,
            "backed_team": self.backed_team,
            "entry_odds": self.entry_odds,
            "entry_stake": self.entry_stake,
            "status": self.status.value,
            "current_odds_a": self.current_odds_a,
            "current_odds_b": self.current_odds_b,
            "hedge_stake": self.hedge_stake,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_exposure": round(self.total_exposure, 2),
            "potential_profit": round(self.potential_profit, 2),
            "trade_count": len(self.trades),
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
        }


class PositionManager:
    """
    Manages the full lifecycle of trading positions.
    
    Responsibilities:
    - Track open/closed positions per match
    - Calculate portfolio-level exposure and P&L
    - Persist position state
    """

    def __init__(self):
        self._positions: Dict[str, Position] = {}  # position_id → Position
        self._match_positions: Dict[str, str] = {}  # match_id → position_id (one per match)
        self._trade_counter = 0
        self._position_counter = 0
        self._total_realized_pnl = 0.0

    def _next_position_id(self) -> str:
        self._position_counter += 1
        return f"POS-{self._position_counter:04d}"

    def _next_trade_id(self) -> str:
        self._trade_counter += 1
        return f"TRD-{self._trade_counter:05d}"

    # ── Open Position ───────────────────────────────────────────────────────

    def open_position(
        self, match_id: str, team_a: str, team_b: str,
        backed_team: str, odds: float, stake: float,
    ) -> Position:
        """Open a new trading position on a match"""
        if match_id in self._match_positions:
            existing = self._positions[self._match_positions[match_id]]
            if existing.status == PositionStatus.OPEN:
                logger.warning(f"Already have open position on match {match_id}")
                return existing

        pos_id = self._next_position_id()
        position = Position(
            position_id=pos_id,
            match_id=match_id,
            team_a=team_a,
            team_b=team_b,
            backed_team=backed_team,
            entry_odds=odds,
            entry_stake=stake,
        )

        # Record entry trade
        trade = Trade(
            trade_id=self._next_trade_id(),
            position_id=pos_id,
            side=PositionSide.BACK,
            team=backed_team,
            odds=odds,
            stake=stake,
            trade_type="ENTRY",
        )
        position.trades.append(trade)
        self._positions[pos_id] = position
        self._match_positions[match_id] = pos_id

        logger.info(f"📈 OPENED {pos_id}: BACK {backed_team} @ {odds} ₹{stake}")
        return position

    # ── Loss Cut (Hedge) ────────────────────────────────────────────────────

    def execute_loss_cut(
        self, match_id: str, hedge_odds: float, hedge_stake: float,
    ) -> Optional[Position]:
        """Execute a hedge to protect capital"""
        pos = self.get_match_position(match_id)
        if not pos or pos.status != PositionStatus.OPEN:
            return None

        pos.hedge_odds = hedge_odds
        pos.hedge_stake = hedge_stake
        pos.status = PositionStatus.HEDGED

        # Calculate locked profit/loss
        guaranteed_return = pos.entry_stake * pos.entry_odds
        total_staked = pos.entry_stake + hedge_stake
        pos.realized_pnl = guaranteed_return - total_staked

        # Record hedge trade
        opposite_team = pos.team_b if pos.backed_team == pos.team_a else pos.team_a
        trade = Trade(
            trade_id=self._next_trade_id(),
            position_id=pos.position_id,
            side=PositionSide.BACK,
            team=opposite_team,
            odds=hedge_odds,
            stake=hedge_stake,
            trade_type="HEDGE",
        )
        pos.trades.append(trade)

        logger.info(f"🛡️ HEDGED {pos.position_id}: {opposite_team} @ {hedge_odds} ₹{hedge_stake} | P&L: ₹{pos.realized_pnl:.2f}")
        return pos

    # ── Bookset ─────────────────────────────────────────────────────────────

    def execute_bookset(
        self, match_id: str, stake_a: float, stake_b: float,
        odds_a: float, odds_b: float, guaranteed_profit: float,
    ) -> Optional[Position]:
        """Execute bookset for guaranteed profit"""
        pos = self.get_match_position(match_id)
        if not pos:
            return None

        pos.bookset_stake_a = stake_a
        pos.bookset_stake_b = stake_b
        pos.status = PositionStatus.BOOKSET
        pos.realized_pnl = guaranteed_profit

        # Record bookset trades
        for team, stake, odds, label in [
            (pos.team_a, stake_a, odds_a, "BOOKSET_A"),
            (pos.team_b, stake_b, odds_b, "BOOKSET_B"),
        ]:
            trade = Trade(
                trade_id=self._next_trade_id(),
                position_id=pos.position_id,
                side=PositionSide.BACK,
                team=team, odds=odds, stake=stake,
                trade_type=label,
            )
            pos.trades.append(trade)

        logger.info(f"💰 BOOKSET {pos.position_id}: Guaranteed ₹{guaranteed_profit:.2f}")
        return pos

    # ── Close Position ──────────────────────────────────────────────────────

    def close_position(self, match_id: str, reason: str, final_pnl: Optional[float] = None) -> Optional[Position]:
        """Close a position (match ended, manual close, etc.)"""
        pos = self.get_match_position(match_id)
        if not pos:
            return None

        if final_pnl is not None:
            pos.realized_pnl = final_pnl

        pos.status = PositionStatus.CLOSED
        pos.closed_at = datetime.now(timezone.utc).isoformat()
        pos.close_reason = reason
        self._total_realized_pnl += pos.realized_pnl

        logger.info(f"🏁 CLOSED {pos.position_id}: {reason} | P&L: ₹{pos.realized_pnl:.2f}")
        return pos

    # ── Queries ──────────────────────────────────────────────────────────────

    def get_match_position(self, match_id: str) -> Optional[Position]:
        pos_id = self._match_positions.get(match_id)
        return self._positions.get(pos_id) if pos_id else None

    def get_open_positions(self) -> List[Position]:
        return [p for p in self._positions.values() if p.status in (PositionStatus.OPEN, PositionStatus.HEDGED)]

    def get_all_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_total_exposure(self) -> float:
        return sum(p.total_exposure for p in self.get_open_positions())

    def get_total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.get_open_positions())

    def get_portfolio_summary(self) -> dict:
        open_pos = self.get_open_positions()
        all_pos = self.get_all_positions()
        return {
            "open_positions": len(open_pos),
            "total_positions": len(all_pos),
            "total_exposure": round(self.get_total_exposure(), 2),
            "unrealized_pnl": round(self.get_total_unrealized_pnl(), 2),
            "realized_pnl": round(self._total_realized_pnl, 2),
            "total_pnl": round(self._total_realized_pnl + self.get_total_unrealized_pnl(), 2),
            "positions": [p.to_dict() for p in open_pos],
        }

    def update_all_odds(self, match_id: str, odds_a: float, odds_b: float):
        """Update odds for all positions on a match"""
        pos = self.get_match_position(match_id)
        if pos and pos.status in (PositionStatus.OPEN, PositionStatus.HEDGED):
            pos.update_odds(odds_a, odds_b)
