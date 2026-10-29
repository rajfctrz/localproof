"""OS-level outbound enforcement: one provider per OS behind ``detect()``.

Tiers are reported truthfully:
- ``enforced``: an OS mechanism blocks this app's outbound traffic and the
  check confirmed it (Windows Firewall rule present; Flatpak without network).
- ``guard_only``: only the Python netguard protects the app.
- ``dev_override``: LOCALPROOF_ALLOW_NETWORK=1 is set; outbound is allowed.

A provider that cannot complete its check never reports ``enforced``.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Literal

Tier = Literal["enforced", "guard_only", "dev_override"]

TIER_LABELS: dict[str, str] = {
    "enforced": "Enforced by the OS",
    "guard_only": "Guard only",
    "dev_override": "Network override ON",
}
CACHE_SECONDS = 60.0


@dataclass(frozen=True)
class EnforcementStatus:
    tier: Tier
    mechanism: str
    active: bool
    verify_steps: tuple[str, ...]
    notes: str

    @property
    def label(self) -> str:
        return TIER_LABELS[self.tier]


def guard_only(mechanism: str, notes: str, verify_steps: tuple[str, ...] = ()) -> EnforcementStatus:
    return EnforcementStatus("guard_only", mechanism, False, verify_steps, notes)


def _provider() -> Callable[[], EnforcementStatus]:
    if sys.platform == "win32":
        from . import windows

        return windows.detect
    if sys.platform == "darwin":
        from . import macos

        return macos.detect
    if sys.platform.startswith("linux"):
        from . import linux

        return linux.detect
    platform = sys.platform
    return lambda: guard_only("none", f"No OS-level enforcement is known for platform '{platform}'.")


def detect(provider: Callable[[], EnforcementStatus] | None = None) -> EnforcementStatus:
    """Current enforcement status. Never ``enforced`` if the check failed."""
    from localproof import netguard

    try:
        status = (provider or _provider())()
    except Exception as exc:  # noqa: BLE001 - a failed check must degrade, not crash
        status = guard_only("unknown", f"The OS enforcement check failed: {type(exc).__name__}: {exc}")
    if status.tier == "enforced" and not status.active:
        status = replace(status, tier="guard_only", notes=status.notes + " (check did not confirm it is active)")

    guard = netguard.status()
    if guard.override or netguard.resolve_mode() == "audit":
        return replace(
            status,
            tier="dev_override",
            notes=f"{netguard.ALLOW_ENV}=1 is set: outbound calls are allowed and only logged. "
            f"Underlying OS status: {TIER_LABELS[status.tier]}. {status.notes}",
        )
    return status


_cache_lock = threading.Lock()
_cache: tuple[float, EnforcementStatus] | None = None


def detect_cached(max_age: float = CACHE_SECONDS, refresh: bool = False) -> EnforcementStatus:
    """detect(), reused for ``max_age`` seconds (the header badge runs on every page)."""
    global _cache
    with _cache_lock:
        now = time.monotonic()
        if refresh or _cache is None or now - _cache[0] > max_age:
            _cache = (now, detect())
        return _cache[1]
