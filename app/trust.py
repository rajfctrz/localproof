"""Trust Panel: what protects this app, what it blocked, and where your data lives."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

from flask import Blueprint, redirect, render_template, request, url_for

from localproof import __version__, buildinfo, enforcement, netguard, opener, paths, settings, userdata

bp = Blueprint("trust", __name__, url_prefix="/trust")

TRY_IT_URL = "https://example.com/"
TRY_IT_TIMEOUT_S = 3
RECENT_ATTEMPTS = 50
DELETE_CONFIRM_FIELD = "confirm_delete"

# Fixed messages keyed by a short code, so nothing from the query string is echoed back.
NOTICES = {
    "try-blocked": ("ok", "Blocked. The attempt to reach example.com never left this computer, and was added to the list below."),
    "try-allowed": ("error", "The connection went through. The guard is not enforcing (network override?)."),
    "try-failed": ("error", "The connection failed, but not because of netguard. Check the list below."),
    "try-unavailable": ("error", "Try it only runs while the guard is enforcing, so it never makes a real request."),
    "opened": ("ok", "Opened the data folder."),
    "open-failed": ("error", "Could not open the folder automatically. The path is shown below."),
    "deleted": ("ok", "Deleted your uploads and exports and emptied the logs."),
    "delete-partial": ("error", "Some files could not be deleted. They are listed in the log folder."),
    "delete-unconfirmed": ("error", "Tick the box to confirm before deleting."),
    "retention-saved": ("ok", "Retention saved. Older uploads were removed."),
    "retention-invalid": (
        "error",
        f"Retention must be a whole number between {settings.MIN_RETENTION_DAYS} and {settings.MAX_RETENTION_DAYS} days.",
    ),
}


@dataclass(frozen=True)
class Badge:
    state: str  # css modifier: enforced | guard_only | dev_override | off
    label: str
    blocked: int


def badge() -> Badge:
    guard = netguard.status()
    blocked = len(netguard.blocked_attempts())
    if guard.override:
        return Badge("dev_override", "Network override ON", blocked)
    if not guard.active:
        return Badge("off", "Guard not running", blocked)
    status = enforcement.detect_cached()
    return Badge(status.tier, status.label, blocked)


def _guard_description(guard: netguard.GuardStatus) -> str:
    if guard.override:
        return f"Audit only: {netguard.ALLOW_ENV}=1 is set, so outbound calls are allowed and logged."
    if guard.active:
        return "Enforcing: every non-loopback connection from Python is refused and logged."
    return "Not running. This happens in browser dev mode (flask run); the desktop app always starts it."


def _redirect(notice: str):
    return redirect(url_for("trust.panel", notice=notice))


@bp.get("/")
def panel():
    guard = netguard.status()
    status = enforcement.detect_cached(refresh=True)
    data_dir = paths.data_dir()
    blocked = netguard.blocked_attempts()
    notice = NOTICES.get(request.args.get("notice", ""))
    return render_template(
        "trust.html",
        notice=notice,
        guard=guard,
        guard_description=_guard_description(guard),
        log_error=netguard.log_error(),
        status=status,
        blocked_count=len(blocked),
        attempts=list(reversed(netguard.attempts()))[:RECENT_ATTEMPTS],
        data_dir=str(data_dir),
        data_size=paths.folder_size(data_dir),
        log_dir=str(paths.log_dir()),
        config_dir=str(paths.config_dir()),
        retention_days=settings.load().upload_retention_days,
        retention_min=settings.MIN_RETENTION_DAYS,
        retention_max=settings.MAX_RETENTION_DAYS,
        version=__version__,
        build_time=buildinfo.build_timestamp(),
        build_commit=buildinfo.build_commit(),
        identity=buildinfo.executable_identity(),
        try_it_enabled=guard.active,
    )


@bp.post("/try")
def try_it():
    if not netguard.status().active:
        return _redirect("try-unavailable")
    try:
        urllib.request.urlopen(TRY_IT_URL, timeout=TRY_IT_TIMEOUT_S).close()
    except urllib.error.URLError as exc:
        blocked = isinstance(exc.reason, netguard.OutboundBlockedError)
        return _redirect("try-blocked" if blocked else "try-failed")
    except netguard.OutboundBlockedError:
        return _redirect("try-blocked")
    except OSError:
        return _redirect("try-failed")
    return _redirect("try-allowed")


@bp.post("/open-folder")
def open_folder():
    ok, _message = opener.open_path(paths.data_dir())
    return _redirect("opened" if ok else "open-failed")


@bp.post("/delete-data")
def delete_data():
    if request.form.get(DELETE_CONFIRM_FIELD) != "yes":
        return _redirect("delete-unconfirmed")
    report = userdata.delete_all()
    return _redirect("delete-partial" if report.failed else "deleted")


@bp.post("/retention")
def retention():
    try:
        days = settings.validate_retention(request.form.get("retention_days", ""))
    except settings.SettingsError:
        return _redirect("retention-invalid")
    settings.save(settings.Settings(upload_retention_days=days))
    userdata.purge_expired_uploads(days)
    return _redirect("retention-saved")
