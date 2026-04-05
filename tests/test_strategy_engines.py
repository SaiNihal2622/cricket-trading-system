"""
Unit Tests for Cricket Trading Intelligence System

Tests cover:
  - LossCutEngine: hedge calculations, trigger conditions
  - BooksetEngine: stake distribution, arb detection
  - SessionEngine: phase predictions
  - DecisionEngine: signal priority ordering
  - ML FeatureEngineering: feature extraction
  - RedisCache: key formatting
"""
import sys
import os
import pytest
import numpy as np

# Allow imports from backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ─── Loss Cut Engine Tests ──────────────────────────────────────────────────────

class TestLossCutEngine:
    def setup_method(self):
        from strategy_engine.loss_cut_engine import LossCutEngine
        self.engine = LossCutEngine()

    def test_hedge_basic_calculation(self):
        """Hedge = (stake × entry_odds) / current_odds"""
        hedge, profit = self.engine.calculate_hedge(
            stake=1000, entry_odds=2.0, current_odds=1.5
        )
        # hedge = (1000 * 2.0) / 1.5 = 1333.33
        assert abs(hedge - 1333.33) < 0.01
        # profit = (1000 * 2.0) - (1000 + 1333.33) = 2000 - 2333.33 = -333.33
        assert abs(profit - (-333.33)) < 0.01

    def test_hedge_zero_odds(self):
        """Should return 0,0 for invalid odds"""
        hedge, profit = self.engine.calculate_hedge(1000, 0, 1.5)
        assert hedge == 0.0
        assert profit == 0.0

    def test_no_trigger_normal_conditions(self):
        """Should not trigger under normal match conditions"""
        result = self.engine.evaluate(
            stake=1000, entry_odds=1.85, current_team_odds=1.80,
            current_over=8.0, wickets_fallen=2, run_rate=7.5,
            required_rr=0, is_wicket_just_fell=False, win_probability=0.55,
        )
        assert result.should_trigger is False
        assert result.urgency == "LOW"

    def test_trigger_odds_drop(self):
        """Should trigger on significant odds drop (>15%)"""
        result = self.engine.evaluate(
            stake=1000, entry_odds=2.00, current_team_odds=1.50,
            current_over=10.0, wickets_fallen=3, run_rate=6.0,
            required_rr=8.0, is_wicket_just_fell=False, win_probability=0.4,
        )
        assert result.should_trigger is True
        assert "Odds dropped" in result.trigger_reason

    def test_trigger_wicket_in_powerplay(self):
        """Wicket in powerplay (1-6) should trigger"""
        result = self.engine.evaluate(
            stake=1000, entry_odds=1.85, current_team_odds=1.85,
            current_over=4.0, wickets_fallen=3, run_rate=5.0,
            required_rr=0, is_wicket_just_fell=True, win_probability=0.45,
        )
        assert result.should_trigger is True
        assert "critical over" in result.trigger_reason.lower()

    def test_trigger_win_prob_critical(self):
        """Win probability < 25% should trigger CRITICAL"""
        result = self.engine.evaluate(
            stake=1000, entry_odds=1.85, current_team_odds=3.50,
            current_over=15.0, wickets_fallen=7, run_rate=5.0,
            required_rr=12.0, is_wicket_just_fell=False, win_probability=0.15,
        )
        assert result.should_trigger is True
        assert result.urgency == "CRITICAL"

    def test_trigger_rr_collapse(self):
        """Run rate collapse (gap > 3) should trigger"""
        result = self.engine.evaluate(
            stake=1000, entry_odds=1.85, current_team_odds=2.50,
            current_over=12.0, wickets_fallen=4, run_rate=5.0,
            required_rr=10.0, is_wicket_just_fell=False, win_probability=0.35,
        )
        assert result.should_trigger is True
        assert "RR collapse" in result.trigger_reason

    def test_optimal_exit_point(self):
        """Optimal exit should return correct position"""
        result = self.engine.get_optimal_exit_point(
            entry_odds=1.80, current_odds=2.20,
            win_probability=0.55, over_number=12.0
        )
        assert result["position"] == "AHEAD"
        assert "recommendation" in result


