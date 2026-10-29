"""Version, build metadata and the identity of the running executable."""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from localproof import __version__
from localproof.enforcement.linux import FLATPAK_INFO, read_flatpak_info

HASH_CHUNK = 1024 * 1024
DEV_BUILD = "development build (not packaged)"


@dataclass(frozen=True)
class ExecutableIdentity:
    label: str  # what is being identified, e.g. "SHA-256 of LocalProof.exe"
    path: str | None
    value: str  # hash, Flatpak commit, or an explanation


def build_timestamp() -> str:
    """UTC build time, written into localproof/_build_info.py by the packaging step."""
    try:
        from localproof import _build_info  # type: ignore[attr-defined]
    except ImportError:
        return DEV_BUILD
    return getattr(_build_info, "BUILD_TIMESTAMP", DEV_BUILD)


def build_commit() -> str:
    try:
        from localproof import _build_info  # type: ignore[attr-defined]
    except ImportError:
        return "n/a"
    return getattr(_build_info, "GIT_COMMIT", "n/a")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _flatpak_identity(info_path: Path) -> ExecutableIdentity | None:
    info = read_flatpak_info(info_path)
    if info is None:
        return None
    commit = info.get("Instance", "app-commit", fallback="") or "unknown"
    app = info.get("Application", "name", fallback="?")
    return ExecutableIdentity(f"Flatpak commit of {app}", None, commit)


@lru_cache(maxsize=1)
def executable_identity(info_path: Path = FLATPAK_INFO) -> ExecutableIdentity:
    """What a reviewer should compare against the published release hashes."""
    flatpak = _flatpak_identity(info_path)
    if flatpak:
        return flatpak
    if not getattr(sys, "frozen", False):
        return ExecutableIdentity("Executable", None, "not packaged: running from source, nothing to hash")
    appimage = os.environ.get("APPIMAGE")
    target = Path(appimage) if appimage else Path(sys.executable)
    # macOS: sys.executable is the main binary inside LocalProof.app/Contents/MacOS/.
    return ExecutableIdentity(f"SHA-256 of {target.name}", str(target), sha256_file(target))
