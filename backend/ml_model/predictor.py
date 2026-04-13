"""
XGBoost Cricket Win Probability Model
Features: overs, runs, wickets, run_rate, player stats, venue stats
Output: win probability + momentum score
"""
import os
import logging
import pickle
import numpy as np
import pandas as pd
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MLPrediction:
    win_probability: float
    momentum_score: float
    feature_importance: dict
    confidence: float
    model_version: str = "xgb_v1"


class FeatureEngineering:
    """Transforms raw match state into ML features"""

    FEATURE_NAMES = [
        # Match state
        "overs_completed",
        "runs_scored",
        "wickets_fallen",
        "current_run_rate",
        "required_run_rate",
        "rr_differential",
        "balls_remaining",
        "target",
        "runs_needed",

        # Phase features
        "is_powerplay",
        "is_middle_overs",
        "is_death_overs",
        "over_bucket",

        # Wicket features
        "wickets_in_pp",
        "wickets_per_10_overs",
        "top_order_intact",

        # Run rate features
        "run_rate_acceleration",
        "pp_run_rate",
        "boundary_rate",

        # Pressure index
        "pressure_index",
        "momentum_indicator",

        # Venue
        "venue_avg_score",
        "venue_pp_avg",

        # Team strength (encoded)
        "batting_team_strength",
        "bowling_team_strength",

        # Score projections
        "projected_score",
        "score_vs_par",
    ]

    def extract(self, state: dict) -> np.ndarray:
        """Extract features from match state dict"""
        overs = float(state.get("overs", 0))
        runs = int(state.get("total_runs", 0))
        wickets = int(state.get("total_wickets", 0))
        crr = float(state.get("run_rate", 0))
        rrr = float(state.get("required_run_rate", 0))
        target = int(state.get("target", 0))
        innings = int(state.get("innings", 1))
        pp_runs = int(state.get("powerplay_runs", 0))

        # Derived features
        balls_done = int(overs) * 6 + round((overs % 1) * 10)
        balls_remaining = max(0, 120 - balls_done)
        runs_needed = max(0, target - runs) if target > 0 else 0
        rr_diff = crr - rrr if rrr > 0 else 0

        # Phase flags
        is_pp = 1 if overs <= 6 else 0
        is_middle = 1 if 6 < overs <= 15 else 0
        is_death = 1 if overs > 15 else 0
        over_bucket = int(overs // 5)

        # Wicket features
        wickets_per_10 = wickets / max(overs, 1) * 10
        top_order_intact = 1 if wickets <= 2 else 0
        wickets_in_pp = min(wickets, pp_runs // 30) if overs <= 6 else 0  # approx

        # Pressure index (high = under pressure)
        if innings == 2 and rrr > 0:
            pressure = min(1, (rrr - crr + wickets * 0.5) / 10)
        else:
            pressure = wickets * 0.1
        pressure = max(0, min(1, pressure))

        # Momentum (recent run rate vs match average)
        match_avg_rr = runs / max(overs, 0.1)
        momentum = min(1, max(0, (crr - match_avg_rr + 2) / 4))

        # Projection
        projected_score = runs + (crr * (20 - overs)) if overs < 20 else runs
        par_score = 165  # T20 average par
        score_vs_par = (projected_score - par_score) / par_score

        # Venue (defaulting to average values)
        venue_avg = float(state.get("venue_avg_score", 165))
        venue_pp_avg = float(state.get("venue_pp_avg", 52))

        # Team strengths (1.0 = average)
        batting_str = float(state.get("batting_team_strength", 1.0))
        bowling_str = float(state.get("bowling_team_strength", 1.0))

        # Boundary rate
        boundary_rate = float(state.get("boundary_rate", 0.25))

        # PP run rate
        pp_rr = (pp_runs / 6) if overs >= 6 else (runs / max(overs, 0.1))

        features = [
            overs,                  # 0
            runs,                   # 1
            wickets,                # 2
            crr,                    # 3
            rrr,                    # 4
            rr_diff,                # 5
            balls_remaining,        # 6
            target,                 # 7
            runs_needed,            # 8
            is_pp,                  # 9
            is_middle,              # 10
            is_death,               # 11
            over_bucket,            # 12
            wickets_in_pp,          # 13
            wickets_per_10,         # 14
            top_order_intact,       # 15
            0.0,                    # 16 run_rate_acceleration (needs prev state)
            pp_rr,                  # 17
            boundary_rate,          # 18
            pressure,               # 19
            momentum,               # 20
            venue_avg,              # 21
            venue_pp_avg,           # 22
            batting_str,            # 23
            bowling_str,            # 24
            projected_score,        # 25
            score_vs_par,           # 26
        ]

        return np.array(features, dtype=np.float32)

    def extract_batch(self, states: list[dict]) -> np.ndarray:
        """Extract features from a list of states"""
        return np.vstack([self.extract(s) for s in states])


class CricketMLModel:
    """
    Win probability model — uses statistical heuristic (no XGBoost dependency).

    The heuristic uses:
    - IPL 17-year averages (venue stats, phase averages, H2H records)
    - Run rate vs required run rate differential
    - Wickets fallen + phase (powerplay/middle/death)
    - DLS-style resource calculation for 2nd innings

    Gemini AI is the primary decision engine; this provides the numeric
    win_probability input that feeds into the decision engine and Gemini prompt.
    """

    def __init__(self, model_path: str = "", scaler_path: str = "", ml_enabled: bool = False):
        self.feature_eng   = FeatureEngineering()
        self._model_loaded = False
        # ml_enabled=False means always use heuristic (no XGBoost needed)
        if ml_enabled and model_path and os.path.exists(model_path):
            try:
                with open(model_path, "rb") as f:
                    self.model = pickle.load(f)
                self._model_loaded = True
                logger.info(f"XGBoost model loaded: {model_path}")
            except Exception as e:
                logger.warning(f"XGBoost load failed: {e} — using heuristic")
                self.model = None
        else:
            self.model  = None
            self.scaler = None
            logger.info("CricketMLModel: heuristic mode (ML_ENABLED=false)")

    def predict(self, match_state: dict) -> MLPrediction:
        """Predict win probability + momentum using IPL heuristic."""
        features = self.feature_eng.extract(match_state)
        return self._heuristic_predict(match_state, features)

    def _xgb_predict(self, features: np.ndarray, state: dict) -> MLPrediction:
        """XGBoost prediction"""
        try:
            if self.scaler:
                features = self.scaler.transform(features.reshape(1, -1))[0]

            X = features.reshape(1, -1)
            win_prob = float(self.model.predict_proba(X)[0][1])
            momentum = self._calc_momentum(state)

            # Feature importance
            importance = {}
            if hasattr(self.model, "feature_importances_"):
                for name, imp in zip(FeatureEngineering.FEATURE_NAMES, self.model.feature_importances_):
                    importance[name] = round(float(imp), 4)

            return MLPrediction(
                win_probability=round(win_prob, 4),
                momentum_score=round(momentum, 4),
                feature_importance=importance,
                confidence=0.85,
                model_version="xgb_v1"
            )
        except Exception as e:
            logger.error(f"XGB prediction error: {e}")
            return self._heuristic_predict(state, features)

    def _heuristic_predict(self, state: dict, features: np.ndarray) -> MLPrediction:
        """
        IPL-calibrated heuristic using 17-year historical data tables.

        Layers (in order of application):
        1. Base win% from SITUATION_WIN_PCT table (overs × wickets × innings)
        2. Venue par adjustment (venue avg vs IPL avg 167)
        3. H2H edge adjustment (historical head-to-head win %)
        4. Team strength adjustment (batting depth, bowling attack ratings)
        5. Live RRR vs CRR momentum adjustment (2nd innings only)
        """
        from data_ingestion.historical_data import HistoricalDataEngine
        hist = HistoricalDataEngine()

        innings  = int(state.get("innings", 1))
        overs    = float(state.get("overs", 0))
        runs     = int(state.get("total_runs", 0))
        wickets  = int(state.get("total_wickets", 0))
        crr      = float(state.get("run_rate", 0))
        rrr      = float(state.get("required_run_rate", 0))
        target   = int(state.get("target", 0))
        team_a   = state.get("team_a", "")
        team_b   = state.get("team_b", "")
        venue    = state.get("venue", "")

        # ── Layer 1: Situation win% from historical table ──────────────────
        base_win_pct = hist.get_situation_win_pct(overs, wickets, innings, crr, rrr)
        win_prob = base_win_pct / 100.0  # convert to 0-1

        # ── Layer 2: Venue adjustment ──────────────────────────────────────
        if venue:
            vs = hist.get_venue_stats(venue)
            venue_avg  = vs.get("avg_1st_innings", 167)
            ipl_avg    = 167
            # Batting venue (avg > 167) lifts batting team's probability slightly
            venue_adj  = (venue_avg - ipl_avg) / 1000  # max ±3% effect
            win_prob  += venue_adj

        # ── Layer 3: H2H adjustment ────────────────────────────────────────
        if team_a and team_b:
            h2h = hist.get_h2h_win_pct(team_a, team_b)  # team_a win %
            h2h_edge = (h2h - 50) / 1000                 # max ±5% effect
            win_prob += h2h_edge

        # ── Layer 4: Team strength adjustment ─────────────────────────────
        if team_a:
            ra = hist.get_team_rating(team_a)
            rb = hist.get_team_rating(team_b) if team_b else {"overall": 7.0}
            strength_edge = (ra.get("overall", 7.0) - rb.get("overall", 7.0)) / 100
            win_prob += strength_edge  # max ±1% per rating point difference

        # ── Layer 5: 1st innings par check ────────────────────────────────
        if innings == 1 and overs > 3 and crr > 0:
            projected    = runs + crr * max(0, 20 - overs)
            venue_par    = hist.get_venue_stats(venue).get("avg_1st_innings", 167) if venue else 167
            par_adj      = (projected - venue_par) / 500   # max ±3% effect
            win_prob    += par_adj

        # ── Clamp ──────────────────────────────────────────────────────────
        win_prob = round(max(0.05, min(0.95, win_prob)), 4)
        momentum = self._calc_momentum(state)

        return MLPrediction(
            win_probability=win_prob,
            momentum_score=momentum,
            feature_importance={
                "situation_table": round(base_win_pct / 100, 3),
                "venue":           venue or "default",
                "h2h":             f"{team_a} vs {team_b}",
                "team_strength":   f"{team_a}:{ra.get('overall',7) if team_a else '-'}",
            },
            confidence=0.72,        # higher than raw heuristic since historical data used
            model_version="historical_v1"
        )

    def _calc_momentum(self, state: dict) -> float:
        """Calculate momentum score based on recent scoring patterns"""
        crr = float(state.get("run_rate", 0))
        wickets = int(state.get("total_wickets", 0))
        overs = float(state.get("overs", 0))
        last_ball = state.get("last_ball", "")

        # Base momentum from run rate
        base = min(1, max(0, (crr - 6) / 6))  # 12 rpo = full momentum

        # Wicket damper
        wicket_factor = max(0.4, 1 - wickets * 0.06)

        # Last ball boost/penalty
        ball_boost = 0.0
        if last_ball in ["4", "6"]:
            ball_boost = 0.15
        elif last_ball == "W":
            ball_boost = -0.20
        elif last_ball == "0":
            ball_boost = -0.05

        momentum = (base * wicket_factor) + ball_boost
        return round(max(0, min(1, momentum)), 4)

    def train(self, df: pd.DataFrame, target_col: str = "batting_team_won"):
        """
        Train XGBoost model on ball-by-ball historical data.
        """
        try:
            import xgboost as xgb
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score, accuracy_score

            logger.info(f"Training XGBoost on {len(df)} records...")

            # Extract features
            feature_rows = []
            for _, row in df.iterrows():
                state = row.to_dict()
                features = self.feature_eng.extract(state)
                feature_rows.append(features)

            X = np.vstack(feature_rows)
            y = df[target_col].values

            # Split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            # Scale
            self.scaler = StandardScaler()
            X_train = self.scaler.fit_transform(X_train)
            X_test = self.scaler.transform(X_test)

            # Train
            self.model = xgb.XGBClassifier(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=42,
                n_jobs=-1,
            )

            self.model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=50,
            )

            # Evaluate
            y_pred = self.model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, y_pred)
            acc = accuracy_score(y_test, (y_pred > 0.5).astype(int))
            logger.info(f"Model trained: AUC={auc:.4f}, Accuracy={acc:.4f}")

            self._model_loaded = True
            return {"auc": auc, "accuracy": acc}

        except ImportError:
            logger.error("XGBoost not installed. Run: pip install xgboost")
            raise

    def save(self, model_path: str, scaler_path: str):
        """Save trained model and scaler"""
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        with open(model_path, "wb") as f:
            pickle.dump(self.model, f)
        with open(scaler_path, "wb") as f:
            pickle.dump(self.scaler, f)
        logger.info(f"Model saved to {model_path}")