# ─── Bookset Engine Tests ───────────────────────────────────────────────────────

class TestBooksetEngine:
    def setup_method(self):
        from strategy_engine.bookset_engine import BooksetEngine
        self.engine = BooksetEngine()

    def test_equal_return(self):
        """Both stakes × odds should produce equal returns"""
        result = self.engine.calculate(odds_a=2.0, odds_b=2.0, total_stake=1000)
        assert abs(result.stake_a - 500) < 1.0
        assert abs(result.stake_b - 500) < 1.0

    def test_arb_detection(self):
        """Overround < 1 = arbitrage opportunity"""
        # 1/1.80 + 1/2.50 = 0.556 + 0.400 = 0.956 < 1 → arb with >2% profit
        result = self.engine.calculate(odds_a=1.80, odds_b=2.50, total_stake=1000)
        assert result.overround < 1.0
        assert result.is_profitable is True
        assert result.guaranteed_profit > 0

    def test_no_arb_with_margin(self):
        """Normal odds with bookmaker margin should not be profitable"""
        result = self.engine.calculate(odds_a=1.85, odds_b=2.10, total_stake=1000)
        assert result.overround > 1.0
        assert result.is_profitable is False

    def test_invalid_odds(self):
        """Odds <= 1 should return invalid result"""
        result = self.engine.calculate(odds_a=0.5, odds_b=2.0, total_stake=1000)
        assert result.is_profitable is False
        assert result.stake_a == 0
        assert "Odds must be" in result.explanation

    def test_implied_probabilities(self):
        """Implied probabilities should be correct"""
        result = self.engine.calculate(odds_a=2.0, odds_b=3.0, total_stake=1000)
        assert abs(result.implied_prob_a - 50.0) < 0.01
        assert abs(result.implied_prob_b - 33.33) < 0.01

    def test_partial_bookset(self):
        """Partial bookset should reduce exposure"""
        result = self.engine.partial_bookset(
            original_stake=1000, original_odds=1.85,
            current_odds_a=1.90, current_odds_b=2.20,
            partial_pct=0.5
        )
        assert result["hedge_stake"] == 500
        assert "remaining_stake" in result

    def test_optimal_moment(self):
        """Should find best bookset point in odds history"""
        history = [
            {"team_a_odds": 1.85, "team_b_odds": 2.10, "timestamp": "t1"},
            {"team_a_odds": 1.90, "team_b_odds": 2.20, "timestamp": "t2"},
            {"team_a_odds": 2.00, "team_b_odds": 2.00, "timestamp": "t3"},
        ]
        result = self.engine.find_optimal_bookset_moment(history, 1.85, 1000)
        assert result["timestamp"] is not None


# ─── Session Engine Tests ───────────────────────────────────────────────────────

