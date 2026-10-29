"""Open a file or folder with its default OS application (Windows, macOS, Linux)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> tuple[bool, str]:
    """Return (ok, message). Never raises for a missing opener."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]  # Windows-only API
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        else:
            return False, f"Opening files is not available on this OS ({sys.platform}). Path: {path}"
    except (OSError, ValueError) as exc:
        return False, f"Could not open it ({exc}). Path: {path}"
    return True, f"Opened {path}"
