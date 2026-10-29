"""Enforcement providers, with mocked commands and files. Never `enforced` on a failed check."""

import os
from pathlib import Path

import pytest

from localproof import enforcement, netguard
from localproof.enforcement import linux, macos, windows

EXE = r"C:\Users\me\AppData\Local\Programs\LocalProof\LocalProof.exe"

RULE_OK = f"""
Rule Name:                            LocalProof - block outbound
----------------------------------------------------------------------
Enabled:                              Yes
Direction:                            Out
Profiles:                             Domain,Private,Public
Grouping:
LocalIP:                              Any
RemoteIP:                             Any
Protocol:                             Any
Edge traversal:                       No
Program:                              {EXE}
InterfaceTypes:                       Any
Security:                             NotRequired
Rule source:                          Local Setting
Action:                               Block
Ok.
"""
PROFILES_ON = """
Domain Profile Settings:
----------------------------------------------------------------------
State                                 ON

Private Profile Settings:
----------------------------------------------------------------------
State                                 ON

Public Profile Settings:
----------------------------------------------------------------------
State                                 ON
Ok.
"""


def runner(rule=(0, RULE_OK), profiles=(0, PROFILES_ON)):
    def run(args):
        return rule if "rule" in args else profiles

    return run


def win(**kw):
    return windows.detect(run=runner(**kw), executable=EXE, frozen=True)


# --- Windows -------------------------------------------------------------------------


def test_windows_enforced_when_rule_matches_and_firewall_on():
    status = win()
    assert status.tier == "enforced" and status.active
    assert any("netsh advfirewall firewall show rule" in s for s in status.verify_steps)
    assert "msedgewebview2.exe" in status.notes  # honest about what the rule does not cover


def test_windows_missing_rule_is_guard_only():
    status = win(rule=(1, "No rules match the specified criteria.\n"))
    assert status.tier == "guard_only" and not status.active
    assert "missing" in status.notes and "netsh advfirewall firewall add rule" in status.notes


@pytest.mark.parametrize(
    "change",
    [("Enabled:                              Yes", "Enabled:                              No"),
     ("Direction:                            Out", "Direction:                            In"),
     ("Action:                               Block", "Action:                               Allow"),
     (EXE, r"C:\Other\LocalProof.exe")],
)
def test_windows_rule_that_does_not_block_this_exe_is_guard_only(change):
    status = win(rule=(0, RULE_OK.replace(*change)))
    assert status.tier == "guard_only"


def test_windows_program_path_compared_case_insensitively():
    assert win(rule=(0, RULE_OK.replace(EXE, EXE.upper()))).tier == "enforced"


def test_windows_one_matching_rule_among_several_is_enough():
    other = RULE_OK.replace(EXE, r"C:\Old\LocalProof.exe")
    assert win(rule=(0, other + "\n" + RULE_OK)).tier == "enforced"


def test_windows_firewall_profile_off_is_guard_only():
    off = PROFILES_ON.replace("State                                 ON\n\nPublic", "State                                 OFF\n\nPublic")
    status = win(profiles=(0, off))
    assert status.tier == "guard_only" and "Private" in status.notes


def test_windows_unreadable_profiles_is_guard_only():
    assert win(profiles=(0, "Zustand EIN\n")).tier == "guard_only"


def test_windows_non_english_netsh_is_guard_only():
    german = "Regelname:   LocalProof - block outbound\nAktiviert:   Ja\nRichtung:   Ausgehend\nAktion:   Blockieren\n"
    status = win(rule=(0, german))
    assert status.tier == "guard_only" and "could not be read" in status.notes


def test_windows_running_from_source_is_guard_only():
    status = windows.detect(run=runner(), executable=r"C:\Python312\python.exe", frozen=False)
    assert status.tier == "guard_only" and "from source" in status.notes


def test_windows_netsh_command_uses_rule_name():
    seen = []
    windows.detect(run=lambda a: seen.append(a) or (1, ""), executable=EXE, frozen=True)
    assert seen[0][:5] == ["netsh", "advfirewall", "firewall", "show", "rule"]
    assert f"name={windows.RULE_NAME}" in seen[0]