class TestSessionEngine:
    def setup_method(self):
        from strategy_engine.session_engine import SessionEngine
        self.engine = SessionEngine()

    def test_powerplay_projection(self):
        """Powerplay prediction should be within reasonable range"""
        result = self.engine.predict_powerplay(
            current_over=3.0, current_runs=28, current_wickets=1,
            batting_team="Mumbai Indians"
        )
        assert result.phase == "powerplay"
        assert 35 < result.predicted_runs < 80  # reasonable range
        assert result.confidence_interval_low <= result.predicted_runs
        assert result.confidence_interval_high >= result.predicted_runs

    def test_completed_phase(self):
        """Phase past over 6 should return completed"""
        result = self.engine.predict_powerplay(
            current_over=7.0, current_runs=54, current_wickets=2
        )
        assert result.predicted_runs == 54
        assert result.value_signal == "NEUTRAL"

    def test_total_score_projection(self):
        """Total score prediction should project forward"""
        result = self.engine.predict_total_score(
            current_over=10.0, current_runs=78, current_wickets=3,
            batting_team="Royal Challengers Bangalore"
        )
        assert result.phase == "total_score"
        assert result.predicted_runs > 78  # must be more than current

    def test_wicket_penalty(self):
        """More wickets should lower predicted runs"""
        low_wkt = self.engine.predict_total_score(
            current_over=10.0, current_runs=78, current_wickets=2
        )
        high_wkt = self.engine.predict_total_score(
            current_over=10.0, current_runs=78, current_wickets=7
        )
        assert high_wkt.predicted_runs < low_wkt.predicted_runs

    def test_team_adjustment(self):
        """RCB (1.12x) should produce higher prediction than SRH (0.97x)"""
        rcb = self.engine.predict_total_score(
            current_over=5.0, current_runs=40, current_wickets=1,
            batting_team="Royal Challengers Bangalore"
        )
        srh = self.engine.predict_total_score(
            current_over=5.0, current_runs=40, current_wickets=1,
            batting_team="Sunrisers Hyderabad"
        )
        assert rcb.predicted_runs > srh.predicted_runs

    def test_phase_dispatcher(self):
        """predict_phase_score should route correctly"""
        result = self.engine.predict_phase_score(
            phase="powerplay", current_over=3.0,
            current_runs=25, current_wickets=1
        )
        assert result.phase == "powerplay"


# ─── Decision Engine Tests ──────────────────────────────────────────────────────

class TestDecisionEngine:
    def setup_method(self):
        from strategy_engine.decision_engine import DecisionEngine, MatchContext
        self.engine = DecisionEngine()
        self.MatchContext = MatchContext

    def _make_ctx(self, **overrides):
        defaults = dict(
            match_id=1, team_a="MI", team_b="CSK", innings=1,
            current_over=10.0, total_runs=75, total_wickets=3,
            run_rate=7.5, required_run_rate=0, target=0,
            team_a_odds=1.85, team_b_odds=2.10, stake=1000,
            entry_odds=1.85, backed_team="A",
            win_probability=0.55, momentum_score=0.5,
        )
        defaults.update(overrides)
        return self.MatchContext(**defaults)

    def test_hold_signal_default(self):
        """Default conditions should return HOLD"""
        ctx = self._make_ctx()
        decision = self.engine.evaluate(ctx)
        assert decision.signal == "HOLD"

    def test_loss_cut_high_urgency(self):
        """Critical loss cut should override everything"""
        ctx = self._make_ctx(
            win_probability=0.15, entry_odds=2.0,
            team_a_odds=4.0, current_over=16.0, total_wickets=8,
            required_run_rate=14.0, run_rate=5.0,
        )
        decision = self.engine.evaluate(ctx)
        assert decision.signal == "LOSS_CUT"
        assert decision.urgency in ("HIGH", "CRITICAL")

    def test_enter_signal(self):
        """High win prob + high momentum should trigger ENTER"""
        ctx = self._make_ctx(
            win_probability=0.78, momentum_score=0.80,
            team_a_odds=1.50, team_b_odds=3.00,
            entry_odds=1.50,  # match current odds to avoid loss cut trigger
        )
        decision = self.engine.evaluate(ctx)
        assert decision.signal == "ENTER"
        assert decision.entry_team is not None

    def test_signal_has_factors(self):
        """Every decision should include factor breakdown"""
        ctx = self._make_ctx()
        decision = self.engine.evaluate(ctx)
        assert "win_probability" in decision.factors
        assert "momentum_score" in decision.factors
        assert "entry_score" in decision.factors

    def test_to_dict_serializable(self):
        """Output should be JSON-serializable"""
        import json
        ctx = self._make_ctx()
        decision = self.engine.evaluate(ctx)
        d = decision.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_session_signal_in_powerplay(self):
        """Early powerplay should consider session signal"""
        ctx = self._make_ctx(
            current_over=3.0, total_runs=35, total_wickets=0,
            win_probability=0.55, momentum_score=0.7,
        )
        decision = self.engine.evaluate(ctx)
        # May or may not trigger SESSION, but factors should include it
        assert "session_signal" in decision.factors


