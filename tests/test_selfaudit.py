import errno
import io
import socket
import sys

import pytest

from localproof import enforcement, launcher, netguard, probe, selfaudit
from localproof.enforcement import windows


def audit(monkeypatch, status):
    monkeypatch.setattr(enforcement, "detect", lambda: status)
    out = io.StringIO()
    code = selfaudit.run(out)
    return code, out.getvalue()


ENFORCED = enforcement.EnforcementStatus("enforced", "Windows Firewall rule", True, ("netsh ...",), "ok")
GUARD_ONLY = enforcement.guard_only("none", "only the guard")


def test_report_lists_every_required_section(monkeypatch):
    code, text = audit(monkeypatch, GUARD_ONLY)
    for heading in ("Version:", "Built:", "Executable:", "Network guard:", "Enforcement tier:",
                    "Firewall rule:", "Data folder:", "Data folder size:", "Last app session:",
                    "Python packages (", "Result:"):
        assert heading in text, heading
    assert "flask==" in text.lower() and "pandas==" in text.lower()


def test_long_labels_keep_a_space_before_the_value():
    import io

    out = io.StringIO()
    selfaudit._line(out, "SHA-256 of LocalProof-0.1.0-x86_64.AppImage", "abc")
    assert out.getvalue() == "SHA-256 of LocalProof-0.1.0-x86_64.AppImage: abc\n"


def test_exit_0_only_when_enforced_and_guard_active(monkeypatch):
    assert audit(monkeypatch, ENFORCED)[0] == selfaudit.EXIT_ENFORCED


def test_guard_only_has_distinct_exit_code(monkeypatch):
    code, text = audit(monkeypatch, GUARD_ONLY)
    assert code == selfaudit.EXIT_GUARD_ONLY == 2
    assert "GUARD ONLY" in text


def test_guard_inactive_is_exit_1_even_if_os_enforced(monkeypatch):
    netguard.uninstall()
    try:
        code, text = audit(monkeypatch, ENFORCED)
    finally:
        netguard.install(mode="enforcing", label="pytest")
    assert code == selfaudit.EXIT_GUARD_INACTIVE and "NOT enforcing" in text


def test_dev_override_exit_3(monkeypatch):
    override = enforcement.EnforcementStatus("dev_override", "x", False, (), "override")
    assert audit(monkeypatch, override)[0] == selfaudit.EXIT_DEV_OVERRIDE


def test_last_app_session_excludes_current_audit_and_allowed_attempts():
    records = [
        {"event": "session_start", "session": "old", "label": "app", "mode": "enforcing", "timestamp": "t0"},
        {"event": "attempt", "session": "old", "allowed": False, "host": "a", "port": "1", "operation": "connect", "timestamp": "t", "stack": []},
        {"event": "session_start", "session": "app2", "label": "app", "mode": "enforcing", "timestamp": "t1"},
        {"event": "attempt", "session": "app2", "allowed": False, "host": "b", "port": "2", "operation": "connect", "timestamp": "t", "stack": []},
        {"event": "attempt", "session": "app2", "allowed": True, "host": "c", "port": "3", "operation": "connect", "timestamp": "t", "stack": []},
        {"event": "session_start", "session": "me", "label": "self-audit", "mode": "enforcing", "timestamp": "t2"},
    ]
    session, blocked = selfaudit.last_app_session(records, current="me")
    assert session["session"] == "app2"
    assert [r["host"] for r in blocked] == ["b"]


@pytest.mark.expected_outbound
def test_report_shows_blocked_attempts_from_last_app_session(monkeypatch):
    netguard.install(mode="enforcing", label="app")
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 443), timeout=1)
    netguard.install(mode="enforcing", label="self-audit")
    _code, text = audit(monkeypatch, GUARD_ONLY)
    assert "Blocked outbound attempts in that session: 1" in text
    assert "example.com:443" in text
    netguard.install(mode="enforcing", label="pytest")


def test_firewall_rule_line_not_applicable_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert selfaudit.firewall_rule_line() == "not applicable on this OS"


def test_windows_rule_present_helper():
    assert windows.rule_present(run=lambda a: (0, "Rule Name: LocalProof - block outbound\nEnabled: Yes\n"))
    assert not windows.rule_present(run=lambda a: (1, "No rules match the specified criteria."))


def test_launcher_self_audit_flag(capsys, monkeypatch):
    monkeypatch.setattr(enforcement, "detect", lambda: GUARD_ONLY)
    assert launcher.main(["--self-audit"]) == selfaudit.EXIT_GUARD_ONLY
    assert "LocalProof self-audit" in capsys.readouterr().out


# --- probe ---------------------------------------------------------------------------


@pytest.mark.expected_outbound
def test_probe_reports_guard_block():
    result = probe.probe("example.com:443")
    assert result.outcome == "blocked_by_guard" and result.exit_code == probe.EXIT_BLOCKED


@pytest.mark.parametrize(
    "exc, outcome",
    [
        (OSError(errno.EACCES, "Permission denied"), "blocked_by_os"),
        (OSError(errno.EPERM, "Operation not permitted"), "blocked_by_os"),
        (OSError(errno.ENETUNREACH, "Network is unreachable"), "no_network"),
        (socket.gaierror(-3, "Temporary failure in name resolution"), "no_network"),
        (TimeoutError("timed out"), "inconclusive"),
    ],
)
def test_probe_classifies_os_errors(exc, outcome):
    assert probe.classify(exc).outcome == outcome


def test_probe_classifies_windows_firewall_error():
    exc = OSError(errno.EACCES, "forbidden by its access permissions")
    exc.winerror = probe.WSAEACCES
    assert probe.classify(exc).outcome == "blocked_by_os"


def test_probe_connected_is_exit_4(monkeypatch):
    class FakeSock:
        def close(self):
            pass

    monkeypatch.setattr(probe.socket, "create_connection", lambda *a, **k: FakeSock())
    result = probe.probe("example.com:443")
    assert result.outcome == "connected" and result.exit_code == probe.EXIT_CONNECTED == 4


@pytest.mark.parametrize("bad", ["example.com", ":443", "host:abc"])
def test_probe_rejects_bad_target(bad):
    with pytest.raises(ValueError):
        probe.parse_target(bad)


def test_launcher_probe_bad_target_is_error():
    assert launcher.main(["--probe-outbound", "nope"]) == launcher.EXIT_FAILURE
