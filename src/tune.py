"""Offline hyperparameter tuning for LightGBM + Random Forest forecasters.

Run manually when you want updated params; the daily cron does NOT call this.
The output is ``data/best_params.json``, which ``analysis.load_best_params``
merges with the in-code defaults at import time.

Strategy: small randomized grid over a single representative zone's recent
history, scored with a 5-fold expanding-window TimeSeriesSplit. We tune on
one zone (default: the largest one) and apply the result globally — per-zone
tuning would multiply runtime and rarely changes the rank-order of good
hyperparameters for this kind of feature set.

Usage:
    python src/tune.py                  # tune LightGBM + RF on default zone
    python src/tune.py --zone DE_LU     # explicit zone
    python src/tune.py --n-trials 30    # more samples (default 12)
    python src/tune.py --quick          # 3 trials, for smoke-testing
"""

import argparse
import json
import sys
import time
from itertools import product
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

LGB_AVAILABLE = False
try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    pass

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit

from logger import setup_logger
from config import DATA_DIR
from datamanager import DataManager
from analysis import prepare_series
from features import build_long_matrix, build_wide_matrix
from metrics import mae

logger = setup_logger(__name__)


LGB_GRID = {
    "n_estimators": [100, 200, 400],
    "learning_rate": [0.03, 0.05, 0.1],
    "num_leaves": [15, 31, 63],
    "min_data_in_leaf": [10, 20, 40],
    "feature_fraction": [0.7, 0.9, 1.0],
}

RF_GRID = {
    "n_estimators": [30, 50, 100],
    "max_depth": [8, 12, 20],
    "max_samples": [0.2, 0.3, 0.5],
    "min_samples_leaf": [2, 4, 8],
}


def _sample_grid(grid: Dict[str, List], n: int, rng: np.random.Generator) -> List[Dict]:
    """Random sample of `n` configs from `grid`."""
    keys = list(grid.keys())
    cartesian = list(product(*[grid[k] for k in keys]))
    rng.shuffle(cartesian)
    sampled = cartesian[: min(n, len(cartesian))]
    return [dict(zip(keys, combo)) for combo in sampled]


def _cv_score_lgb(X: np.ndarray, y: np.ndarray, params: Dict, splits: int = 5) -> float:
    """Mean CV MAE for a LightGBM long-format model."""
    tscv = TimeSeriesSplit(n_splits=splits)
    errs = []
    for tr_idx, va_idx in tscv.split(X):
        model = lgb.LGBMRegressor(
            objective="regression",
            verbose=-1, n_jobs=-1, random_state=42, **params,
        )
        model.fit(X[tr_idx], y[tr_idx])
        pred = model.predict(X[va_idx])
        errs.append(mae(y[va_idx], pred))
    return float(np.mean(errs))


def _cv_score_rf(X: np.ndarray, y: np.ndarray, params: Dict, splits: int = 5) -> float:
    """Mean CV MAE for a Random Forest wide-format model."""
    tscv = TimeSeriesSplit(n_splits=splits)
    errs = []
    for tr_idx, va_idx in tscv.split(X):
        model = RandomForestRegressor(
            n_jobs=-1, random_state=42, **params,
        )
        model.fit(X[tr_idx], y[tr_idx])
        pred = model.predict(X[va_idx])
        # y here is (n, horizon); flatten for MAE
        errs.append(mae(np.asarray(y[va_idx]).ravel(), np.asarray(pred).ravel()))
    return float(np.mean(errs))


def tune(zone_code: str, n_trials: int = 12, history_days: int = 90) -> Dict[str, Dict]:
    """Tune LightGBM (long-format) and RF (wide-format) for one zone."""
    logger.info(f"Tuning on zone={zone_code}, n_trials={n_trials}, history={history_days}d")
    dm = DataManager(read_mode="data")
    if zone_code not in dm.data:
        raise ValueError(f"No data for zone {zone_code}")
    df = dm.data[zone_code]
    exog = dm.exogenous.get(zone_code)
    series, freq, spd = prepare_series(df)
    horizon = 24 * (spd // 24)
    logger.info(f"Series @ {freq}, spd={spd}, horizon={horizon}")

    rng = np.random.default_rng(42)
    out: Dict[str, Dict] = {}

    if LGB_AVAILABLE:
        X_l, y_l, _ = build_long_matrix(series, zone_code, spd, horizon,
                                         exog=exog, history_days=history_days)
        if X_l.size > 0:
            best = (float("inf"), None)
            for i, params in enumerate(_sample_grid(LGB_GRID, n_trials, rng)):
                t = time.time()
                score = _cv_score_lgb(X_l, y_l, params)
                logger.info(f"  LGB trial {i + 1}: mae={score:.3f} "
                            f"({time.time() - t:.1f}s) {params}")
                if score < best[0]:
                    best = (score, params)
            if best[1] is not None:
                out["lgb"] = best[1]
                logger.info(f"Best LGB: mae={best[0]:.3f} {best[1]}")
        else:
            logger.warning("Not enough data for LGB tuning")

    X_w, y_w, _ = build_wide_matrix(series, zone_code, spd, horizon,
                                     exog=exog, history_days=history_days)
    if X_w.size > 0:
        best = (float("inf"), None)
        for i, params in enumerate(_sample_grid(RF_GRID, n_trials, rng)):
            t = time.time()
            score = _cv_score_rf(X_w, y_w, params)
            logger.info(f"  RF  trial {i + 1}: mae={score:.3f} "
                        f"({time.time() - t:.1f}s) {params}")
            if score < best[0]:
                best = (score, params)
        if best[1] is not None:
            out["rf"] = best[1]
            logger.info(f"Best RF:  mae={best[0]:.3f} {best[1]}")
    else:
        logger.warning("Not enough data for RF tuning")

    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zone", default="DE_LU",
                   help="Bidding zone to tune on (default: DE_LU)")
    p.add_argument("--n-trials", type=int, default=12,
                   help="Random-search trials per model (default: 12)")
    p.add_argument("--history-days", type=int, default=90,
                   help="Training history per CV fold (default: 90)")
    p.add_argument("--quick", action="store_true",
                   help="3 trials for a smoke test")
    p.add_argument("--out", default=str(Path(DATA_DIR) / "best_params.json"),
                   help="Output JSON path")
    args = p.parse_args()

    n_trials = 3 if args.quick else args.n_trials
    result = tune(args.zone, n_trials=n_trials, history_days=args.history_days)
    if not result:
        logger.error("No tuning results to save")
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    logger.info(f"Saved tuned params to {out}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