# ─── ML Feature Engineering Tests ───────────────────────────────────────────────

class TestFeatureEngineering:
    def setup_method(self):
        from ml_model.predictor import FeatureEngineering
        self.fe = FeatureEngineering()

    def test_feature_count(self):
        """Should produce exactly 27 features"""
        state = {
            "overs": 10.0, "total_runs": 75, "total_wickets": 3,
            "run_rate": 7.5, "required_run_rate": 8.0,
            "target": 180, "innings": 2, "powerplay_runs": 48,
        }
        features = self.fe.extract(state)
        assert len(features) == 27

    def test_feature_dtype(self):
        """Features should be float32 numpy array"""
        features = self.fe.extract({"overs": 5.0, "total_runs": 40})
        assert features.dtype == np.float32

    def test_phase_flags_exclusive(self):
        """Only one phase flag should be 1 at a time"""
        for overs in [3.0, 10.0, 18.0]:
            features = self.fe.extract({"overs": overs})
            pp, mid, death = features[9], features[10], features[11]
            assert sum([pp, mid, death]) == 1, f"Overs {overs}: PP={pp}, MID={mid}, DEATH={death}"

    def test_pressure_index_range(self):
        """Pressure index should be in [0, 1]"""
        features = self.fe.extract({
            "overs": 15, "total_runs": 100, "total_wickets": 7,
            "run_rate": 5, "required_run_rate": 14, "innings": 2, "target": 200,
        })
        pressure = features[19]
        assert 0 <= pressure <= 1

    def test_batch_extraction(self):
        """Batch extraction should stack correctly"""
        states = [
            {"overs": 5, "total_runs": 40},
            {"overs": 10, "total_runs": 80},
        ]
        batch = self.fe.extract_batch(states)
        assert batch.shape == (2, 27)


# ─── ML Model Tests ────────────────────────────────────────────────────────────

class TestCricketMLModel:
    def setup_method(self):
        from ml_model.predictor import CricketMLModel
        self.model = CricketMLModel()  # no model file = heuristic mode

    def test_heuristic_prediction(self):
        """Heuristic model should return valid prediction"""
        pred = self.model.predict({
            "overs": 10, "total_runs": 85, "total_wickets": 2,
            "run_rate": 8.5, "innings": 1,
        })
        assert 0 < pred.win_probability < 1
        assert 0 <= pred.momentum_score <= 1
        assert pred.model_version == "heuristic_v1"
        assert pred.confidence == 0.60

    def test_chasing_probability(self):
        """Chasing team losing badly should have low win prob"""
        pred = self.model.predict({
            "overs": 18, "total_runs": 100, "total_wickets": 8,
            "run_rate": 5.5, "required_run_rate": 15.0,
            "innings": 2, "target": 200,
        })
        assert pred.win_probability < 0.3


# ─── Backtester Tests ──────────────────────────────────────────────────────────

class TestBacktester:
    def test_synthetic_data_generation(self):
        """Should generate valid synthetic data"""
        from backtesting.backtester import IPLDataLoader
        loader = IPLDataLoader()
        df = loader.generate_synthetic_data(n_matches=5)
        assert len(df) > 0
        assert "match_id" in df.columns
        assert "cum_runs" in df.columns
        assert df["match_id"].nunique() == 5

    def test_backtest_runs(self):
        """Full backtest should complete without errors"""
        from backtesting.backtester import Backtester, IPLDataLoader
        loader = IPLDataLoader()
        df = loader.generate_synthetic_data(n_matches=3)
        bt = Backtester(stake=1000)
        result = bt.run(df)
        assert result.total_trades >= 0
        assert len(result.equity_curve) > 0
        assert 0 <= result.win_rate <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
