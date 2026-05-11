"""Feature engineering for price-forecast models.

Two layouts are supported:

* ``build_wide_matrix`` — one row per forecast origin, target shape
  (n_origins, horizon). Used by Random Forest (multi-output) and the
  sklearn HGB fallback.
* ``build_long_matrix`` — one row per (forecast origin, horizon step).
  Used by LightGBM. The horizon step is itself a feature, so a single
  trained model handles all H steps in one fit — cuts cost by ~Hx
  vs. one model per horizon step.

Both layouts include lagged price (24 h + same-day-last-week), cyclical
calendar features + holiday flags for the target timestamp, and TSO
load/wind/solar forecasts for the target timestamp when available.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HOLIDAYS_AVAILABLE = False
try:
    import holidays
    HOLIDAYS_AVAILABLE = True
except ImportError:
    pass


ZONE_TO_COUNTRIES: Dict[str, List[str]] = {
    "DE_LU": ["DE", "LU"], "DE": ["DE"], "LU": ["LU"],
    "DK_1": ["DK"], "DK_2": ["DK"],
    "SE_1": ["SE"], "SE_2": ["SE"], "SE_3": ["SE"], "SE_4": ["SE"],
    "NO_1": ["NO"], "NO_2": ["NO"], "NO_3": ["NO"], "NO_4": ["NO"], "NO_5": ["NO"],
    "FI": ["FI"], "FR": ["FR"], "NL": ["NL"], "BE": ["BE"], "AT": ["AT"],
    "CH": ["CH"], "ES": ["ES"], "PT": ["PT"], "IT": ["IT"], "PL": ["PL"],
    "CZ": ["CZ"], "SK": ["SK"], "HU": ["HU"], "RO": ["RO"], "GR": ["GR"],
    "EE": ["EE"], "LV": ["LV"], "LT": ["LT"], "IE": ["IE"], "GB": ["GB"],
}


def _holiday_set(zone_code: str, years) -> set:
    if not HOLIDAYS_AVAILABLE:
        return set()
    countries = ZONE_TO_COUNTRIES.get(zone_code, [zone_code.split("_")[0]])
    out = set()
    for c in countries:
        try:
            out.update(holidays.country_holidays(c, years=list(years)).keys())
        except Exception:
            pass
    return out


def calendar_features(times: pd.DatetimeIndex, zone_code: str) -> pd.DataFrame:
    """Cyclical hour/dow + weekend/holiday flags for a target index."""
    df = pd.DataFrame(index=times)
    hour_norm = (times.hour + times.minute / 60.0) / 24.0
    dow_norm = times.dayofweek / 7.0
    df["hour_sin"] = np.sin(2 * np.pi * hour_norm)
    df["hour_cos"] = np.cos(2 * np.pi * hour_norm)
    df["dow_sin"] = np.sin(2 * np.pi * dow_norm)
    df["dow_cos"] = np.cos(2 * np.pi * dow_norm)
    df["is_weekend"] = (times.dayofweek >= 5).astype(float)

    years = sorted(set(times.year))
    hset = _holiday_set(zone_code, years + [min(years) - 1, max(years) + 1])
    dates = pd.Index(times.date)
    df["is_holiday"] = dates.isin(hset).astype(float)
    df["is_day_before_holiday"] = dates.map(
        lambda d: (d + pd.Timedelta(days=1)) in hset).astype(float)
    df["is_day_after_holiday"] = dates.map(
        lambda d: (d - pd.Timedelta(days=1)) in hset).astype(float)
    return df


def align_exogenous(exog: Optional[pd.DataFrame],
                    target_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Reindex exogenous regressors onto ``target_index``. Missing rows are
    interpolated and forward+backward-filled so the matrix has no NaNs.
    Returns an empty DataFrame indexed on target_index when exog is None."""
    if exog is None or exog.empty:
        return pd.DataFrame(index=target_index)
    if "time" in exog.columns:
        exog = exog.set_index("time")
    exog.index = pd.to_datetime(exog.index, utc=True)
    exog = exog[~exog.index.duplicated(keep="last")].sort_index()
    aligned = exog.reindex(target_index.union(exog.index)).interpolate("time")
    return aligned.reindex(target_index).ffill().bfill().fillna(0.0)


