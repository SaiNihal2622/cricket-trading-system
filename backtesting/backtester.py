"""
Backtesting Engine
Replays IPL ball-by-ball data to evaluate strategy performance.
Computes ROI, drawdown, and signal accuracy.
"""
import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from strategy_engine.decision_engine import DecisionEngine, MatchContext
from ml_model.predictor import CricketMLModel

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    match_id: str
    over: float
    signal: str
    confidence: float
    stake: float
    entry_odds: float
    current_odds_a: float
    current_odds_b: float
    win_probability: float
    hedge_amount: float = 0.0
    hedge_profit: float = 0.0
    bookset_profit: float = 0.0
    actual_outcome: Optional[int] = None  # 1 = team A won, 0 = team B won
    pnl: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    roi_pct: float
    signal_breakdown: dict
    trades: list[BacktestTrade]
    equity_curve: list[float]


class IPLDataLoader:
    """Loads IPL ball-by-ball CSV data"""

    def load_csv(self, filepath: str) -> pd.DataFrame:
        """Load and preprocess IPL ball-by-ball CSV"""
        df = pd.read_csv(filepath)

        # Standard column mapping for Cricsheet format
        column_map = {
            "match_id": "match_id",
            "inning": "innings",
            "over": "over_number",
            "ball": "ball_number",
            "batting_team": "batting_team",
            "bowling_team": "bowling_team",
            "batsman": "batsman",
            "bowler": "bowler",
            "runs_off_bat": "runs_scored",
            "extras": "extras",
            "wicket_type": "wicket_type",
            "player_dismissed": "player_dismissed",
        }

        for old, new in column_map.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})

        # Parse Cricsheet float `ball` (now renamed to `ball_number`) into `over_number`
        if "ball_number" in df.columns and "over_number" not in df.columns:
            temp_balls = df["ball_number"].copy()
            df["over_number"] = temp_balls.apply(lambda x: int(float(x)))
            df["ball_number"] = temp_balls.apply(lambda x: round((float(x) % 1) * 10))

        # Compute cumulative stats per match/innings
        df = df.sort_values(["match_id", "innings", "over_number", "ball_number"])

        # Cumulative runs and wickets
        df["is_wicket"] = df["wicket_type"].notna().astype(int)
        df["total_runs_ball"] = df.get("runs_scored", 0).fillna(0) + df.get("extras", 0).fillna(0)

        df["cum_runs"] = df.groupby(["match_id", "innings"])["total_runs_ball"].cumsum()
        df["cum_wickets"] = df.groupby(["match_id", "innings"])["is_wicket"].cumsum()

        # Over as float (4.3 = over 4, ball 3)
        if "over_number" in df.columns and "ball_number" in df.columns:
            df["overs"] = df["over_number"] + df["ball_number"] / 10

        # Run rate
        df["overs_float"] = df["over_number"] + df.get("ball_number", 1) / 6
        df["run_rate"] = df["cum_runs"] / df["overs_float"].clip(lower=0.1)

        return df

    def generate_synthetic_data(self, n_matches: int = 100) -> pd.DataFrame:
        """Generate synthetic IPL-style data for testing"""
        import random
        rng = random.Random(42)

        records = []
        teams = [
            "Mumbai Indians", "Chennai Super Kings", "Kolkata Knight Riders",
            "Royal Challengers Bangalore", "Delhi Capitals", "Sunrisers Hyderabad"
        ]

        for match_num in range(n_matches):
            match_id = f"IPL_2024_{match_num:03d}"
            team_a, team_b = rng.sample(teams, 2)
            winner = rng.choice([team_a, team_b])

            for innings in [1, 2]:
                batting = team_a if innings == 1 else team_b
                cum_runs = 0
                cum_wickets = 0

                for over in range(20):
                    for ball in range(1, 7):
                        run_choices = [0, 1, 1, 2, 4, 6]
                        weights = [30, 25, 15, 10, 12, 8]
                        runs = rng.choices(run_choices, weights=weights)[0]
                        is_wicket = (rng.random() < 0.04) and cum_wickets < 9

                        cum_runs += runs
                        if is_wicket:
                            cum_wickets += 1

                        overs_float = over + ball / 6
                        records.append({
                            "match_id": match_id,
                            "innings": innings,
                            "over_number": over,
                            "ball_number": ball,
                            "batting_team": batting,
                            "bowling_team": team_b if batting == team_a else team_a,
                            "runs_scored": runs,
                            "extras": 0,
                            "is_wicket": int(is_wicket),
                            "cum_runs": cum_runs,
                            "cum_wickets": cum_wickets,
                            "overs": over + ball / 10,
                            "run_rate": cum_runs / max(overs_float, 0.1),
                            "winner": winner,
                            "target": 165 if innings == 2 else 0,
                        })

        return pd.DataFrame(records)


