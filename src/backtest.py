"""Walk-forward backtesting for day-ahead price forecasts.

For each backtest day d, we use only data available before d at 00:00 UTC
to fit each model, then forecast d's 24 h and score against actuals. ML
models are re-fit every ``refit_every_days`` folds (default weekly) to
keep runtime tractable on 15-min data.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

LGB_AVAILABLE = False
try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    pass

ML_AVAILABLE = False
try:
    from sklearn.ensemble import RandomForestRegressor
    ML_AVAILABLE = True
except ImportError:
    pass

from logger import setup_logger
from metrics import all_metrics
from analysis import prepare_series, load_best_params, DEFAULT_PARAMS
from features import (
    build_wide_matrix, build_wide_forecast_row,
    build_long_matrix, build_long_forecast_rows,
)

logger = setup_logger(__name__)


def _seasonal_naive(prices: np.ndarray, horizon: int, spd: int) -> Optional[np.ndarray]:
    week = spd * 7
    if len(prices) < week:
        return None
    return prices[-week:-week + horizon]


def _holt_winters(prices: pd.Series, horizon: int, spd: int) -> Optional[np.ndarray]:
    try:
        window = min(len(prices), spd * 60)
        subset = prices.iloc[-window:]
        model = ExponentialSmoothing(
            subset, seasonal_periods=spd, trend="add", seasonal="add",
            initialization_method="estimated",
        ).fit()
        return model.forecast(horizon).values
    except Exception as e:
        logger.debug(f"HW fit failed at backtest step: {e}")
        return None


def _fit_lightgbm(X: np.ndarray, y: np.ndarray, params: dict):
    """One global LightGBM with horizon-step as a feature (long-format)."""
    m = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=params["n_estimators"],
        learning_rate=params["learning_rate"],
        num_leaves=params["num_leaves"],
        min_data_in_leaf=params["min_data_in_leaf"],
        feature_fraction=params["feature_fraction"],
        verbose=-1, n_jobs=-1, random_state=42,
    )
    m.fit(X, y)
    return m


def walk_forward(df: pd.DataFrame, backtest_days: int = 14,
                 horizon_hours: int = 24, history_days: int = 60,
                 refit_every_days: int = 7,
                 zone_code: str = "",
                 exog: Optional[pd.DataFrame] = None,
                 ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run a daily walk-forward backtest.

    ML models are re-fit every `refit_every_days` folds (default weekly) to
    keep runtime tractable. HW and the seasonal-naive baseline are refit
    every fold (cheap).

    Returns:
        predictions: long-format DataFrame [time, model, predicted, actual]
        metrics:     DataFrame indexed by model (mae/rmse/smape/bias/mase)
    """
    series, freq, spd = prepare_series(df)
    horizon = horizon_hours * (spd // 24)
    step = spd

    if len(series) < spd * (7 + backtest_days + 1):
        logger.warning("Not enough history for backtest")
        return pd.DataFrame(), pd.DataFrame()

    end = len(series) - horizon
    start = max(spd * 14, end - backtest_days * step)
    cuts = list(range(start, end + 1, step))
    params = load_best_params()
    lgb_params = params.get("lgb", DEFAULT_PARAMS["lgb"])
    rf_params = params.get("rf", DEFAULT_PARAMS["rf"])

    rows: List[dict] = []
    n_models = 2 + (1 if LGB_AVAILABLE else 0) + (1 if ML_AVAILABLE else 0)
    logger.info(f"Backtest: {len(cuts)} folds × {n_models} models at {freq}, "
                f"ML refit every {refit_every_days}d (zone={zone_code or 'unknown'})")

    lgb_model = None
    rf_model = None
    last_ml_refit = -10**9

    for k, cut in enumerate(cuts):
        train = series.iloc[:cut]
        actual = series.iloc[cut:cut + horizon]
        if len(actual) < horizon:
            continue

        forecasts: Dict[str, Optional[np.ndarray]] = {
            "naive": _seasonal_naive(train.values, horizon, spd),
            "hw": _holt_winters(train, horizon, spd),
        }

        need_refit = (k - last_ml_refit) >= refit_every_days
        if need_refit:
            if LGB_AVAILABLE:
                X_lng, y_lng, _ = build_long_matrix(
                    train, zone_code, spd, horizon,
                    exog=exog, history_days=history_days)
                if X_lng.size > 0:
                    try:
                        lgb_model = _fit_lightgbm(X_lng, y_lng, lgb_params)
                    except Exception as e:
                        logger.warning(f"LGB refit failed: {e}")
            if ML_AVAILABLE:
                X_w, y_w, _ = build_wide_matrix(
                    train, zone_code, spd, horizon,
                    exog=exog, history_days=history_days)
                if X_w.size > 0:
                    try:
                        rf_model = RandomForestRegressor(
                            n_estimators=rf_params["n_estimators"],
                            max_depth=rf_params["max_depth"],
                            max_samples=rf_params["max_samples"],
                            min_samples_leaf=rf_params["min_samples_leaf"],
                            n_jobs=-1, random_state=42,
                        )
                        rf_model.fit(X_w, y_w)
                    except Exception as e:
                        logger.warning(f"RF refit failed: {e}")
            last_ml_refit = k

        if lgb_model is not None and LGB_AVAILABLE:
            X_pred_lng = build_long_forecast_rows(train, zone_code, spd, horizon, exog=exog)
            if X_pred_lng is not None:
                try:
                    forecasts["gb"] = lgb_model.predict(X_pred_lng)
                except Exception as e:
                    logger.debug(f"LGB predict failed: {e}")
        if rf_model is not None:
            x_pred_w = build_wide_forecast_row(train, zone_code, spd, horizon, exog=exog)
            if x_pred_w is not None:
                try:
                    forecasts["rf"] = rf_model.predict(x_pred_w.reshape(1, -1))[0]
                except Exception as e:
                    logger.debug(f"RF predict failed: {e}")

        for model_name, preds in forecasts.items():
            if preds is None or len(preds) != horizon:
                continue
            for t, p, a in zip(actual.index, preds, actual.values):
                rows.append({"time": t, "model": model_name,
                             "predicted": float(p), "actual": float(a)})

        if (k + 1) % 5 == 0:
            logger.info(f"  fold {k + 1}/{len(cuts)} done")

    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    predictions = pd.DataFrame(rows)
    train_for_mase = series.iloc[:start].values
    metric_rows = []
    for model_name, sub in predictions.groupby("model"):
        m = all_metrics(sub["actual"].values, sub["predicted"].values,
                        y_train=train_for_mase, seasonality=spd)
        m["model"] = model_name
        metric_rows.append(m)
    metrics_df = (pd.DataFrame(metric_rows)
                  .set_index("model")
                  .sort_values("mae"))
    return predictions, metrics_df
