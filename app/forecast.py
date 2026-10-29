"""Cash-flow forecasting: pure functions, no Flask.

Input is a CSV with ``date`` and ``amount`` columns. Rows are summed per
calendar month, and the monthly series is forecast with additive Holt-Winters
(statsmodels ETS, 12-month season) including a prediction interval.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

SEASON_LENGTH = 12
MIN_MONTHS = 2 * SEASON_LENGTH  # two full seasons to estimate seasonality
MIN_HORIZON = 6
MAX_HORIZON = 12
DEFAULT_CONFIDENCE = 0.95
REQUIRED_COLUMNS = ("date", "amount")


class ForecastError(ValueError):
    """Input or parameters cannot produce a forecast. Message is user-facing."""


@dataclass(frozen=True)
class ForecastResult:
    history: pd.Series  # actuals, monthly, indexed by month start
    forecast: pd.Series
    lower: pd.Series
    upper: pd.Series
    confidence: float

    def to_frame(self) -> pd.DataFrame:
        """One row per month: actuals, then forecast with its band."""
        actual = pd.DataFrame({"month": self.history.index, "actual": self.history.values})
        future = pd.DataFrame(
            {
                "month": self.forecast.index,
                "forecast": self.forecast.values,
                "lower": self.lower.values,
                "upper": self.upper.values,
            }
        )
        return pd.concat([actual, future], ignore_index=True)

    def chart_data(self) -> dict[str, list]:
        """JSON-ready series for the chart, aligned on one label axis."""
        labels = [m.strftime("%Y-%m") for m in self.history.index.append(self.forecast.index)]
        pad_future = [None] * len(self.forecast)
        # The forecast line starts at the last actual so the two lines join.
        pad_history = [None] * (len(self.history) - 1)
        last = [round(float(self.history.iloc[-1]), 2)]
        return {
            "labels": labels,
            "actual": _rounded(self.history) + pad_future,
            "forecast": pad_history + last + _rounded(self.forecast),
            "lower": pad_history + last + _rounded(self.lower),
            "upper": pad_history + last + _rounded(self.upper),
        }


def _rounded(series: pd.Series) -> list[float]:
    return [round(float(v), 2) for v in series.values]


def load_cashflow_csv(source: str | Path | IO) -> pd.Series:
    """Read a ``date,amount`` CSV and return monthly totals.

    Raises ForecastError for missing columns, unparseable values, or gaps
    between months.
    """
    try:
        frame = pd.read_csv(source)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ForecastError(f"Could not read the CSV file: {exc}") from exc

    frame.columns = [str(c).strip().lower() for c in frame.columns]
    duplicated = sorted({c for c in REQUIRED_COLUMNS if list(frame.columns).count(c) > 1})
    if duplicated:
        raise ForecastError(f"CSV has the column(s) {', '.join(duplicated)} more than once.")
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ForecastError(
            f"CSV is missing column(s): {', '.join(missing)}. Expected 'date' and 'amount'."
        )
    if frame.empty:
        raise ForecastError("CSV has no data rows.")

    dates = _parse_dates(frame["date"])
    amounts = pd.to_numeric(frame["amount"], errors="coerce")
    _reject_bad_values(dates, amounts)

    months = dates.dt.to_period("M")
    monthly = amounts.groupby(months).sum().sort_index()
    if not np.isfinite(monthly).all():
        raise ForecastError("Monthly totals are too large to calculate with.")
    expected = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    gaps = expected.difference(monthly.index)
    if len(gaps):
        shown = ", ".join(str(p) for p in gaps[:5])
        raise ForecastError(f"Missing months in the data: {shown}. Every month needs at least one row.")

    monthly.index = monthly.index.to_timestamp(how="start")
    monthly.index.freq = "MS"
    monthly.name = "amount"
    return monthly.astype(float)


def _parse_dates(raw: pd.Series) -> pd.Series:
    """Parse dates, keeping the calendar date as written.

    Timezone offsets are dropped rather than converted, so a row dated
    2024-01-01T00:00+05:30 stays in January instead of shifting to December UTC.
    Unparseable values become NaT.
    """
    try:
        dates = pd.to_datetime(raw, errors="coerce")
    except ValueError:
        dates = None  # pandas refuses mixed offsets in one pass
    if dates is not None and isinstance(dates.dtype, pd.DatetimeTZDtype):
        return dates.dt.tz_localize(None)
    if dates is not None and pd.api.types.is_datetime64_dtype(dates):
        return dates
    # Mixed offsets: drop each offset individually.
    return pd.to_datetime(raw.map(_naive_timestamp))


def _naive_timestamp(value: object) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    return stamp.tz_localize(None) if stamp.tzinfo else stamp


def _reject_bad_values(dates: pd.Series, amounts: pd.Series) -> None:
    bad_dates = dates.isna()
    if bad_dates.any():
        rows = ", ".join(str(i + 2) for i in bad_dates[bad_dates].index[:5])
        raise ForecastError(f"Unreadable date on CSV line(s) {rows}.")
    bad_amounts = amounts.isna() | ~np.isfinite(amounts)
    if bad_amounts.any():
        rows = ", ".join(str(i + 2) for i in bad_amounts[bad_amounts].index[:5])
        raise ForecastError(f"Missing or non-numeric amount on CSV line(s) {rows}.")


def forecast_cashflow(
    monthly: pd.Series,
    horizon: int = MAX_HORIZON,
    confidence: float = DEFAULT_CONFIDENCE,
) -> ForecastResult:
    """Forecast ``horizon`` months ahead with a ``confidence`` prediction band."""
    if not MIN_HORIZON <= horizon <= MAX_HORIZON:
        raise ForecastError(f"Horizon must be between {MIN_HORIZON} and {MAX_HORIZON} months.")
    if not 0 < confidence < 1:
        raise ForecastError("Confidence must be between 0 and 1.")
    if len(monthly) < MIN_MONTHS:
        raise ForecastError(
            f"Need at least {MIN_MONTHS} months of data to model yearly seasonality; got {len(monthly)}."
        )
    if monthly.isna().any():
        raise ForecastError("Series contains missing values.")

    model = ETSModel(
        monthly,
        error="add",
        trend="add",
        seasonal="add",
        seasonal_periods=SEASON_LENGTH,
    )
    try:
        with warnings.catch_warnings():
            # Convergence chatter from the optimiser is not actionable for users.
            warnings.simplefilter("ignore")
            fitted = model.fit(disp=False)
            frame = fitted.get_prediction(
                start=len(monthly), end=len(monthly) + horizon - 1
            ).summary_frame(alpha=1 - confidence)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        raise ForecastError("The model could not be fitted to this data.") from exc

    if frame[["mean", "pi_lower", "pi_upper"]].isna().any().any():
        raise ForecastError("The model could not produce a stable forecast for this data.")

    return ForecastResult(
        history=monthly,
        forecast=frame["mean"].rename("forecast"),
        lower=frame["pi_lower"].rename("lower"),
        upper=frame["pi_upper"].rename("upper"),
        confidence=confidence,
    )


def write_excel(result: ForecastResult, path: Path) -> Path:
    """Write the actuals and forecast table to ``path`` (.xlsx)."""
    table = result.to_frame()
    table["month"] = table["month"].dt.strftime("%Y-%m")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Forecast", index=False)
    return path