def test_parse_rules_splits_blocks():
    rules = windows.parse_rules(RULE_OK + "\n" + RULE_OK)
    assert len(rules) == 2 and rules[0]["action"] == "Block"


# --- Linux ---------------------------------------------------------------------------


def flatpak_info(tmp_path: Path, shared: str, extra: str = "") -> Path:
    path = tmp_path / "flatpak-info"
    path.write_text(
        "[Application]\nname=io.github.OWNER.LocalProof\nruntime=runtime/org.gnome.Platform/x86_64/48\n\n"
        f"[Instance]\napp-commit=abc123\n\n[Context]\nshared={shared}\nsockets=wayland;fallback-x11;\n{extra}"
    )
    return path


def test_flatpak_without_network_is_enforced(tmp_path):
    status = linux.detect(info_path=flatpak_info(tmp_path, "ipc;"), environ={})
    assert status.tier == "enforced" and status.active
    assert any("flatpak info --show-permissions" in s for s in status.verify_steps)


def test_flatpak_with_network_is_guard_only(tmp_path):
    status = linux.detect(info_path=flatpak_info(tmp_path, "network;ipc;"), environ={})
    assert status.tier == "guard_only" and "network" in status.notes


def test_flatpak_info_without_context_is_guard_only(tmp_path):
    path = tmp_path / "flatpak-info"
    path.write_text("[Application]\nname=x\n")
    assert linux.detect(info_path=path, environ={}).tier == "guard_only"


def test_corrupt_flatpak_info_is_guard_only(tmp_path):
    path = tmp_path / "flatpak-info"
    path.write_text("not an ini file [[[")
    assert linux.detect(info_path=path, environ={}).tier == "guard_only"


def test_appimage_is_guard_only(tmp_path):
    status = linux.detect(info_path=tmp_path / "missing", environ={"APPIMAGE": "/tmp/LocalProof.AppImage"})
    assert status.tier == "guard_only" and "AppImage" in status.mechanism


def test_plain_linux_is_guard_only(tmp_path):
    assert linux.detect(info_path=tmp_path / "missing", environ={}).tier == "guard_only"


# --- macOS ---------------------------------------------------------------------------


def test_macos_is_always_guard_only(tmp_path):
    lulu = tmp_path / "LuLu.app"
    lulu.mkdir()
    with_lulu = macos.detect(candidates={"LuLu": lulu, "Little Snitch": tmp_path / "nope"})
    assert with_lulu.tier == "guard_only" and not with_lulu.active
    assert "LuLu is installed" in with_lulu.notes and "cannot check" in with_lulu.notes
    without = macos.detect(candidates={"LuLu": tmp_path / "nope"})
    assert without.tier == "guard_only" and "install an outbound firewall" in without.notes


# --- detect() --------------------------------------------------------------------------


def test_detect_never_enforced_when_provider_raises():
    def broken():
        raise RuntimeError("netsh not found")

    status = enforcement.detect(provider=broken)
    assert status.tier == "guard_only" and "netsh not found" in status.notes


def test_detect_never_enforced_when_not_active():
    fake = enforcement.EnforcementStatus("enforced", "fake", False, (), "")
    assert enforcement.detect(provider=lambda: fake).tier == "guard_only"


def test_detect_reports_dev_override(monkeypatch):
    monkeypatch.setenv(netguard.ALLOW_ENV, "1")
    status = enforcement.detect(provider=lambda: windows.detect(run=runner(), executable=EXE, frozen=True))
    assert status.tier == "dev_override"
    assert "Enforced by the OS" in status.notes  # still says what the OS layer would do


def test_detect_uses_current_platform_provider():
    status = enforcement.detect()
    assert status.tier in ("enforced", "guard_only")


def test_detect_cached_reuses_then_refreshes(monkeypatch):
    calls = []
    monkeypatch.setattr(enforcement, "detect", lambda: calls.append(1) or enforcement.guard_only("x", "y"))
    enforcement.detect_cached(refresh=True)
    enforcement.detect_cached()
    assert len(calls) == 1
    enforcement.detect_cached(refresh=True)
    assert len(calls) == 2
