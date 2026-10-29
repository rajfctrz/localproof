"""Retention purging and "delete all my data"."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from localproof import paths

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class DeletionReport:
    removed_files: int
    removed_bytes: int
    truncated_logs: int
    failed: tuple[str, ...]


def purge_expired_uploads(retention_days: int, now: float | None = None) -> tuple[Path, ...]:
    """Delete uploads older than ``retention_days`` (by modification time)."""
    cutoff = (time.time() if now is None else now) - retention_days * SECONDS_PER_DAY
    removed = []
    for path in paths.uploads_dir().iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path)
        except OSError:
            continue  # retried on the next purge
    return tuple(removed)


def _files_under(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()]


def delete_all() -> DeletionReport:
    """Remove every upload and export, and empty the log files.

    Logs are truncated rather than deleted because the running app holds them
    open (Windows will not delete open files). Settings and the session key in
    the config folder are kept so the app keeps working.
    """
    removed, removed_bytes, truncated, failed = 0, 0, 0, []
    for folder in (paths.uploads_dir(), paths.exports_dir()):
        for path in _files_under(folder):
            try:
                size = path.stat().st_size
                path.unlink()
                removed += 1
                removed_bytes += size
            except OSError as exc:
                failed.append(f"{path}: {exc}")
    for path in _files_under(paths.log_dir()):
        try:
            removed_bytes += path.stat().st_size
            path.write_bytes(b"")
            truncated += 1
        except OSError as exc:
            failed.append(f"{path}: {exc}")
    return DeletionReport(removed, removed_bytes, truncated, tuple(failed))