def build_wide_matrix(
    prices: pd.Series,
    zone_code: str,
    steps_per_day: int,
    horizon: int,
    exog: Optional[pd.DataFrame] = None,
    history_days: int = 180,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """One row per forecast origin, target shape (n, horizon).

    Calendar + exogenous features are taken at the forecast origin (not the
    horizon) to keep the matrix small. Use this for RF / sklearn HGB.
    """
    values = prices.values
    times = prices.index
    week = steps_per_day * 7
    limit_rows = steps_per_day * history_days
    start_idx = max(week, len(values) - limit_rows)
    end_idx = len(values) - horizon
    if end_idx <= start_idx:
        return np.empty((0, 0)), np.empty((0, 0)), []

    cal_all = calendar_features(times, zone_code)
    exog_all = align_exogenous(exog, times)
    exog_cols = list(exog_all.columns)

    n = end_idx - start_idx
    n_features = (2 * steps_per_day) + cal_all.shape[1] + len(exog_cols)
    X = np.empty((n, n_features))
    y = np.empty((n, horizon))
    for j, i in enumerate(range(start_idx, end_idx)):
        lag_day = values[i - steps_per_day:i]
        lag_week = values[i - week:i - week + steps_per_day]
        row = np.concatenate([lag_day, lag_week,
                              cal_all.iloc[i].to_numpy(),
                              exog_all.iloc[i].to_numpy() if exog_cols else np.empty(0)])
        X[j] = row
        y[j] = values[i:i + horizon]

    cal_names = list(cal_all.columns)
    feature_names = (
        [f"lag_day_{k}" for k in range(steps_per_day)]
        + [f"lag_week_{k}" for k in range(steps_per_day)]
        + [f"cal_{c}" for c in cal_names]
        + [f"exog_{c}" for c in exog_cols]
    )
    return X, y, feature_names


def build_wide_forecast_row(
    prices: pd.Series, zone_code: str, steps_per_day: int, horizon: int,
    exog: Optional[pd.DataFrame] = None,
) -> Optional[np.ndarray]:
    values = prices.values
    times = prices.index
    week = steps_per_day * 7
    if len(values) < week:
        return None
    cal_all = calendar_features(times[-1:], zone_code)
    exog_all = align_exogenous(exog, times[-1:])
    lag_day = values[-steps_per_day:]
    lag_week = values[-week:-week + steps_per_day]
    return np.concatenate([
        lag_day, lag_week,
        cal_all.iloc[0].to_numpy(),
        exog_all.iloc[0].to_numpy() if not exog_all.empty else np.empty(0),
    ])


def build_long_matrix(
    prices: pd.Series,
    zone_code: str,
    steps_per_day: int,
    horizon: int,
    exog: Optional[pd.DataFrame] = None,
    history_days: int = 180,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """One row per (forecast origin, horizon step). Target shape (n*horizon,).

    For each origin t and horizon offset h:
      features = [
        lag_day prices ending at t,         # 24h of recent history
        lag_week prices starting 7d ago at t,  # same 24h a week prior
        horizon step h (integer 0..H-1),
        calendar features at t+h,
        exog features at t+h,
      ]
      target = price at t+h

    One LightGBM fit on this matrix handles all 96 horizon steps. The model
    sees the horizon step as a feature plus the calendar/exog for that
    specific target timestamp.
    """
    values = prices.values
    times = prices.index
    week = steps_per_day * 7
    limit_rows = steps_per_day * history_days
    start_idx = max(week, len(values) - limit_rows)
    end_idx = len(values) - horizon
    if end_idx <= start_idx:
        return np.empty((0, 0)), np.empty(0), []

    cal_all = calendar_features(times, zone_code)
    exog_all = align_exogenous(exog, times)
    exog_cols = list(exog_all.columns)
    cal_arr = cal_all.to_numpy()
    exog_arr = exog_all.to_numpy() if exog_cols else None

    n_origins = end_idx - start_idx
    n_features = (2 * steps_per_day) + 1 + cal_arr.shape[1] + len(exog_cols)
    X = np.empty((n_origins * horizon, n_features))
    y = np.empty(n_origins * horizon)

    row = 0
    for i in range(start_idx, end_idx):
        lag_day = values[i - steps_per_day:i]
        lag_week = values[i - week:i - week + steps_per_day]
        base = np.concatenate([lag_day, lag_week])
        for h in range(horizon):
            tgt = i + h
            parts = [base, np.array([h])]
            parts.append(cal_arr[tgt])
            if exog_arr is not None:
                parts.append(exog_arr[tgt])
            X[row] = np.concatenate(parts)
            y[row] = values[tgt]
            row += 1

    cal_names = list(cal_all.columns)
    feature_names = (
        [f"lag_day_{k}" for k in range(steps_per_day)]
        + [f"lag_week_{k}" for k in range(steps_per_day)]
        + ["horizon_step"]
        + [f"cal_{c}" for c in cal_names]
        + [f"exog_{c}" for c in exog_cols]
    )
    return X, y, feature_names


def build_long_forecast_rows(
    prices: pd.Series, zone_code: str, steps_per_day: int, horizon: int,
    exog: Optional[pd.DataFrame] = None,
) -> Optional[np.ndarray]:
    """Return ``horizon`` rows of features for the forecast window."""
    values = prices.values
    times = prices.index
    week = steps_per_day * 7
    if len(values) < week:
        return None
    step = times[-1] - times[-2] if len(times) >= 2 else pd.Timedelta(hours=1)
    future_idx = pd.date_range(start=times[-1] + step, periods=horizon, freq=step)

    cal_future = calendar_features(future_idx, zone_code).to_numpy()
    exog_future = align_exogenous(exog, future_idx)
    exog_arr = exog_future.to_numpy() if not exog_future.empty else None

    lag_day = values[-steps_per_day:]
    lag_week = values[-week:-week + steps_per_day]
    base = np.concatenate([lag_day, lag_week])

    n_features = (2 * steps_per_day) + 1 + cal_future.shape[1] + (
        exog_arr.shape[1] if exog_arr is not None else 0)
    X = np.empty((horizon, n_features))
    for h in range(horizon):
        parts = [base, np.array([h]), cal_future[h]]
        if exog_arr is not None:
            parts.append(exog_arr[h])
        X[h] = np.concatenate(parts)
    return X
