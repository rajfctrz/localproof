"""Linux: Flatpak sandbox without network permission, else guard only."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Mapping

from . import EnforcementStatus, guard_only

FLATPAK_INFO = Path("/.flatpak-info")
FLATPAK_APP_ID = "io.github.OWNER.LocalProof"
FLATPAK_VERIFY = (
    f"flatpak info --show-permissions {FLATPAK_APP_ID}   (no 'network' under shared=)",
    f"flatpak run --env=LOCALPROOF_ALLOW_NETWORK=1 {FLATPAK_APP_ID} --probe-outbound   (expect: blocked by the OS)",
    f"flatpak run {FLATPAK_APP_ID} --self-audit   (exit code 0 = enforced)",
)
GUARD_VERIFY = ("LocalProof --self-audit   (exit code 2 = guard only)",)


def read_flatpak_info(path: Path = FLATPAK_INFO) -> configparser.ConfigParser | None:
    if not path.exists():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return parser


def shared_permissions(info: configparser.ConfigParser) -> set[str]:
    raw = info.get("Context", "shared", fallback="")
    return {item.strip() for item in raw.split(";") if item.strip()}


def detect(info_path: Path = FLATPAK_INFO, environ: Mapping[str, str] = os.environ) -> EnforcementStatus:
    try:
        info = read_flatpak_info(info_path)
    except (configparser.Error, OSError, UnicodeDecodeError) as exc:
        return guard_only("Flatpak sandbox", f"Could not read {info_path}: {exc}", FLATPAK_VERIFY)

    if info is not None:
        if not info.has_section("Context"):
            return guard_only("Flatpak sandbox", f"{info_path} has no [Context] section.", FLATPAK_VERIFY)
        shared = shared_permissions(info)
        if "network" in shared:
            return guard_only(
                "Flatpak sandbox (network shared)",
                "This Flatpak was granted network access (shared=network), so the sandbox does not block outbound traffic.",
                FLATPAK_VERIFY,
            )
        return EnforcementStatus(
            tier="enforced",
            mechanism="Flatpak sandbox without network permission",
            active=True,
            verify_steps=FLATPAK_VERIFY,
            notes="The app runs in its own network namespace with only a loopback interface, so no process inside it can reach the network.",
        )

    if environ.get("APPIMAGE"):
        return guard_only(
            "none (AppImage)",
            "AppImages have no sandbox: only the Python netguard protects this app. Use the Flatpak for OS-level enforcement.",
            GUARD_VERIFY,
        )
    return guard_only(
        "none",
        "Running outside a sandbox: only the Python netguard protects this app. Use the Flatpak for OS-level enforcement.",
        GUARD_VERIFY,
    )
