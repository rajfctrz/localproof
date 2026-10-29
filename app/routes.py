"""HTTP routes for the Cash Flow Forecast demo."""

from __future__ import annotations

import io
import math
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge

from localproof import paths

from . import forecast

bp = Blueprint("main", __name__)

SAMPLE_RUN_ID = "sample"
UPLOAD_SOURCE = "upload"
SAMPLE_FILE = Path("sample_data") / "monthly_cashflow.csv"
RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
EXPORT_NAME_PATTERN = re.compile(r"cashflow-forecast-\d{8}-\d{6}-[0-9a-f]{6}\.xlsx")
EXPORT_SUFFIX_BYTES = 3


def _sample_path() -> Path:
    return paths.app_dir() / SAMPLE_FILE


def _run_csv(run_id: str) -> Path:
    if run_id == SAMPLE_RUN_ID:
        return _sample_path()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        abort(404)
    path = paths.uploads_dir() / f"{run_id}.csv"
    if not path.is_file():
        abort(404)
    return path


def _parse_horizon(raw: str | None) -> int:
    try:
        return int(raw) if raw else forecast.MAX_HORIZON
    except ValueError as exc:
        raise forecast.ForecastError("Horizon must be a whole number of months.") from exc


def _existing_export(name: str | None) -> str | None:
    """Only echo back an export name we generated and that is on disk."""
    if name and EXPORT_NAME_PATTERN.fullmatch(name) and (paths.exports_dir() / name).is_file():
        return name
    return None


def _horizons() -> range:
    return range(forecast.MIN_HORIZON, forecast.MAX_HORIZON + 1)


def _index(error: str | None = None, status: int = 200):
    return (
        render_template(
            "index.html",
            error=error,
            horizons=_horizons(),
            default_horizon=forecast.MAX_HORIZON,
            min_months=forecast.MIN_MONTHS,
        ),
        status,
    )


def _run(run_id: str, horizon: int) -> forecast.ForecastResult:
    monthly = forecast.load_cashflow_csv(_run_csv(run_id))
    return forecast.forecast_cashflow(monthly, horizon=horizon)


def _save_upload(upload: FileStorage | None, horizon: int) -> str:
    """Validate an uploaded CSV, then store it in the user data folder."""
    if not (upload and upload.filename):
        raise forecast.ForecastError("Choose a CSV file, or use the sample data.")
    raw = upload.read()
    # Run the full forecast first so nothing invalid is written to disk.
    forecast.forecast_cashflow(forecast.load_cashflow_csv(io.BytesIO(raw)), horizon)
    run_id = uuid.uuid4().hex
    (paths.uploads_dir() / f"{run_id}.csv").write_bytes(raw)
    return run_id


@bp.get("/")
def index():
    return _index()


@bp.post("/forecast")
def start_forecast():
    try:
        horizon = _parse_horizon(request.form.get("horizon"))
        source = request.form.get("source")
        if source == SAMPLE_RUN_ID:
            run_id = SAMPLE_RUN_ID
        elif source == UPLOAD_SOURCE:
            run_id = _save_upload(request.files.get("csv_file"), horizon)
        else:
            raise forecast.ForecastError("Choose a CSV file, or use the sample data.")
    except forecast.ForecastError as exc:
        return _index(str(exc), 400)
    return redirect(url_for("main.show_forecast", run_id=run_id, horizon=horizon))


@bp.get("/forecast/<run_id>")
def show_forecast(run_id: str):
    try:
        horizon = _parse_horizon(request.args.get("horizon"))
        result = _run(run_id, horizon)
    except forecast.ForecastError as exc:
        return _index(str(exc), 400)
    return render_template(
        "result.html",
        run_id=run_id,
        is_sample=run_id == SAMPLE_RUN_ID,
        horizon=horizon,
        horizons=_horizons(),
        result=result,
        rows=result.to_frame().to_dict("records"),
        chart=result.chart_data(),
        export_name=_existing_export(request.args.get("exported")),
        exports_folder=str(paths.exports_dir()),
    )


@bp.post("/forecast/<run_id>/export")
def export_forecast(run_id: str):
    try:
        horizon = _parse_horizon(request.form.get("horizon"))
        result = _run(run_id, horizon)
    except forecast.ForecastError as exc:
        return _index(str(exc), 400)
    name = f"cashflow-forecast-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(EXPORT_SUFFIX_BYTES)}.xlsx"
    forecast.write_excel(result, paths.exports_dir() / name)
    return redirect(url_for("main.show_forecast", run_id=run_id, horizon=horizon, exported=name))


@bp.get("/exports/<name>")
def download_export(name: str):
    if not EXPORT_NAME_PATTERN.fullmatch(name):
        abort(404)
    return send_from_directory(paths.exports_dir(), name, as_attachment=True)


@bp.get("/health")
def health():
    return jsonify(status="ok", version=current_app.config["APP_VERSION"])


@bp.app_template_filter("money")
def money(value: object) -> str:
    """Format an amount with thousands separators; blank for missing values."""
    if not isinstance(value, (int, float)) or math.isnan(value):
        return ""
    return f"{value:,.0f}"


@bp.app_errorhandler(RequestEntityTooLarge)
def too_large(_exc):
    limit_mb = current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return _index(f"That file is larger than {limit_mb} MB.", 413)
