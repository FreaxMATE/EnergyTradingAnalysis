"""Time-series analyzers: moving average + day-ahead price forecasts.

Forecast suite (all at native market resolution — 15-min once a zone has
switched, hourly before that):

* ``forecast_naive``     seasonal naive baseline (lag = 1 week)
* ``forecast_hw``        Holt-Winters point forecast
* ``forecast_hw_lo/hi``  Holt-Winters 80% conformal prediction interval
* ``forecast_gb``        LightGBM point forecast (quantile=0.5)
* ``forecast_gb_lo/hi``  LightGBM 80% prediction interval (quantile 0.1/0.9)
* ``forecast_rf``        Random Forest point forecast

The ML pipeline ingests lag features, cyclical calendar features, holiday
flags, and TSO load + wind/solar forecasts when available — see
``features.build_feature_matrix``. Hyperparameters can be overridden by
writing ``data/best_params.json`` (see ``tune.py``).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Tuple
import json

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
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
    ML_AVAILABLE = True
except ImportError:
    import sys
    print("Warning: scikit-learn not installed. ML forecasts disabled.", file=sys.stderr)

from logger import setup_logger
from config import START_OF_15_MIN_SPOT_PRICE, DATA_DIR
from features import (
    build_wide_matrix, build_wide_forecast_row,
    build_long_matrix, build_long_forecast_rows,
)

logger = setup_logger(__name__)


# -- Hyperparameter defaults (overridable via data/best_params.json) ----------

DEFAULT_PARAMS = {
    "lgb": {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31,
            "min_data_in_leaf": 20, "feature_fraction": 0.9},
    "rf":  {"n_estimators": 50, "max_depth": 12, "max_samples": 0.3,
            "min_samples_leaf": 4},
    "hgb": {"max_iter": 100, "max_depth": 5, "learning_rate": 0.1},
}


def load_best_params() -> Dict[str, Dict]:
    """Return DEFAULT_PARAMS overridden by data/best_params.json if present."""
    fp = Path(DATA_DIR) / "best_params.json"
    params = {k: dict(v) for k, v in DEFAULT_PARAMS.items()}
    if fp.exists():
        try:
            tuned = json.loads(fp.read_text())
            for model, override in tuned.items():
                params.setdefault(model, {}).update(override)
            logger.info(f"Loaded tuned params from {fp}")
        except Exception as e:
            logger.warning(f"best_params.json present but unreadable: {e}")
    return params


# -- Series prep --------------------------------------------------------------

def detect_freq(times: pd.DatetimeIndex) -> str:
    """Return '15min' or 'h' from the median spacing of the most recent week."""
    if len(times) < 10:
        return "h"
    recent = times[-672:] if len(times) >= 672 else times
    diffs = pd.Series(recent).diff().dropna()
    if diffs.empty:
        return "h"
    return "15min" if diffs.median() <= pd.Timedelta(minutes=20) else "h"


def prepare_series(df: pd.DataFrame) -> Tuple[pd.Series, str, int]:
    """Return (price_series, freq, steps_per_day) at native market resolution."""
    df = df.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    freq = detect_freq(df.index)
    if freq == "15min":
        cutoff = pd.Timestamp(START_OF_15_MIN_SPOT_PRICE).tz_convert("UTC")
        df = df[df.index >= cutoff]

    series = df["price"].asfreq(freq).interpolate("time", limit=8).dropna()
    steps_per_day = 96 if freq == "15min" else 24
    return series, freq, steps_per_day


# -- Analyzers ----------------------------------------------------------------

class Analyzer(ABC):
    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame: ...


class BasicStatsAnalyzer(Analyzer):
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.describe()


class MovingAverageAnalyzer(Analyzer):
    def __init__(self, window: str = "24h", min_periods: int = 1, center: bool = True):
        self.window = window
        self.min_periods = min_periods
        self.center = center

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info(f"Moving average (window={self.window})")
        if df.empty:
            return pd.DataFrame()

        target_col = "price"
        if target_col not in df.columns:
            cols = [c for c in df.columns if c != "time"]
            if len(cols) != 1:
                raise ValueError("'price' column not found")
            target_col = cols[0]

        d = df.copy()
        if "time" in d.columns:
            d["time"] = pd.to_datetime(d["time"], utc=True)
            d = d.set_index("time")
        d["ma"] = d[target_col].rolling(self.window, min_periods=self.min_periods,
                                        center=self.center).mean()
        return d.reset_index()


class CombinedForecastAnalyzer(Analyzer):
    """Naive + Holt-Winters + LightGBM (with quantile bands) + Random Forest."""

    def __init__(self, horizon_hours: int = 24, history_days: int = 180,
                 zone_code: Optional[str] = None,
                 exog: Optional[pd.DataFrame] = None,
                 conformal_interval: float = 0.8):
        self.horizon_hours = horizon_hours
        self.history_days = history_days
        self.zone_code = zone_code or ""
        self.exog = exog
        self.conformal_interval = conformal_interval
        self._params = load_best_params()

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        series, freq, spd = prepare_series(df)
        horizon = self.horizon_hours * (spd // 24)
        logger.info(f"Forecast at {freq} resolution, horizon={horizon} steps "
                    f"(zone={self.zone_code or 'unknown'})")

        if len(series) < spd * 14:
            logger.warning("Not enough history for forecasting")
            return pd.DataFrame()

        step = series.index[-1] - series.index[-2]
        next_time = series.index[-1] + step
        future_index = pd.date_range(start=next_time, periods=horizon, freq=step)

        out = pd.DataFrame({"time": future_index})

        # Seasonal naive
        naive = self._seasonal_naive(series, horizon, spd)
        if naive is not None:
            out["forecast_naive"] = naive

        # Holt-Winters with conformal interval from residuals on a holdout
        hw_point, hw_lo, hw_hi = self._holt_winters(series, horizon, spd)
        if hw_point is not None:
            out["forecast_hw"] = hw_point
            if hw_lo is not None:
                out["forecast_hw_lo"] = hw_lo
                out["forecast_hw_hi"] = hw_hi

        # LightGBM (quantile 0.5 + 0.1/0.9)
        if LGB_AVAILABLE:
            gb_p50, gb_p10, gb_p90 = self._lightgbm_quantile(series, horizon, spd)
            if gb_p50 is not None:
                out["forecast_gb"] = gb_p50
                out["forecast_gb_lo"] = gb_p10
                out["forecast_gb_hi"] = gb_p90
        elif ML_AVAILABLE:
            gb_p50 = self._sklearn_gb(series, horizon, spd)
            if gb_p50 is not None:
                out["forecast_gb"] = gb_p50

        if ML_AVAILABLE:
            rf = self._random_forest(series, horizon, spd)
            if rf is not None:
                out["forecast_rf"] = rf

        return out if len(out.columns) > 1 else pd.DataFrame()

    # -- Models ---------------------------------------------------------------

    def _seasonal_naive(self, series: pd.Series, horizon: int, spd: int):
        values = series.values
        week = spd * 7
        if len(values) < week:
            return None
        return values[-week:-week + horizon] if horizon <= week else None

    def _holt_winters(self, series: pd.Series, horizon: int, spd: int):
        """Returns (point, lower, upper). Bounds via split conformal on the
        last `horizon` observations: hold out, fit on the rest, take the
        alpha-quantile of |residual| as the half-width."""
        try:
            window = min(len(series), spd * 60)
            cal = series.iloc[-(window + horizon):-horizon] if len(series) > window + horizon else series.iloc[:-horizon]
            cal_target = series.iloc[-horizon:]
            # Calibration fit
            try:
                cal_model = ExponentialSmoothing(
                    cal, seasonal_periods=spd, trend="add", seasonal="add",
                    initialization_method="estimated",
                ).fit()
                cal_pred = cal_model.forecast(horizon).values
                resid = np.abs(cal_target.values - cal_pred)
                alpha = self.conformal_interval
                half_width = float(np.quantile(resid, alpha))
            except Exception:
                half_width = None

            # Full-history fit for the real forecast
            subset = series.iloc[-window:]
            model = ExponentialSmoothing(
                subset, seasonal_periods=spd, trend="add", seasonal="add",
                initialization_method="estimated",
            ).fit()
            point = model.forecast(horizon).values
            if half_width is not None:
                return point, point - half_width, point + half_width
            return point, None, None
        except Exception as e:
            logger.warning(f"Holt-Winters failed: {e}")
            return None, None, None

    def _lightgbm_quantile(self, series: pd.Series, horizon: int, spd: int):
        """Train one global LightGBM per quantile (horizon step is a feature).
        Three fits total instead of 3 * horizon. Returns (p50, p10, p90)."""
        try:
            X, y, _ = build_long_matrix(
                series, self.zone_code, spd, horizon,
                exog=self.exog, history_days=self.history_days)
            if X.size == 0:
                return None, None, None
            X_pred = build_long_forecast_rows(series, self.zone_code, spd,
                                               horizon, exog=self.exog)
            if X_pred is None:
                return None, None, None

            lgb_params = self._params.get("lgb", DEFAULT_PARAMS["lgb"])
            preds = {}
            for q in (0.1, 0.5, 0.9):
                model = lgb.LGBMRegressor(
                    objective="quantile", alpha=q,
                    n_estimators=lgb_params["n_estimators"],
                    learning_rate=lgb_params["learning_rate"],
                    num_leaves=lgb_params["num_leaves"],
                    min_data_in_leaf=lgb_params["min_data_in_leaf"],
                    feature_fraction=lgb_params["feature_fraction"],
                    verbose=-1, n_jobs=-1, random_state=42,
                )
                model.fit(X, y)
                preds[q] = model.predict(X_pred)
            lo = np.minimum(preds[0.1], preds[0.5])
            hi = np.maximum(preds[0.9], preds[0.5])
            return preds[0.5], lo, hi
        except Exception as e:
            logger.warning(f"LightGBM failed: {e}")
            return None, None, None

    def _sklearn_gb(self, series: pd.Series, horizon: int, spd: int):
        """Fallback when lightgbm isn't installed."""
        try:
            X, y, _ = build_wide_matrix(
                series, self.zone_code, spd, horizon,
                exog=self.exog, history_days=self.history_days)
            if X.size == 0:
                return None
            x_pred = build_wide_forecast_row(series, self.zone_code, spd,
                                             horizon, exog=self.exog)
            if x_pred is None:
                return None
            hgb = self._params.get("hgb", DEFAULT_PARAMS["hgb"])
            model = MultiOutputRegressor(HistGradientBoostingRegressor(
                max_iter=hgb["max_iter"], max_depth=hgb["max_depth"],
                learning_rate=hgb["learning_rate"], random_state=42))
            model.fit(X, y)
            return model.predict(x_pred.reshape(1, -1))[0]
        except Exception as e:
            logger.warning(f"sklearn GB fallback failed: {e}")
            return None

    def _random_forest(self, series: pd.Series, horizon: int, spd: int):
        try:
            X, y, _ = build_wide_matrix(
                series, self.zone_code, spd, horizon,
                exog=self.exog, history_days=self.history_days)
            if X.size == 0:
                return None
            x_pred = build_wide_forecast_row(series, self.zone_code, spd,
                                             horizon, exog=self.exog)
            if x_pred is None:
                return None
            rf = self._params.get("rf", DEFAULT_PARAMS["rf"])
            model = RandomForestRegressor(
                n_estimators=rf["n_estimators"], max_depth=rf["max_depth"],
                max_samples=rf["max_samples"], min_samples_leaf=rf["min_samples_leaf"],
                n_jobs=-1, random_state=42)
            model.fit(X, y)
            return model.predict(x_pred.reshape(1, -1))[0]
        except Exception as e:
            logger.warning(f"Random Forest failed: {e}")
            return None


class AnalysisRunner:
    def __init__(self):
        self.analyzers = []

    def add_analyzer(self, analyzer: Analyzer):
        self.analyzers.append(analyzer)

    def run_all(self, df: pd.DataFrame) -> dict:
        results = {}
        for a in self.analyzers:
            try:
                results[a.__class__.__name__] = a.analyze(df)
            except Exception as e:
                logger.error(f"Error in {a.__class__.__name__}: {e}")
        return results
