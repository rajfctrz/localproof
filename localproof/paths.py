"""Per-user folders for everything LocalProof writes.

All user files (uploads, exports, logs, config, the Flask SECRET_KEY) must be
resolved through this module. Nothing is ever written inside the app or
install directory; every path is checked against it before use.

``LOCALPROOF_HOME`` (dev/test only) relocates all folders under one root.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import platformdirs

APP_NAME = "LocalProof"
HOME_ENV = "LOCALPROOF_HOME"
SECRET_KEY_FILE = "secret_key"
SECRET_KEY_BYTES = 32


class UnsafePathError(RuntimeError):
    """Raised when a user-file path would land inside the app directory."""


def app_dir() -> Path:
    """Directory the app runs from: the PyInstaller bundle, or the source tree."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle).resolve()
    return Path(__file__).resolve().parents[1]


def _checked(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(app_dir()):
        raise UnsafePathError(
            f"Refusing to use {resolved}: it is inside the app directory {app_dir()}"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _home_override() -> Path | None:
    value = os.environ.get(HOME_ENV, "").strip()
    return Path(value) if value else None


def data_dir() -> Path:
    home = _home_override()
    if home:
        return _checked(home / "data")
    return _checked(Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)))


def log_dir() -> Path:
    home = _home_override()
    if home:
        return _checked(home / "logs")
    return _checked(Path(platformdirs.user_log_dir(APP_NAME, appauthor=False)))


def config_dir() -> Path:
    home = _home_override()
    if home:
        return _checked(home / "config")
    return _checked(Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)))


def uploads_dir() -> Path:
    return _checked(data_dir() / "uploads")


def exports_dir() -> Path:
    return _checked(data_dir() / "exports")


def secret_key() -> str:
    """Return the per-install Flask SECRET_KEY, creating it on first use."""
    key_path = config_dir() / SECRET_KEY_FILE
    if key_path.exists():
        key = key_path.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(SECRET_KEY_BYTES)
    # Write a fresh owner-only file, then swap it in atomically so a stale
    # file's permissions are never inherited and readers never see a partial key.
    tmp_path = key_path.with_name(f"{SECRET_KEY_FILE}.{os.getpid()}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    os.replace(tmp_path, key_path)
    return key


def folder_size(path: Path) -> int:
    """Total size in bytes of all files under ``path``."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
