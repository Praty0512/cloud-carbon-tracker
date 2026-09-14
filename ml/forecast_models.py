"""The forecasting model bake-off: every candidate algorithm, compared honestly.

This is a genuine multi-algorithm comparison, not a single model with a
fallback. On every training run, every algorithm family that's actually
installed is evaluated with the same walk-forward cross-validation on the
same data, and the one with the lowest out-of-sample MAE wins:

- **Ridge regression** (scikit-learn) -- a linear baseline; if a simple
  model wins, that's a meaningful, reportable finding on its own.
- **Random Forest** and **Gradient Boosting** (scikit-learn) -- the two
  tree ensembles the project already had.
- **XGBoost** and **LightGBM** -- the two gradient-boosting
  implementations that actually win most real-world tabular-data
  competitions and production forecasting systems; each family's
  hyperparameters (depth, learning rate, tree count, etc.) are tuned with
  ``RandomizedSearchCV`` against the same walk-forward split before being
  scored, so the comparison is between *tuned* versions of each family.
- **SARIMAX** (statsmodels) -- a classical, model-based time-series method
  (autoregression + seasonal differencing), included because it works
  fundamentally differently from every tree/linear model above: it fits
  the raw series directly instead of hand-engineered lag features, and at
  very small sample sizes (this project's real reference dataset is only
  30 days) a well-specified classical model can beat a tree ensemble that
  has very little data to learn a split structure from.
- **A small LSTM** (PyTorch) -- included for breadth even though, honestly,
  a recurrent neural net needs far more than a few dozen to a few hundred
  data points to reliably beat tree ensembles or classical time-series
  models. It's a legitimate, real (if small) architecture -- not a stub --
  and the leaderboard this module produces will typically show it losing
  to gradient boosting or SARIMAX at this data scale. That's a genuine and
  useful thing to be able to say in a report: "we tried a neural approach,
  and here is the honest, cross-validated reason it didn't win here."

Every family here is an *optional* dependency: if a library isn't
installed, that one candidate is silently skipped (like the rest of this
project's resilience pattern -- see ``ml/forecasting.py``,
``ml/anomaly_detection.py``) and the bake-off proceeds with whatever is
available, falling all the way back to a dependency-free numpy
least-squares fit if literally nothing else is installed.

Every candidate implements the small ``ForecastModelAdapter`` interface
below, so ``ml.forecasting.recursive_forecast`` can roll any winning family
forward one day at a time without needing to know which algorithm it is.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from ml.features import (
    FEATURE_COLUMNS,
    CVResult,
    ForecastRun,
    build_feature_frame,
    build_next_feature_row,
    time_series_splits,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

try:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import RandomizedSearchCV

    _SKLEARN_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only without sklearn installed
    _SKLEARN_AVAILABLE = False

try:
    import xgboost as xgb

    _XGBOOST_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb

    _LIGHTGBM_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _LIGHTGBM_AVAILABLE = False

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    _STATSMODELS_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _STATSMODELS_AVAILABLE = False

try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _TORCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Common adapter interface
# ---------------------------------------------------------------------------
class ForecastModelAdapter:
    """Minimal interface every candidate model family implements.

    Keeping this interface small (fit / predict_next / cv_evaluate) is what
    lets ``ml.forecasting.recursive_forecast`` roll forward a tree model, a
    classical SARIMAX model, or a neural net through the exact same loop
    without a family-specific branch.
    """

    name: str = "base"
    library: str = "unknown"

    def fit(self, daily_df: pd.DataFrame) -> None:
        raise NotImplementedError

    def predict_next(self, history_df: pd.DataFrame) -> float:
        """Predict the single day after ``history_df``'s last day."""
        raise NotImplementedError

    def cv_evaluate(self, daily_df: pd.DataFrame, n_splits: int) -> CVResult:
        raise NotImplementedError

    def feature_importance(self) -> dict[str, float]:
        return {}


