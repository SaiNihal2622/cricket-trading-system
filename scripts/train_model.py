#!/usr/bin/env python3
"""
Train XGBoost cricket win probability model.

Usage:
    python train_model.py --data ipl_data.csv --output artifacts/
    python train_model.py --synthetic  # Use synthetic data for testing
"""
import argparse
import os
import sys
import logging
import pickle
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def prepare_training_data(df: pd.DataFrame) -> tuple:
    """
    Prepare features and labels from ball-by-ball data.
    Label: did batting team win? (1/0)
    """
    from ml_model.predictor import FeatureEngineering

    fe = FeatureEngineering()

    # Only use rows where outcome is known
    if "winner" not in df.columns:
        raise ValueError("DataFrame must have 'winner' column")

    rows = []
    labels = []
    skipped = 0

    for _, row in df.iterrows():
        state = {
            "total_runs": int(row.get("cum_runs", 0)),
            "total_wickets": int(row.get("cum_wickets", 0)),
            "overs": float(row.get("overs", 0)),
            "run_rate": float(row.get("run_rate", 0)),
            "innings": int(row.get("innings", 1)),
            "target": int(row.get("target", 0)),
            "batting_team": str(row.get("batting_team", "")),
            "powerplay_runs": int(row.get("powerplay_runs", 0)),
            "required_run_rate": float(row.get("required_run_rate", 0)),
            "venue_avg_score": float(row.get("venue_avg_score", 165)),
            "venue_pp_avg": float(row.get("venue_pp_avg", 52)),
            "batting_team_strength": float(row.get("batting_team_strength", 1.0)),
            "bowling_team_strength": float(row.get("bowling_team_strength", 1.0)),
            "boundary_rate": float(row.get("boundary_rate", 0.25)),
        }

        try:
            features = fe.extract(state)
            batting_team = str(row.get("batting_team", ""))
            winner = str(row.get("winner", ""))
            label = 1 if winner == batting_team else 0

            rows.append(features)
            labels.append(label)
        except Exception as e:
            skipped += 1

    if skipped > 0:
        logger.warning(f"Skipped {skipped} rows during feature extraction")

    X = np.vstack(rows)
    y = np.array(labels)
    logger.info(f"Prepared {len(X)} samples | {y.sum()} wins | {(1-y).sum()} losses")
    return X, y


def train(X, y, output_dir: str):
    """Train XGBoost and save artifacts"""
    try:
        import xgboost as xgb
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split, cross_val_score
        from sklearn.metrics import roc_auc_score, accuracy_score, classification_report

        os.makedirs(output_dir, exist_ok=True)

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train
        model = xgb.XGBClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.0,
            use_label_encoder=False,
            eval_metric="logloss",
            early_stopping_rounds=30,
            random_state=42,
            n_jobs=-1,
        )

        logger.info("Training XGBoost model...")
        model.fit(
            X_train_s, y_train,
            eval_set=[(X_test_s, y_test)],
            verbose=100,
        )

        # Evaluate
        y_prob = model.predict_proba(X_test_s)[:, 1]
        y_pred = (y_prob > 0.5).astype(int)

        auc = roc_auc_score(y_test, y_prob)
        acc = accuracy_score(y_test, y_pred)

        logger.info(f"\n{'='*50}")
        logger.info(f"Model Performance:")
        logger.info(f"  AUC-ROC: {auc:.4f}")
        logger.info(f"  Accuracy: {acc:.4f}")
        logger.info(f"\nClassification Report:")
        logger.info(classification_report(y_test, y_pred))

        # Feature importance
        from ml_model.predictor import FeatureEngineering
        feature_names = FeatureEngineering.FEATURE_NAMES
        importance_df = pd.DataFrame({
            "feature": feature_names[:len(model.feature_importances_)],
            "importance": model.feature_importances_
        }).sort_values("importance", ascending=False)
        logger.info(f"\nTop 10 Features:\n{importance_df.head(10).to_string()}")

        # Save
        model_path = os.path.join(output_dir, "xgboost_model.pkl")
        scaler_path = os.path.join(output_dir, "scaler.pkl")

        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        with open(scaler_path, "wb") as f:
            pickle.dump(scaler, f)

        logger.info(f"\nModel saved: {model_path}")
        logger.info(f"Scaler saved: {scaler_path}")

        return {"auc": auc, "accuracy": acc}

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Install with: pip install xgboost scikit-learn")
        raise


def main():
    parser = argparse.ArgumentParser(description="Train Cricket Win Probability Model")
    parser.add_argument("--data", type=str, help="Path to IPL CSV data file")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic data")
    parser.add_argument("--output", type=str, default="artifacts/", help="Output directory")
    args = parser.parse_args()

    if args.synthetic:
        logger.info("Generating synthetic IPL data...")
        from backtesting.backtester import IPLDataLoader
        loader = IPLDataLoader()
        df = loader.generate_synthetic_data(n_matches=500)
        logger.info(f"Generated {len(df)} ball records")
    elif args.data:
        logger.info(f"Loading data from {args.data}...")
        from backtesting.backtester import IPLDataLoader
        loader = IPLDataLoader()
        df = loader.load_csv(args.data)
    else:
        logger.error("Provide --data or --synthetic")
        sys.exit(1)

    logger.info("Preparing features...")
    X, y = prepare_training_data(df)

    logger.info("Training model...")
    metrics = train(X, y, args.output)

    logger.info(f"\n✅ Training complete!")
    logger.info(f"  AUC: {metrics['auc']:.4f}")
    logger.info(f"  Accuracy: {metrics['accuracy']:.4f}")


if __name__ == "__main__":
    main()
