"""
Unit tests for Autonomous Trading Agent classes.
"""
import sys
import os
import pytest
from datetime import datetime

# Allow imports from backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.position_manager import PositionManager, PositionStatus
from agent.risk_manager import RiskManager
from agent.execution_engine import SimulatedExchange, OrderResult

class TestPositionManager:
    def setup_method(self):
        self.pm = PositionManager()

    def test_open_position(self):
        pos = self.pm.open_position(
            match_id="101", team_a="MI", team_b="CSK",
            backed_team="MI", odds=1.85, stake=1000
        )
        assert pos.status == PositionStatus.OPEN
        assert pos.total_exposure == 1000
        assert pos.potential_profit == 850
        assert len(self.pm.get_open_positions()) == 1

    def test_loss_cut(self):
        self.pm.open_position(
            match_id="101", team_a="MI", team_b="CSK",
            backed_team="MI", odds=2.00, stake=1000
        )
        # Hedge on CSK at 1.50 with 1333
        pos = self.pm.execute_loss_cut(
            match_id="101", hedge_odds=1.50, hedge_stake=1333.33
        )
        assert pos.status == PositionStatus.HEDGED
        assert round(pos.realized_pnl, 0) == -333.0  # (1000*2) - (1000+1333)
        assert round(pos.total_exposure, 2) == -333.33  # 1000 - 1333.33

    def test_bookset(self):
        self.pm.open_position(
            match_id="101", team_a="MI", team_b="CSK",
            backed_team="MI", odds=1.85, stake=1000
        )
        pos = self.pm.execute_bookset(
            match_id="101",
            stake_a=500, stake_b=500,
            odds_a=1.9, odds_b=2.1,
            guaranteed_profit=50
        )
        assert pos.status == PositionStatus.BOOKSET
        assert pos.realized_pnl == 50
        assert pos.total_exposure == 0

    def test_close_position(self):
        self.pm.open_position(
            match_id="101", team_a="MI", team_b="CSK",
            backed_team="MI", odds=1.85, stake=1000
        )
        pos = self.pm.close_position("101", reason="Match Ended", final_pnl=850)
        assert pos.status == PositionStatus.CLOSED
        assert len(self.pm.get_open_positions()) == 0
        summary = self.pm.get_portfolio_summary()
        assert summary["realized_pnl"] == 850


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager(
            initial_bankroll=10000,
            max_stake_per_trade=1000,
            max_daily_loss=2000,
        )

    def test_approve_trade_normal(self):
        res = self.rm.approve_trade(
            proposed_stake=1000, current_exposure=0,
            win_probability=0.7, confidence=0.8, odds=2.0
        )
        assert res["approved"] is True
        # Kelly size is checked, might adjust stake
        assert res["adjusted_stake"] > 0

    def test_approve_trade_insufficient_confidence(self):
        res = self.rm.approve_trade(
            proposed_stake=1000, current_exposure=0,
            win_probability=0.7, confidence=0.4, odds=2.0
        )
        assert res["approved"] is False
        assert "Confidence too low" in res["rejections"][0]

    def test_approve_trade_circuit_breaker(self):
        self.rm._trigger_circuit_breaker("Test")
        res = self.rm.approve_trade(
            proposed_stake=1000, current_exposure=0,
            win_probability=0.7, confidence=0.8, odds=2.0
        )
        assert res["approved"] is False
        assert "Circuit breaker active" in res["rejections"][0]

    def test_record_trade_result(self):
        self.rm.record_trade_result(500)
        assert self.rm.current_bankroll == 10500
        assert self.rm.consecutive_losses == 0

        self.rm.record_trade_result(-1000)
        assert self.rm.current_bankroll == 9500
        assert self.rm.consecutive_losses == 1


class TestSimulatedExchange:
    def setup_method(self):
        # 0% slippage for easier math in test
        self.ex = SimulatedExchange(initial_balance=10000, slippage_pct=0)

    @pytest.mark.asyncio
    async def test_place_back(self):
        res = await self.ex.place_back("101", "MI", 2.0, 1000)
        assert res.success is True
        assert res.filled_stake == 1000
        assert res.filled_odds == 2.0
        assert self.ex.balance == 9000

    @pytest.mark.asyncio
    async def test_place_lay(self):
        res = await self.ex.place_lay("101", "CSK", 3.0, 1000)
        assert res.success is True
        assert res.filled_stake == 1000
        # For a lay bet at 3.0, liability is 2000
        assert self.ex.balance == 8000

    @pytest.mark.asyncio
    async def test_insufficient_balance(self):
        res = await self.ex.place_back("101", "MI", 2.0, 20000)
        assert res.success is False
        assert "Insufficient balance" in res.message