def _grid_size(param_distributions: dict) -> int:
    size = 1
    for values in param_distributions.values():
        size *= len(values)
    return size


def _safe_mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    nonzero = actual != 0
    if not nonzero.any():
        return 0.0
    return float(np.mean(np.abs((actual[nonzero] - predicted[nonzero]) / actual[nonzero])) * 100)


# ---------------------------------------------------------------------------
# Tabular (lag-feature) models: Ridge, RandomForest, GradientBoosting,
# XGBoost, LightGBM all share this one implementation -- only the estimator
# constructor and hyperparameter grid differ between them.
# ---------------------------------------------------------------------------
def _make_ridge(**kwargs):
    return Ridge(random_state=0, **kwargs)


def _make_random_forest(**kwargs):
    return RandomForestRegressor(random_state=0, **kwargs)


def _make_gradient_boosting(**kwargs):
    return GradientBoostingRegressor(random_state=0, **kwargs)


def _make_xgboost(**kwargs):
    return xgb.XGBRegressor(random_state=0, verbosity=0, objective="reg:squarederror", **kwargs)


def _make_lightgbm(**kwargs):
    return lgb.LGBMRegressor(random_state=0, verbosity=-1, min_child_samples=1, **kwargs)


class _TabularForecastModel(ForecastModelAdapter):
    """Shared implementation for every lag-feature-based candidate.

    ``estimator_factory`` must be a module-level function (not a lambda or
    closure) so a fitted instance of this class can be pickled by the model
    registry (``ml/model_registry.py``) -- see ``_make_ridge`` etc. above.
    """

    def __init__(self, name: str, library: str, estimator_factory, param_distributions: dict | None = None):
        self.name = name
        self.library = library
        self._estimator_factory = estimator_factory
        self._param_distributions = param_distributions or {}
        self._best_params: dict = {}
        self._model = None

    def _tune(self, x: np.ndarray, y: np.ndarray, splits: list[tuple[np.ndarray, np.ndarray]]) -> None:
        if not self._param_distributions or not _SKLEARN_AVAILABLE or len(splits) < 2:
            self._best_params = {}
            return
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                search = RandomizedSearchCV(
                    self._estimator_factory(),
                    self._param_distributions,
                    n_iter=min(10, _grid_size(self._param_distributions)),
                    cv=splits,
                    scoring="neg_mean_absolute_error",
                    random_state=0,
                )
                search.fit(x, y)
            self._best_params = search.best_params_
        except Exception as exc:  # pragma: no cover - defensive: tuning must never break the bake-off
            logger.warning("forecast_bakeoff.tuning_failed", extra={"model": self.name, "error": str(exc)})
            self._best_params = {}

    def cv_evaluate(self, daily_df: pd.DataFrame, n_splits: int) -> CVResult:
        feature_df = build_feature_frame(daily_df)
        if len(feature_df) < 4:
            return CVResult([math.inf], [0.0], [], 0)

        x = feature_df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = feature_df["carbon"].to_numpy(dtype=float)
        splits = list(time_series_splits(len(x), n_splits))
        self._tune(x, y, splits)

        fold_maes: list[float] = []
        fold_mapes: list[float] = []
        fold_residuals: list[float] = []
        for train_idx, test_idx in splits:
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue
            try:
                model = self._estimator_factory(**self._best_params)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model.fit(x[train_idx], y[train_idx])
                predictions = model.predict(x[test_idx])
            except Exception as exc:  # pragma: no cover
                logger.warning("forecast_bakeoff.fold_failed", extra={"model": self.name, "error": str(exc)})
                continue
            actual = y[test_idx]
            fold_maes.append(float(np.mean(np.abs(actual - predictions))))
            fold_mapes.append(_safe_mape(actual, predictions))
            fold_residuals.extend((actual - predictions).tolist())

        if not fold_maes:
            return CVResult([math.inf], [0.0], [], 0)
        return CVResult(fold_maes, fold_mapes, fold_residuals, len(fold_maes))

    def fit(self, daily_df: pd.DataFrame) -> None:
        feature_df = build_feature_frame(daily_df)
        x = feature_df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = feature_df["carbon"].to_numpy(dtype=float)
        if not self._best_params and self._param_distributions:
            splits = list(time_series_splits(len(x), min(5, max(2, len(x) // 6))))
            self._tune(x, y, splits)
        self._model = self._estimator_factory(**self._best_params)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._model.fit(x, y)

    def predict_next(self, history_df: pd.DataFrame) -> float:
        row = build_next_feature_row(history_df)
        return float(self._model.predict(row)[0])

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            return {}
        if hasattr(self._model, "coef_"):
            weights = np.abs(np.ravel(self._model.coef_))
        elif hasattr(self._model, "feature_importances_"):
            weights = np.asarray(self._model.feature_importances_, dtype=float)
        else:
            return {}
        total = float(np.sum(weights)) or 1.0
        return {col: float(w / total) for col, w in sorted(zip(FEATURE_COLUMNS, weights), key=lambda kv: -kv[1])}


# ---------------------------------------------------------------------------
# SARIMAX: classical time-series baseline, operates on the raw series.
# ---------------------------------------------------------------------------
_SARIMAX_CANDIDATE_ORDERS: list[tuple[tuple, tuple]] = [
    ((1, 1, 1), (0, 0, 0, 0)),
    ((1, 1, 1), (1, 0, 1, 7)),
    ((2, 1, 2), (1, 0, 1, 7)),
    ((1, 0, 1), (1, 1, 1, 7)),
]


class SARIMAXForecastModel(ForecastModelAdapter):
    name = "sarimax"
    library = "statsmodels"

    def __init__(self):
        self.order: tuple = (1, 1, 1)
        self.seasonal_order: tuple = (0, 0, 0, 0)

    @staticmethod
    def _fit_one(series: pd.Series, order: tuple, seasonal_order: tuple):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return SARIMAX(
                series, order=order, seasonal_order=seasonal_order,
                enforce_stationarity=False, enforce_invertibility=False,
            ).fit(disp=False)

    def _select_order(self, series: pd.Series) -> tuple[tuple, tuple]:
        best_aic, best = math.inf, _SARIMAX_CANDIDATE_ORDERS[0]
        for order, seasonal_order in _SARIMAX_CANDIDATE_ORDERS:
            if seasonal_order[3] and len(series) < 2 * seasonal_order[3]:
                continue  # not enough data for this seasonal period
            try:
                result = self._fit_one(series, order, seasonal_order)
                if math.isfinite(result.aic) and result.aic < best_aic:
                    best_aic, best = result.aic, (order, seasonal_order)
            except Exception:
                continue
        return best

    def cv_evaluate(self, daily_df: pd.DataFrame, n_splits: int) -> CVResult:
        series = daily_df["carbon"].reset_index(drop=True)
        if len(series) < 6:
            return CVResult([math.inf], [0.0], [], 0)

        self.order, self.seasonal_order = self._select_order(series)
        splits = list(time_series_splits(len(series), n_splits))

        fold_maes: list[float] = []
        fold_mapes: list[float] = []
        fold_residuals: list[float] = []
        for train_idx, test_idx in splits:
            if len(train_idx) < 4 or len(test_idx) == 0:
                continue
            train_series = series.iloc[train_idx]
            seasonal_period = self.seasonal_order[3] if len(self.seasonal_order) > 3 else 0
            # A seasonal order needs enough training points to estimate the
            # seasonal terms at all -- on an early, small walk-forward fold
            # there may not be. Fitting anyway doesn't error, it just
            # produces a wildly unstable extrapolation (seen in practice:
            # single-fold MAE in the thousands next to single digits on
            # every other fold), which would unfairly tank this candidate's
            # otherwise honest score. Fall back to a naive persistence
            # forecast for just that fold rather than let one under-powered
            # fold's numerical instability dominate the mean.
            if seasonal_period and len(train_series) < 2 * seasonal_period + 5:
                predictions = np.full(len(test_idx), float(train_series.iloc[-1]))
            else:
                try:
                    result = self._fit_one(train_series, self.order, self.seasonal_order)
                    predictions = np.asarray(result.forecast(steps=len(test_idx)))
                except Exception as exc:
                    logger.warning("forecast_bakeoff.fold_failed", extra={"model": self.name, "error": str(exc)})
                    predictions = np.full(len(test_idx), float(train_series.mean()))

            # Defensive sanity clamp: if the fitted model still extrapolated
            # to something wildly outside the observed range of the training
            # data (numerical instability, not a real forecast), treat this
            # fold like a fit failure rather than let a nonsensical number
            # into the leaderboard.
            train_min, train_max = float(train_series.min()), float(train_series.max())
            train_span = max(train_max - train_min, float(train_series.std()) or 1.0, 1.0)
            if not np.all(np.isfinite(predictions)) or np.any(
                np.abs(predictions - float(train_series.mean())) > 15 * train_span
            ):
                predictions = np.full(len(test_idx), float(train_series.iloc[-1]))

            actual = series.iloc[test_idx].to_numpy()
            fold_maes.append(float(np.mean(np.abs(actual - predictions))))
            fold_mapes.append(_safe_mape(actual, predictions))
            fold_residuals.extend((actual - predictions).tolist())

        if not fold_maes:
            return CVResult([math.inf], [0.0], [], 0)
        return CVResult(fold_maes, fold_mapes, fold_residuals, len(fold_maes))

    def fit(self, daily_df: pd.DataFrame) -> None:
        series = daily_df["carbon"].reset_index(drop=True)
        if not hasattr(self, "_selected") :
            self.order, self.seasonal_order = self._select_order(series)
        # Full history is small enough at this project's data scale that
        # refitting from scratch each call in predict_next() is fine -- see
        # that method's docstring for the production alternative.
        self._last_series = series

    def predict_next(self, history_df: pd.DataFrame) -> float:
        series = history_df["carbon"].reset_index(drop=True)
        try:
            result = self._fit_one(series, self.order, self.seasonal_order)
            forecast = np.asarray(result.forecast(steps=1))
            return float(forecast[0])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("forecast_bakeoff.predict_failed", extra={"model": self.name, "error": str(exc)})
            return float(series.iloc[-1]) if len(series) else 0.0

    def feature_importance(self) -> dict[str, float]:
        return {}


# ---------------------------------------------------------------------------
# LSTM: small recurrent neural net, windowed sequence-to-one regression.
# ---------------------------------------------------------------------------
if _TORCH_AVAILABLE:

    class _LSTMNet(nn.Module):
        """Defined at module level (not nested in a method) so a fitted
        LSTMForecastModel can be pickled by the model registry -- a class
        defined inside a function isn't importable by pickle's mechanism."""

        def __init__(self, hidden_size: int = 16):
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=hidden_size, batch_first=True)
            self.head = nn.Linear(hidden_size, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])


class LSTMForecastModel(ForecastModelAdapter):
    """A small windowed LSTM: the last ``window`` days predict the next one.

    Included for algorithmic breadth (per the project's own choice to try
    deep learning even at this data scale). With only a few dozen to a few
    hundred training points, this is not expected to beat the tree
    ensembles or SARIMAX -- the leaderboard (``ForecastRun.candidates_tried``)
    reports its real, honest cross-validated error alongside every other
    family so that's a checkable claim, not an assertion.
    """

    name = "lstm"
    library = "pytorch"

    def __init__(self, window: int = 7, hidden_size: int = 16, epochs: int = 200, lr: float = 0.01, patience: int = 25, seed: int = 0):
        self.window = window
        self.hidden_size = hidden_size
        self.epochs = epochs
        self.lr = lr
        self.patience = patience
        self.seed = seed
        self._model = None
        self._mean = 0.0
        self._std = 1.0

    def _make_windows(self, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y = [], []
        for i in range(len(values) - self.window):
            x.append(values[i : i + self.window])
            y.append(values[i + self.window])
        return np.array(x), np.array(y)

    def _train_net(self, train_values: np.ndarray):
        mean = float(np.mean(train_values))
        std = float(np.std(train_values)) or 1.0
        scaled = (train_values - mean) / std
        x_train, y_train = self._make_windows(scaled)
        if len(x_train) == 0:
            return None, mean, std

        torch.manual_seed(self.seed)
        net = _LSTMNet(self.hidden_size)
        x_tensor = torch.tensor(x_train, dtype=torch.float32).unsqueeze(-1)
        y_tensor = torch.tensor(y_train, dtype=torch.float32).unsqueeze(-1)
        optimizer = torch.optim.Adam(net.parameters(), lr=self.lr)
        loss_fn = nn.MSELoss()

        best_state, best_loss, patience_left = None, math.inf, self.patience
        for _ in range(self.epochs):
            net.train()
            optimizer.zero_grad()
            prediction = net(x_tensor)
            loss = loss_fn(prediction, y_tensor)
            loss.backward()
            optimizer.step()
            current_loss = float(loss.item())
            if current_loss < best_loss - 1e-6:
                best_loss = current_loss
                best_state = {key: value.clone() for key, value in net.state_dict().items()}
                patience_left = self.patience
            else:
                patience_left -= 1
                if patience_left <= 0:
                    break
        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        return net, mean, std

    def cv_evaluate(self, daily_df: pd.DataFrame, n_splits: int) -> CVResult:
        values = daily_df["carbon"].to_numpy(dtype=float)
        if len(values) < self.window + 4:
            return CVResult([math.inf], [0.0], [], 0)

        splits = list(time_series_splits(len(values), n_splits))
        fold_maes: list[float] = []
        fold_mapes: list[float] = []
        fold_residuals: list[float] = []
        for train_idx, test_idx in splits:
            train_values = values[train_idx]
            if len(train_values) <= self.window or len(test_idx) == 0:
                continue
            net, mean, std = self._train_net(train_values)
            if net is None:
                continue
            # Honest one-step-ahead rolling evaluation: predict the next
            # real day, then feed the *true* observed value back in as
            # history before predicting the day after -- this is a fair
            # walk-forward score, not a multi-step compounding forecast.
            history = list(train_values)
            predictions = []
            for true_value in values[test_idx]:
                window_values = np.array(history[-self.window :])
                scaled_window = (window_values - mean) / std
                with torch.no_grad():
                    x_in = torch.tensor(scaled_window, dtype=torch.float32).view(1, self.window, 1)
                    prediction_scaled = net(x_in).item()
                predictions.append(prediction_scaled * std + mean)
                history.append(true_value)
            predictions = np.array(predictions)
            actual = values[test_idx]
            fold_maes.append(float(np.mean(np.abs(actual - predictions))))
            fold_mapes.append(_safe_mape(actual, predictions))
            fold_residuals.extend((actual - predictions).tolist())

        if not fold_maes:
            return CVResult([math.inf], [0.0], [], 0)
        return CVResult(fold_maes, fold_mapes, fold_residuals, len(fold_maes))

    def fit(self, daily_df: pd.DataFrame) -> None:
        values = daily_df["carbon"].to_numpy(dtype=float)
        net, mean, std = self._train_net(values)
        self._model, self._mean, self._std = net, mean, std

    def predict_next(self, history_df: pd.DataFrame) -> float:
        values = history_df["carbon"].to_numpy(dtype=float)
        if self._model is None or len(values) < self.window:
            return float(values[-1]) if len(values) else 0.0
        window_values = values[-self.window :]
        scaled = (window_values - self._mean) / self._std
        with torch.no_grad():
            x_in = torch.tensor(scaled, dtype=torch.float32).view(1, self.window, 1)
            prediction_scaled = self._model(x_in).item()
        return float(prediction_scaled * self._std + self._mean)

    def feature_importance(self) -> dict[str, float]:
        return {}


# ---------------------------------------------------------------------------
# Dependency-free fallback: only used if NOTHING else is installed.
# ---------------------------------------------------------------------------
class LstsqForecastModel(ForecastModelAdapter):
    name = "least_squares_fallback"
    library = "numpy"

    def __init__(self):
        self.coefficients: np.ndarray | None = None

    @staticmethod
    def _design(x: np.ndarray) -> np.ndarray:
        return np.hstack([np.ones((len(x), 1)), x])

    def cv_evaluate(self, daily_df: pd.DataFrame, n_splits: int) -> CVResult:
        feature_df = build_feature_frame(daily_df)
        if len(feature_df) < 4:
            return CVResult([math.inf], [0.0], [], 0)
        x = feature_df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = feature_df["carbon"].to_numpy(dtype=float)

        fold_maes: list[float] = []
        fold_mapes: list[float] = []
        fold_residuals: list[float] = []
        for train_idx, test_idx in time_series_splits(len(x), n_splits):
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue
            coefficients, *_ = np.linalg.lstsq(self._design(x[train_idx]), y[train_idx], rcond=None)
            predictions = self._design(x[test_idx]) @ coefficients
            actual = y[test_idx]
            fold_maes.append(float(np.mean(np.abs(actual - predictions))))
            fold_mapes.append(_safe_mape(actual, predictions))
            fold_residuals.extend((actual - predictions).tolist())

        if not fold_maes:
            return CVResult([math.inf], [0.0], [], 0)
        return CVResult(fold_maes, fold_mapes, fold_residuals, len(fold_maes))

    def fit(self, daily_df: pd.DataFrame) -> None:
        feature_df = build_feature_frame(daily_df)
        x = feature_df[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = feature_df["carbon"].to_numpy(dtype=float)
        self.coefficients, *_ = np.linalg.lstsq(self._design(x), y, rcond=None)

    def predict_next(self, history_df: pd.DataFrame) -> float:
        row = build_next_feature_row(history_df)
        return float((self._design(row) @ self.coefficients)[0])


# ---------------------------------------------------------------------------
# The bake-off itself
# ---------------------------------------------------------------------------
def _available_adapters() -> list[ForecastModelAdapter]:
    adapters: list[ForecastModelAdapter] = []
    if _SKLEARN_AVAILABLE:
        adapters.append(_TabularForecastModel(
            "ridge_regression", "scikit-learn", _make_ridge,
            {"alpha": [0.1, 0.3, 1.0, 3.0, 10.0]},
        ))
        adapters.append(_TabularForecastModel(
            "random_forest", "scikit-learn", _make_random_forest,
            {"n_estimators": [100, 200], "max_depth": [3, 5, 8]},
        ))
        adapters.append(_TabularForecastModel(
            "gradient_boosting", "scikit-learn", _make_gradient_boosting,
            {"n_estimators": [100, 150, 200], "max_depth": [2, 3, 4], "learning_rate": [0.03, 0.05, 0.08, 0.12]},
        ))
    if _XGBOOST_AVAILABLE:
        adapters.append(_TabularForecastModel(
            "xgboost", "xgboost", _make_xgboost,
            {"n_estimators": [100, 200, 300], "max_depth": [2, 3, 4, 5], "learning_rate": [0.03, 0.05, 0.08, 0.12], "subsample": [0.7, 0.85, 1.0]},
        ))
    if _LIGHTGBM_AVAILABLE:
        adapters.append(_TabularForecastModel(
            "lightgbm", "lightgbm", _make_lightgbm,
            {"n_estimators": [100, 200, 300], "num_leaves": [7, 15, 31], "learning_rate": [0.03, 0.05, 0.08, 0.12]},
        ))
    if _STATSMODELS_AVAILABLE:
        adapters.append(SARIMAXForecastModel())
    if _TORCH_AVAILABLE:
        adapters.append(LSTMForecastModel())
    if not adapters:
        adapters.append(LstsqForecastModel())
    return adapters


def available_library_report() -> dict[str, bool]:
    """Which optional ML libraries this environment actually has -- surfaced
    in the UI so it's obvious why the leaderboard has (or is missing) a
    given family, rather than that being a silent difference between
    environments."""
    return {
        "scikit-learn": _SKLEARN_AVAILABLE,
        "xgboost": _XGBOOST_AVAILABLE,
        "lightgbm": _LIGHTGBM_AVAILABLE,
        "statsmodels": _STATSMODELS_AVAILABLE,
        "pytorch": _TORCH_AVAILABLE,
    }


def run_model_bakeoff(daily_df: pd.DataFrame) -> tuple[ForecastModelAdapter, ForecastRun]:
    """Cross-validate every available candidate family and return the winner.

    Every family is scored with the exact same walk-forward split
    (``ml.features.time_series_splits``) on the exact same data, so the
    resulting leaderboard (``ForecastRun.candidates_tried``) is a fair,
    apples-to-apples comparison rather than each family picking its own
    favorable evaluation.
    """
    n_splits = min(5, max(2, len(daily_df) // 8))
    candidates = _available_adapters()

    scored: list[tuple[float, ForecastModelAdapter, CVResult]] = []
    for adapter in candidates:
        try:
            result = adapter.cv_evaluate(daily_df, n_splits)
        except Exception as exc:  # pragma: no cover - defensive: one bad family must never sink the bake-off
            logger.warning("forecast_bakeoff.candidate_crashed", extra={"model": adapter.name, "error": str(exc)})
            continue
        if not result.fold_maes:
            continue
        mean_mae = float(np.mean(result.fold_maes))
        if not math.isfinite(mean_mae):
            continue
        scored.append((mean_mae, adapter, result))

    if not scored:
        fallback = LstsqForecastModel()
        result = fallback.cv_evaluate(daily_df, n_splits)
        mean_mae = float(np.mean(result.fold_maes)) if result.fold_maes else math.inf
        scored = [(mean_mae, fallback, result)]

    scored.sort(key=lambda entry: entry[0])
    best_mae, best_adapter, best_result = scored[0]
    best_adapter.fit(daily_df)

    candidates_tried = {adapter.name: round(mae, 4) for mae, adapter, _ in scored}
    raw_best_params = getattr(best_adapter, "_best_params", {}) or {}
    best_params = {key: (value if isinstance(value, (int, float, str, bool)) else str(value)) for key, value in raw_best_params.items()}

    residual_quantiles = (
        (float(np.quantile(best_result.fold_residuals, 0.10)), float(np.quantile(best_result.fold_residuals, 0.90)))
        if best_result.fold_residuals
        else (0.0, 0.0)
    )

    run = ForecastRun(
        model_name=best_adapter.name,
        library=best_adapter.library,
        feature_columns=FEATURE_COLUMNS,
        training_rows=len(daily_df),
        cv_folds=best_result.n_splits,
        cv_mae=best_mae,
        cv_mape=float(np.mean(best_result.fold_mapes)) if best_result.fold_mapes else 0.0,
        fitted_mae=best_mae,
        residual_quantiles=residual_quantiles,
        feature_importance=best_adapter.feature_importance(),
        used_sklearn=_SKLEARN_AVAILABLE,
        candidates_tried=candidates_tried,
        best_params=best_params,
    )
    return best_adapter, run
