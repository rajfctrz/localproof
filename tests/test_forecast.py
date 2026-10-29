import io

import numpy as np
import pandas as pd
import pytest

from app import forecast
from app.forecast import ForecastError
from tests.conftest import SAMPLE_CSV


def csv(text: str) -> io.StringIO:
    return io.StringIO(text)


def monthly_series(months: int) -> pd.Series:
    index = pd.date_range("2022-01-01", periods=months, freq="MS")
    t = np.arange(months)
    values = 1000 + 10 * t + 100 * np.sin(2 * np.pi * t / 12)
    return pd.Series(values, index=index, dtype=float)


def test_sample_csv_loads_as_36_contiguous_months():
    monthly = forecast.load_cashflow_csv(SAMPLE_CSV)
    assert len(monthly) == 36
    assert monthly.index.freqstr == "MS"
    assert not monthly.isna().any()


@pytest.mark.parametrize("horizon", [6, 9, 12])
def test_forecast_has_requested_shape_and_no_nans(horizon):
    result = forecast.forecast_cashflow(forecast.load_cashflow_csv(SAMPLE_CSV), horizon)
    assert len(result.forecast) == len(result.lower) == len(result.upper) == horizon
    for series in (result.forecast, result.lower, result.upper):
        assert not series.isna().any()
    assert (result.lower <= result.forecast).all()
    assert (result.forecast <= result.upper).all()
    assert result.forecast.index[0] == result.history.index[-1] + pd.offsets.MonthBegin(1)


def test_to_frame_has_history_then_forecast_rows():
    result = forecast.forecast_cashflow(monthly_series(30), 6)
    frame = result.to_frame()
    assert len(frame) == 36
    assert frame["actual"].iloc[:30].notna().all()
    assert frame["forecast"].iloc[30:].notna().all()


def test_chart_data_aligns_all_series_with_labels():
    result = forecast.forecast_cashflow(monthly_series(24), 6)
    chart = result.chart_data()
    lengths = {len(chart[k]) for k in ("labels", "actual", "forecast", "lower", "upper")}
    assert lengths == {30}
    # Forecast line joins the last actual point.
    assert chart["forecast"][23] == chart["actual"][23]


def test_short_series_raises_clear_error():
    with pytest.raises(ForecastError, match="at least 24 months"):
        forecast.forecast_cashflow(monthly_series(23), 6)


@pytest.mark.parametrize("horizon", [5, 13, 0])
def test_out_of_range_horizon_rejected(horizon):
    with pytest.raises(ForecastError, match="between 6 and 12"):
        forecast.forecast_cashflow(monthly_series(24), horizon)


def test_rows_are_summed_per_month():
    monthly = forecast.load_cashflow_csv(
        csv("date,amount\n2024-01-03,10\n2024-01-20,5\n2024-02-01,7\n")
    )
    assert monthly.tolist() == [15.0, 7.0]


def test_column_names_are_case_and_space_insensitive():
    monthly = forecast.load_cashflow_csv(csv(" Date , AMOUNT \n2024-01-01,1\n"))
    assert monthly.tolist() == [1.0]


def test_missing_column_reported():
    with pytest.raises(ForecastError, match="missing column.*amount"):
        forecast.load_cashflow_csv(csv("date,value\n2024-01-01,1\n"))


def test_bad_amount_reports_line_number():
    with pytest.raises(ForecastError, match="line\\(s\\) 3"):
        forecast.load_cashflow_csv(csv("date,amount\n2024-01-01,1\n2024-02-01,abc\n"))


def test_bad_date_reports_line_number():
    with pytest.raises(ForecastError, match="Unreadable date.*2"):
        forecast.load_cashflow_csv(csv("date,amount\nnot-a-date,1\n"))


def test_gap_between_months_rejected():
    with pytest.raises(ForecastError, match="Missing months.*2024-02"):
        forecast.load_cashflow_csv(csv("date,amount\n2024-01-01,1\n2024-03-01,1\n"))


def test_empty_csv_rejected():
    with pytest.raises(ForecastError):
        forecast.load_cashflow_csv(csv(""))


def test_write_excel_round_trips(tmp_path):
    result = forecast.forecast_cashflow(monthly_series(24), 6)
    out = forecast.write_excel(result, tmp_path / "out.xlsx")
    table = pd.read_excel(out)
    assert list(table.columns) == ["month", "actual", "forecast", "lower", "upper"]
    assert len(table) == 30


def test_forecast_module_has_no_flask_dependency():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(forecast.__file__).read_text())
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.split(".")[0] == "flask" for name in imported)


def test_duplicate_columns_after_normalising_rejected():
    with pytest.raises(ForecastError, match="more than once"):
        forecast.load_cashflow_csv(csv("Date,date,amount\n2024-01-01,2024-01-01,1\n"))


@pytest.mark.parametrize(
    "rows",
    [
        "2024-01-01T00:00:00+05:30,1\n2024-02-01T00:00:00+05:30,2\n",  # same offset
        "2024-01-01T00:00:00+05:30,1\n2024-02-01T00:00:00-08:00,2\n",  # mixed offsets
    ],
)
def test_timezone_offsets_keep_the_calendar_month_as_written(rows):
    monthly = forecast.load_cashflow_csv(csv("date,amount\n" + rows))
    assert [m.strftime("%Y-%m") for m in monthly.index] == ["2024-01", "2024-02"]
    assert monthly.tolist() == [1.0, 2.0]


def test_mixed_offsets_with_garbage_reports_line():
    with pytest.raises(ForecastError, match="Unreadable date.*3"):
        forecast.load_cashflow_csv(
            csv("date,amount\n2024-01-01T00:00:00+05:30,1\nnope,2\n2024-02-01T00:00:00-08:00,2\n")
        )


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")
def test_monthly_total_overflow_rejected():
    with pytest.raises(ForecastError, match="too large"):
        forecast.load_cashflow_csv(csv("date,amount\n2024-01-01,1e308\n2024-01-15,1e308\n"))


def test_constant_series_does_not_crash():
    flat = pd.Series([100.0] * 24, index=pd.date_range("2022-01-01", periods=24, freq="MS"))
    try:
        result = forecast.forecast_cashflow(flat, 6)
    except ForecastError:
        return  # a clear user-facing error is acceptable
    assert not result.forecast.isna().any()
