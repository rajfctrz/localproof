"""macOS: no built-in per-app outbound blocking (the macOS firewall is inbound only)."""

from __future__ import annotations

from pathlib import Path

from . import EnforcementStatus, guard_only

OUTBOUND_FIREWALLS = {
    "LuLu": Path("/Applications/LuLu.app"),
    "Little Snitch": Path("/Applications/Little Snitch.app"),
}
VERIFY_STEPS = (
    "LocalProof.app/Contents/MacOS/LocalProof --self-audit   (exit code 2 = guard only)",
)


def installed_firewalls(candidates: dict[str, Path] = OUTBOUND_FIREWALLS) -> list[str]:
    return [name for name, path in candidates.items() if path.exists()]


def detect(candidates: dict[str, Path] = OUTBOUND_FIREWALLS) -> EnforcementStatus:
    found = installed_firewalls(candidates)
    if found:
        tool = " and ".join(found)
        extra = (
            f" {tool} is installed. LocalProof cannot check whether it has a rule for this app; "
            f"to add OS-level blocking, create a {tool} rule that denies all outbound connections for LocalProof."
        )
    else:
        extra = (
            " For OS-level blocking, install an outbound firewall such as LuLu (free, open source) or "
            "Little Snitch and deny all outbound connections for LocalProof."
        )
    return guard_only(
        "none (macOS has no built-in outbound firewall)",
        "Only the Python netguard protects this app on macOS." + extra,
        VERIFY_STEPS,
    )
