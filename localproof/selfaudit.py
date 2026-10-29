"""--self-audit: a plain-text report an IT or security reviewer can run themselves.

Exit codes:
  0  OS-level enforcement confirmed and the Python guard is active
  2  guard only: the Python guard is active, but there is no OS-level enforcement
  3  dev override: LOCALPROOF_ALLOW_NETWORK=1 is set, outbound is allowed
  1  the Python guard is not active, or the audit itself failed
"""

from __future__ import annotations

import platform
import sys
from importlib import metadata
from typing import Any, TextIO

from localproof import __version__, buildinfo, enforcement, netguard, paths

EXIT_ENFORCED = 0
EXIT_GUARD_INACTIVE = 1
EXIT_GUARD_ONLY = 2
EXIT_DEV_OVERRIDE = 3
APP_SESSION_LABEL = "app"
LABEL_WIDTH = 24
RESULT_TEXT = {
    EXIT_ENFORCED: "ENFORCED: OS-level blocking confirmed, Python guard active",
    EXIT_GUARD_ONLY: "GUARD ONLY: Python guard active, no OS-level enforcement",
    EXIT_DEV_OVERRIDE: "DEV OVERRIDE: outbound connections are allowed (LOCALPROOF_ALLOW_NETWORK=1)",
    EXIT_GUARD_INACTIVE: "GUARD INACTIVE: the Python network guard is not running",
}


def exit_code(status: enforcement.EnforcementStatus, guard: netguard.GuardStatus) -> int:
    if status.tier == "dev_override" or guard.override:
        return EXIT_DEV_OVERRIDE
    if not guard.active:
        return EXIT_GUARD_INACTIVE
    return EXIT_ENFORCED if status.tier == "enforced" else EXIT_GUARD_ONLY


def last_app_session(records: list[dict[str, Any]], current: str | None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The most recent app session (not this audit) and its blocked attempts."""
    starts = [r for r in records if r.get("event") == "session_start" and r.get("label") == APP_SESSION_LABEL and r.get("session") != current]
    if not starts:
        return None, []
    session = starts[-1]
    blocked = [r for r in records if r.get("event") == "attempt" and r.get("session") == session["session"] and not r.get("allowed")]
    return session, blocked


def firewall_rule_line() -> str:
    if sys.platform != "win32":
        return "not applicable on this OS"
    from localproof.enforcement import windows

    return "present" if windows.rule_present() else "MISSING"


def installed_packages() -> list[str]:
    names = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            names[name.lower()] = f"{name}=={dist.version}"
    return [names[k] for k in sorted(names)]


def _line(out: TextIO, label: str, value: object) -> None:
    print(f"{label + ':':<{LABEL_WIDTH}}{value}", file=out)


def run(out: TextIO) -> int:
    guard = netguard.status()
    status = enforcement.detect()
    identity = buildinfo.executable_identity()
    code = exit_code(status, guard)

    print("LocalProof self-audit", file=out)
    print("=" * 60, file=out)
    _line(out, "Version", __version__)
    _line(out, "Built", buildinfo.build_timestamp())
    _line(out, "Commit", buildinfo.build_commit())
    _line(out, identity.label, identity.value)
    if identity.path:
        _line(out, "Executable path", identity.path)
    _line(out, "Platform", platform.platform())
    _line(out, "Python", platform.python_version())
    print(file=out)

    _line(out, "Network guard", "active (enforcing)" if guard.active else f"NOT enforcing (mode: {guard.mode})")
    _line(out, "Enforcement tier", f"{status.tier} - {status.label}")
    _line(out, "OS mechanism", status.mechanism)
    _line(out, "OS enforcement active", "yes" if status.active and status.tier == "enforced" else "no")
    _line(out, "Firewall rule", firewall_rule_line())
    _line(out, "Notes", status.notes)
    if status.verify_steps:
        print("Verify it yourself:", file=out)
        for step in status.verify_steps:
            print(f"  {step}", file=out)
    print(file=out)

    data = paths.data_dir()
    _line(out, "Data folder", data)
    _line(out, "Data folder size", f"{paths.folder_size(data):,} bytes")
    _line(out, "Logs", paths.log_dir())
    _line(out, "Settings", paths.config_dir())
    print(file=out)

    session, blocked = last_app_session(netguard.read_log(), guard.session)
    if session is None:
        print("Last app session: none recorded yet", file=out)
    else:
        print(f"Last app session: {session['session']} started {session['timestamp']} (mode: {session['mode']})", file=out)
        print(f"Blocked outbound attempts in that session: {len(blocked)}", file=out)
        for record in blocked:
            origin = netguard.origin_of(record.get("stack") or [])
            print(f"  {record['timestamp']}  {record['operation']} {record['host']}:{record['port']}  <- {origin}", file=out)
    print(file=out)

    packages = installed_packages()
    print(f"Python packages ({len(packages)}):", file=out)
    if packages:
        for package in packages:
            print(f"  {package}", file=out)
    else:
        print("  (package metadata not bundled in this build)", file=out)
    print(file=out)
    print(f"Result: {RESULT_TEXT[code]} (exit code {code})", file=out)
    return code
