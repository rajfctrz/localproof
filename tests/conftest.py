import os
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO_ROOT / "sample_data" / "monthly_cashflow.csv"
NETGUARD_TESTS = "test_netguard.py"
# Attempts made while a netguard test runs are deliberate; everything else is a finding.
_expected_attempts: set[int] = set()


def pytest_configure(config):
    """Run the whole suite with netguard enforcing, like the shipped app.

    User folders point at a throwaway dir first, so even the guard's own
    session log never lands in the developer's real profile.
    """
    os.environ["LOCALPROOF_HOME"] = tempfile.mkdtemp(prefix="localproof-session-")
    from localproof import netguard

    netguard.install(mode="enforcing", label="pytest")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    from localproof import netguard

    before = len(netguard.attempts())
    yield
    if item.path.name == NETGUARD_TESTS:
        _expected_attempts.update(id(a) for a in netguard.attempts()[before:])


def _unexpected_attempts():
    from localproof import netguard

    return [a for a in netguard.attempts() if id(a) not in _expected_attempts]


def pytest_terminal_summary(terminalreporter):
    unexpected = _unexpected_attempts()
    terminalreporter.write_sep("-", f"netguard: {len(unexpected)} unexpected outbound attempt(s)")
    for attempt in unexpected:
        terminalreporter.write_line(f"{attempt.operation} {attempt.host}:{attempt.port}")
        for frame in attempt.stack:
            terminalreporter.write_line(f"    {frame}")


def pytest_sessionfinish(session, exitstatus):
    if _unexpected_attempts() and exitstatus == 0:
        session.exitstatus = 1


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point every user folder at a temp dir so tests never touch real data."""
    from localproof import paths

    home = tmp_path / "localproof-home"
    monkeypatch.setenv(paths.HOME_ENV, str(home))
    return home


@pytest.fixture
def app(isolated_home):
    from app import create_app

    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()
