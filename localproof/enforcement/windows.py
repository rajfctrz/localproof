"""Windows: per-app outbound block via a Windows Firewall rule."""

from __future__ import annotations

import ntpath
import subprocess
import sys
from typing import Callable

from . import EnforcementStatus, guard_only

RULE_NAME = "LocalProof - block outbound"
NETSH_TIMEOUT_S = 10
SHOW_RULE = ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}", "verbose"]
SHOW_PROFILES = ["netsh", "advfirewall", "show", "allprofiles", "state"]
VERIFY_STEPS = (
    f'netsh advfirewall firewall show rule name="{RULE_NAME}" verbose',
    "netsh advfirewall show allprofiles state",
    'LocalProof.exe --self-audit   (exit code 0 = enforced)',
)
ADD_RULE_HELP = (
    "To add it, run in an administrator PowerShell: "
    f'netsh advfirewall firewall add rule name="{RULE_NAME}" dir=out action=block '
    'program="<install folder>\\LocalProof.exe" enable=yes'
)

Runner = Callable[[list[str]], tuple[int, str]]


def _run(args: list[str]) -> tuple[int, str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=NETSH_TIMEOUT_S, creationflags=flags, errors="replace"
    )
    return proc.returncode, proc.stdout


def parse_rules(output: str) -> list[dict[str, str]]:
    """Split `netsh ... show rule verbose` output into one dict per rule."""
    rules: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip() or set(line.strip()) == {"-"}:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        if key == "rule name" and current:
            rules.append(current)
            current = {}
        current[key] = value.strip()
    if current:
        rules.append(current)
    return rules


def _same_path(a: str, b: str) -> bool:
    # ntpath, not os.path: these are Windows paths, compared case-insensitively on any host.
    return ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b))


def _rule_blocks(rule: dict[str, str], executable: str) -> bool:
    return (
        rule.get("enabled", "").lower() == "yes"
        and rule.get("direction", "").lower() == "out"
        and rule.get("action", "").lower() == "block"
        and _same_path(rule.get("program", ""), executable)
    )


def _profiles_off(output: str) -> list[str] | None:
    """Profiles whose firewall is off; None if the output could not be read."""
    profile, states, off = None, 0, []
    for line in output.splitlines():
        text = line.strip()
        if text.lower().endswith("profile settings:"):
            profile = text.split()[0]
        elif text.lower().startswith("state"):
            states += 1
            if text.split()[-1].upper() != "ON":
                off.append(profile or "unknown")
    return off if states else None


def detect(run: Runner = _run, executable: str | None = None, frozen: bool | None = None) -> EnforcementStatus:
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    mechanism = f"Windows Firewall rule '{RULE_NAME}'"

    code, output = run(SHOW_RULE)
    rules = parse_rules(output) if code == 0 else []
    if code != 0 or not rules:
        return guard_only(mechanism, f"The firewall rule is missing. {ADD_RULE_HELP}", VERIFY_STEPS)
    if not any("enabled" in r and "program" in r for r in rules):
        return guard_only(
            mechanism,
            "The rule exists but netsh output could not be read (non-English Windows?). "
            "Check it manually with the commands below.",
            VERIFY_STEPS,
        )
    if not frozen:
        return guard_only(
            mechanism,
            "Running from source: the rule applies to the installed LocalProof.exe, not to this Python interpreter.",
            VERIFY_STEPS,
        )
    if not any(_rule_blocks(r, executable) for r in rules):
        programs = ", ".join(r.get("program", "?") for r in rules)
        return guard_only(
            mechanism,
            f"A rule with this name exists but does not block outbound traffic for {executable} "
            f"(rule program: {programs}; it must be enabled, direction Out, action Block).",
            VERIFY_STEPS,
        )

    code, profiles = run(SHOW_PROFILES)
    off = _profiles_off(profiles) if code == 0 else None
    if off is None:
        return guard_only(mechanism, "Could not read the Windows Firewall profile state.", VERIFY_STEPS)
    if off:
        return guard_only(
            mechanism,
            f"The rule is present, but Windows Firewall is off for: {', '.join(off)}. It only applies where the firewall is on.",
            VERIFY_STEPS,
        )
    return EnforcementStatus(
        tier="enforced",
        mechanism=mechanism,
        active=True,
        verify_steps=VERIFY_STEPS,
        notes=(
            "Windows Firewall blocks all outbound traffic from LocalProof.exe, including its native "
            "extensions. The WebView2 runtime runs as separate msedgewebview2.exe processes that this "
            "rule does not cover; see SECURITY.md."
        ),
    )
