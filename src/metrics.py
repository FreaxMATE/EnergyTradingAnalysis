"""Forecast accuracy metrics.

All functions accept array-like inputs and ignore NaN pairs (any row where
either y_true or y_pred is NaN is dropped). Returns float values; returns
NaN when there are not enough valid samples.
"""

from typing import Dict, Optional
import numpy as np


def _align(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    return y_true[mask], y_pred[mask]


def mae(y_true, y_pred) -> float:
    y_true, y_pred = _align(y_true, y_pred)
    if y_true.size == 0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    y_true, y_pred = _align(y_true, y_pred)
    if y_true.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def smape(y_true, y_pred) -> float:
    """Symmetric MAPE in percent. Robust to zero/negative values, which is
    important for electricity prices that frequently go to or below 0."""
    y_true, y_pred = _align(y_true, y_pred)
    if y_true.size == 0:
        return float("nan")
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    denom = np.where(denom == 0, 1.0, denom)
    return float(np.mean(np.abs(y_true - y_pred) / denom) * 100.0)


def bias(y_true, y_pred) -> float:
    """Mean signed error (pred - actual). Positive means over-forecast."""
    y_true, y_pred = _align(y_true, y_pred)
    if y_true.size == 0:
        return float("nan")
    return float(np.mean(y_pred - y_true))


def mase(y_true, y_pred, y_train, seasonality: int = 24) -> float:
    """Mean Absolute Scaled Error vs a seasonal naive forecast on the
    training set. <1.0 means we beat seasonal-naive on average."""
    y_true, y_pred = _align(y_true, y_pred)
    y_train = np.asarray(y_train, dtype=float)
    y_train = y_train[np.isfinite(y_train)]
    if y_true.size == 0 or y_train.size <= seasonality:
        return float("nan")
    scale = float(np.mean(np.abs(y_train[seasonality:] - y_train[:-seasonality])))
    if scale == 0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)) / scale)


def all_metrics(
    y_true,
    y_pred,
    y_train: Optional[np.ndarray] = None,
    seasonality: int = 24,
) -> Dict[str, float]:
    out = {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "smape": smape(y_true, y_pred),
        "bias": bias(y_true, y_pred),
        "n": int(_align(y_true, y_pred)[0].size),
    }
    if y_train is not None:
        out["mase"] = mase(y_true, y_pred, y_train, seasonality)
    return out