class Backtester:
    """
    Replays IPL matches ball-by-ball and evaluates strategy performance.
    """

    def __init__(
        self,
        stake: float = 1000.0,
        decision_engine: Optional[DecisionEngine] = None,
        ml_model: Optional[CricketMLModel] = None,
    ):
        self.stake = stake
        self.engine = decision_engine or DecisionEngine()
        self.ml = ml_model or CricketMLModel()
        self.loader = IPLDataLoader()

    def run(
        self,
        df: pd.DataFrame,
        simulated_odds_fn=None,
    ) -> BacktestResult:
        """
        Run backtest over ball-by-ball data.
        
        Args:
            df: Ball-by-ball DataFrame
            simulated_odds_fn: Function(row) -> (odds_a, odds_b) 
        """
        logger.info(f"Starting backtest over {len(df)} balls...")

        trades: list[BacktestTrade] = []
        equity_curve = [0.0]
        cumulative_pnl = 0.0
        peak_equity = 0.0
        max_drawdown = 0.0

        # Process each match
        match_ids = df["match_id"].unique()
        logger.info(f"Processing {len(match_ids)} matches...")

        for match_id in match_ids:
            match_df = df[df["match_id"] == match_id].copy()
            winner = match_df["winner"].iloc[0] if "winner" in match_df.columns else None
            entry_odds = 0.0

            for _, row in match_df.iterrows():
                state = self._row_to_state(row)

                # Simulate odds
                if simulated_odds_fn:
                    odds_a, odds_b = simulated_odds_fn(row)
                else:
                    odds_a, odds_b = self._default_odds(row)

                # ML prediction
                ml_pred = self.ml.predict(state)

                # Build context
                ctx = MatchContext(
                    match_id=1,
                    team_a=str(row.get("batting_team", "Team A")),
                    team_b=str(row.get("bowling_team", "Team B")),
                    innings=int(row.get("innings", 1)),
                    current_over=float(row.get("overs", 0)),
                    total_runs=int(row.get("cum_runs", 0)),
                    total_wickets=int(row.get("cum_wickets", 0)),
                    run_rate=float(row.get("run_rate", 0)),
                    required_run_rate=float(state.get("required_run_rate", 0)),
                    target=int(row.get("target", 0)),
                    team_a_odds=odds_a,
                    team_b_odds=odds_b,
                    stake=self.stake,
                    entry_odds=entry_odds or odds_a,
                    backed_team="A",
                    win_probability=ml_pred.win_probability,
                    momentum_score=ml_pred.momentum_score,
                )

                decision = self.engine.evaluate(ctx)

                if decision.signal in ("ENTER", "LOSS_CUT", "BOOKSET"):
                    if entry_odds == 0:
                        entry_odds = odds_a

                    # Calculate P&L
                    pnl = self._calculate_pnl(decision, winner, row, odds_a, odds_b)
                    cumulative_pnl += pnl
                    equity_curve.append(cumulative_pnl)

                    peak_equity = max(peak_equity, cumulative_pnl)
                    drawdown = peak_equity - cumulative_pnl
                    max_drawdown = max(max_drawdown, drawdown)

                    trade = BacktestTrade(
                        match_id=str(match_id),
                        over=float(row.get("overs", 0)),
                        signal=decision.signal,
                        confidence=decision.confidence,
                        stake=self.stake,
                        entry_odds=entry_odds,
                        current_odds_a=odds_a,
                        current_odds_b=odds_b,
                        win_probability=ml_pred.win_probability,
                        hedge_amount=decision.loss_cut.hedge_amount if decision.loss_cut else 0,
                        hedge_profit=decision.loss_cut.hedge_profit if decision.loss_cut else 0,
                        bookset_profit=decision.bookset.guaranteed_profit if decision.bookset else 0,
                        actual_outcome=1 if winner == row.get("batting_team") else 0,
                        pnl=pnl,
                    )
                    trades.append(trade)

        # Compute metrics
        total = len(trades)
        winners = sum(1 for t in trades if t.pnl > 0)
        losers = total - winners
        win_rate = winners / max(total, 1)
        roi = (cumulative_pnl / (self.stake * max(total, 1))) * 100

        returns = np.diff(equity_curve) if len(equity_curve) > 1 else [0]
        sharpe = (np.mean(returns) / (np.std(returns) + 1e-9)) * np.sqrt(252)

        signal_breakdown = {}
        for trade in trades:
            signal_breakdown[trade.signal] = signal_breakdown.get(trade.signal, 0) + 1

        logger.info(
            f"Backtest complete: {total} trades | {win_rate*100:.1f}% win rate | "
            f"ROI: {roi:.2f}% | Max DD: {max_drawdown:.2f}"
        )

        return BacktestResult(
            total_trades=total,
            winning_trades=winners,
            losing_trades=losers,
            win_rate=round(win_rate, 4),
            total_pnl=round(cumulative_pnl, 2),
            max_drawdown=round(max_drawdown, 2),
            sharpe_ratio=round(float(sharpe), 4),
            roi_pct=round(roi, 2),
            signal_breakdown=signal_breakdown,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _row_to_state(self, row) -> dict:
        """Convert DataFrame row to match state dict"""
        return {
            "total_runs": int(row.get("cum_runs", 0)),
            "total_wickets": int(row.get("cum_wickets", 0)),
            "overs": float(row.get("overs", 0)),
            "run_rate": float(row.get("run_rate", 0)),
            "innings": int(row.get("innings", 1)),
            "target": int(row.get("target", 0)),
            "batting_team": str(row.get("batting_team", "")),
            "required_run_rate": self._calc_rrr(row),
            "last_ball": str(int(row.get("runs_scored", 0))) if not row.get("is_wicket") else "W",
            "powerplay_runs": int(row.get("cum_runs", 0)) if float(row.get("overs", 0)) <= 6 else 0,
        }

    def _calc_rrr(self, row) -> float:
        innings = int(row.get("innings", 1))
        if innings != 2:
            return 0.0
        target = int(row.get("target", 0))
        runs = int(row.get("cum_runs", 0))
        overs = float(row.get("overs", 0))
        balls_remaining = max(1, (20 - overs) * 6)
        runs_needed = max(0, target - runs)
        return round((runs_needed / balls_remaining) * 6, 2)

    def _default_odds(self, row) -> tuple[float, float]:
        """Simulate market odds from win probability"""
        cum_runs = int(row.get("cum_runs", 0))
        cum_wkts = int(row.get("cum_wickets", 0))
        overs = float(row.get("overs", 0))

        # Rough heuristic
        projected = cum_runs + (cum_runs / max(overs, 0.1)) * (20 - overs)
        par = 165
        score_edge = (projected - par) / 50
        win_prob_a = max(0.1, min(0.9, 0.5 + score_edge - cum_wkts * 0.04))

        margin = 1.05  # bookmaker margin
        odds_a = round((1 / win_prob_a) * margin, 2)
        odds_b = round((1 / (1 - win_prob_a)) * margin, 2)
        return max(1.01, odds_a), max(1.01, odds_b)

    def _calculate_pnl(self, decision, winner, row, odds_a, odds_b) -> float:
        """Calculate P&L for a trade"""
        batting_team = str(row.get("batting_team", ""))
        batting_won = (winner == batting_team) if winner else False

        if decision.signal == "ENTER":
            # Simple back bet on team A
            return (self.stake * odds_a - self.stake) if batting_won else -self.stake

        elif decision.signal == "LOSS_CUT" and decision.loss_cut:
            # Hedge guarantees some return
            return decision.loss_cut.hedge_profit

        elif decision.signal == "BOOKSET" and decision.bookset:
            # Guaranteed profit
            return decision.bookset.guaranteed_profit

        return 0.0
