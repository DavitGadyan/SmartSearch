"""LightGBM LambdaRank wrapper: training, prediction, per-feature contributions, (de)serialisation."""

from pathlib import Path

import lightgbm as lgb
import numpy as np

from app.ml.ranking.features import FEATURE_NAMES

DEFAULT_PARAMS = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "eval_at": [10],
    "label_gain": [0, 1, 3],  # grades 0/1/2 → gains; Exact matches are worth 3x a Partial
    "lambdarank_truncation_level": 20,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 10.0,
    "verbosity": -1,
    "seed": 42,
    "num_threads": 0,
}


class Ranker:
    def __init__(self, booster: lgb.Booster, version: str) -> None:
        self.booster = booster
        self.version = version

    @classmethod
    def train(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        groups_val: np.ndarray,
        version: str,
        params: dict | None = None,
        num_rounds: int = 800,
    ) -> tuple["Ranker", dict]:
        p = {**DEFAULT_PARAMS, **(params or {})}
        dtrain = lgb.Dataset(X, y, group=groups, feature_name=FEATURE_NAMES, free_raw_data=False)
        dval = lgb.Dataset(X_val, y_val, group=groups_val, reference=dtrain, free_raw_data=False)
        evals: dict = {}
        booster = lgb.train(
            p,
            dtrain,
            num_boost_round=num_rounds,
            valid_sets=[dval],
            valid_names=["val"],
            callbacks=[lgb.early_stopping(100, verbose=False), lgb.record_evaluation(evals)],
        )
        history = evals["val"]["ndcg@10"]
        info = {
            "best_iteration": int(booster.best_iteration),
            "val_ndcg10_best": float(max(history)),
            "val_ndcg10_history": [float(v) for v in history],
        }
        return cls(booster, version), info

    @classmethod
    def fit(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        version: str = "fit",
        params: dict | None = None,
        num_rounds: int = 150,
    ) -> "Ranker":
        """Train for a fixed number of rounds without a validation set (used by cross-validation)."""
        p = {**DEFAULT_PARAMS, **(params or {})}
        dtrain = lgb.Dataset(X, y, group=groups, feature_name=FEATURE_NAMES, free_raw_data=False)
        return cls(lgb.train(p, dtrain, num_boost_round=num_rounds), version)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if len(X) == 0:
            return np.empty(0, np.float32)
        return self.booster.predict(X, num_iteration=self.booster.best_iteration or None).astype(np.float32)

    def contributions(self, X: np.ndarray) -> np.ndarray:
        """SHAP-style per-feature contributions, shape (n, F+1); last column is the bias."""
        return np.asarray(
            self.booster.predict(X, pred_contrib=True, num_iteration=self.booster.best_iteration or None)
        )

    def feature_importance(self) -> dict[str, float]:
        gain = self.booster.feature_importance(importance_type="gain")
        total = float(gain.sum()) or 1.0
        return {
            n: round(float(g) / total, 4)
            for n, g in sorted(zip(FEATURE_NAMES, gain, strict=True), key=lambda t: -t[1])
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(path), num_iteration=self.booster.best_iteration or None)
        return path

    @classmethod
    def load(cls, path: Path, version: str) -> "Ranker":
        return cls(lgb.Booster(model_file=str(path)), version)
