"""User settings stored as JSON in the user config folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from localproof import paths

SETTINGS_FILE = "settings.json"
DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365


class SettingsError(ValueError):
    """Invalid setting value. Message is user-facing."""


@dataclass(frozen=True)
class Settings:
    upload_retention_days: int = DEFAULT_RETENTION_DAYS


def validate_retention(value: object) -> int:
    try:
        days = int(str(value).strip())
    except ValueError as exc:
        raise SettingsError("Retention must be a whole number of days.") from exc
    if not MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS:
        raise SettingsError(f"Retention must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS} days.")
    return days


def load() -> Settings:
    """Read settings; missing or invalid values fall back to defaults."""
    path = paths.config_dir() / SETTINGS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Settings(upload_retention_days=validate_retention(raw["upload_retention_days"]))
    except (OSError, ValueError, KeyError, TypeError):
        return Settings()


def save(settings: Settings) -> Settings:
    validated = Settings(upload_retention_days=validate_retention(settings.upload_retention_days))
    path = paths.config_dir() / SETTINGS_FILE
    tmp = path.with_name(f"{SETTINGS_FILE}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(asdict(validated), indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return validated
