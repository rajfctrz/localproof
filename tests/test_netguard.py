"""netguard: loopback allowed, everything else blocked and recorded.

The session-wide guard from conftest is already enforcing. External targets
use the TEST-NET-1 range (192.0.2.0/24) and example.com so that even a broken
guard could not reach a real service from these tests.
"""

import http.client
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

from localproof import netguard
from localproof.netguard import OutboundBlockedError
from tests.conftest import REPO_ROOT

EXTERNAL_IP = "192.0.2.1"
EXTERNAL_HOST = "example.com"


@pytest.fixture(autouse=True)
def enforcing_guard():
    netguard.install(mode="enforcing", label="pytest")
    yield
    netguard.install(mode="enforcing", label="pytest")


@pytest.fixture
def local_http_server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            body = b"local ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def new_attempts(before: int):
    return netguard.attempts()[before:]


# --- classification -------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.8.9.10", "::1", "[::1]", "localhost", "LOCALHOST", "localhost.", "::ffff:127.0.0.1", "::1%lo0", b"127.0.0.1"],
)
def test_loopback_hosts_recognised(host):
    assert netguard.is_loopback_host(host)


@pytest.mark.parametrize(
    "host",
    ["192.0.2.1", "10.0.0.1", "0.0.0.0", "::", "2001:db8::1", "example.com", "localhost.evil.com", "127.0.0.1.evil.com", "", None, 80],
)
def test_non_loopback_hosts_rejected(host):
    assert not netguard.is_loopback_host(host)


# --- loopback works through every layer ------------------------------------------


def test_loopback_socket_connect_allowed(local_http_server):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("127.0.0.1", local_http_server))


def test_loopback_create_connection_allowed(local_http_server):
    socket.create_connection(("localhost", local_http_server), timeout=2).close()


def test_loopback_urllib_allowed(local_http_server):
    with urllib.request.urlopen(f"http://127.0.0.1:{local_http_server}/", timeout=2) as resp:
        assert resp.read() == b"local ok"


def test_loopback_http_client_allowed(local_http_server):
    conn = http.client.HTTPConnection("127.0.0.1", local_http_server, timeout=2)
    conn.request("GET", "/")
    assert conn.getresponse().status == 200
    conn.close()


def test_loopback_requests_allowed(local_http_server):
    requests = pytest.importorskip("requests")
    assert requests.get(f"http://127.0.0.1:{local_http_server}/", timeout=2).text == "local ok"


def test_loopback_getaddrinfo_allowed():
    assert socket.getaddrinfo("localhost", 80)
    assert socket.getaddrinfo(None, 0, socket.AF_INET, socket.SOCK_STREAM, 0, socket.AI_PASSIVE)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="no AF_UNIX on this OS")
def test_unix_socketpair_allowed():
    a, b = socket.socketpair()
    a.sendall(b"x")
    assert b.recv(1) == b"x"
    a.close()
    b.close()


# --- external is blocked through every layer --------------------------------------


def test_socket_connect_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        with pytest.raises(OutboundBlockedError):
            s.connect((EXTERNAL_IP, 80))


def test_socket_connect_ex_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OutboundBlockedError):
            s.connect_ex((EXTERNAL_IP, 80))


def test_ipv6_connect_blocked():
    if not socket.has_ipv6:
        pytest.skip("no IPv6")
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        with pytest.raises(OutboundBlockedError):
            s.connect(("2001:db8::1", 80, 0, 0))


def test_udp_sendto_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(OutboundBlockedError):
            s.sendto(b"x", (EXTERNAL_IP, 53))


def test_create_connection_blocked():
    with pytest.raises(OutboundBlockedError):
        socket.create_connection((EXTERNAL_HOST, 443), timeout=1)


def test_getaddrinfo_blocked():
    with pytest.raises(OutboundBlockedError):
        socket.getaddrinfo(EXTERNAL_HOST, 443)


def test_gethostbyname_blocked():
    with pytest.raises(OutboundBlockedError):
        socket.gethostbyname(EXTERNAL_HOST)


def test_urllib_blocked():
    with pytest.raises(urllib.error.URLError) as info:
        urllib.request.urlopen(f"https://{EXTERNAL_HOST}/", timeout=1)
    assert isinstance(info.value.reason, OutboundBlockedError)


def test_http_client_blocked():
    conn = http.client.HTTPSConnection(EXTERNAL_HOST, timeout=1)
    with pytest.raises(OutboundBlockedError):
        conn.request("GET", "/")


def test_requests_blocked():
    requests = pytest.importorskip("requests")
    with pytest.raises(requests.exceptions.ConnectionError) as info:
        requests.get(f"https://{EXTERNAL_HOST}/", timeout=1)
    assert "netguard blocked" in str(info.value)


def test_origin_points_at_third_party_library_not_stdlib():
    requests = pytest.importorskip("requests")
    before = len(netguard.attempts())
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(f"https://{EXTERNAL_HOST}/", timeout=1)
    attempt = new_attempts(before)[0]
    assert "site-packages" in attempt.origin and "urllib3" in attempt.origin


def test_blocked_error_is_an_oserror_with_clear_message():
    err = OutboundBlockedError("connect", EXTERNAL_IP, 80)
    assert isinstance(err, OSError)
    assert "192.0.2.1:80" in str(err)


# --- recording -------------------------------------------------------------------


def test_attempt_is_recorded_in_memory_and_log():
    before = len(netguard.attempts())
    with pytest.raises(OutboundBlockedError):
        socket.create_connection((EXTERNAL_HOST, 443), timeout=1)
    [attempt] = new_attempts(before)
    assert attempt.operation == "create_connection"
    assert (attempt.host, attempt.port) == (EXTERNAL_HOST, "443")
    assert attempt.allowed is False
    assert any("test_attempt_is_recorded_in_memory_and_log" in frame for frame in attempt.stack)
    assert not any(frame.startswith(netguard.__file__ + ":") for frame in attempt.stack)
    assert "socket.py" not in attempt.origin  # origin skips the stdlib frames

    records = netguard.read_log()
    assert records[-1]["event"] == "attempt"
    assert records[-1]["host"] == EXTERNAL_HOST


def test_loopback_is_not_recorded(local_http_server):
    before = len(netguard.attempts())
    socket.create_connection(("127.0.0.1", local_http_server), timeout=2).close()
    assert new_attempts(before) == ()


def test_install_writes_session_start(isolated_home):
    state = netguard.install(mode="enforcing", label="pytest")
    record = netguard.read_log()[-1]
    assert record["event"] == "session_start"
    assert record["session"] == state.session
    assert state.log_path and str(isolated_home) in state.log_path


def test_logging_failure_does_not_break_the_guard(monkeypatch):
    monkeypatch.setattr(netguard, "_resolve_log_path", lambda: None)
    with pytest.raises(OutboundBlockedError):
        socket.getaddrinfo(EXTERNAL_HOST, 443)


# --- modes and the dev override -------------------------------------------------


def test_env_override_selects_audit_mode(monkeypatch):
    monkeypatch.setenv(netguard.ALLOW_ENV, "1")
    assert netguard.resolve_mode() == "audit"
    monkeypatch.setenv(netguard.ALLOW_ENV, "0")
    assert netguard.resolve_mode() == "enforcing"
    monkeypatch.delenv(netguard.ALLOW_ENV)
    assert netguard.resolve_mode() == "enforcing"


def test_audit_mode_allows_but_records(monkeypatch):
    monkeypatch.setenv(netguard.ALLOW_ENV, "1")
    status = netguard.install()
    assert status.override and not status.active
    calls = []
    # Stub the real resolver so the test never touches the network.
    monkeypatch.setitem(netguard._state.originals, "getaddrinfo", lambda *a, **k: calls.append(a) or [])
    before = len(netguard.attempts())
    assert socket.getaddrinfo(EXTERNAL_HOST, 443) == []
    assert calls
    [attempt] = new_attempts(before)
    assert attempt.allowed is True


def test_uninstall_restores_socket_functions():
    netguard.uninstall()
    assert socket.getaddrinfo is netguard._state.originals.get("getaddrinfo", socket.getaddrinfo)
    assert socket.socket.connect.__name__ == "connect"
    assert netguard.status().mode == "off"


# --- third-party libraries under the guard -----------------------------------------

LIBRARY_PROBE = r"""
import json, sys
from localproof import netguard
netguard.install(mode="enforcing", label="library-probe")
import numpy, pandas, statsmodels.api, openpyxl
from app import forecast
monthly = forecast.load_cashflow_csv(sys.argv[1])
result = forecast.forecast_cashflow(monthly, 12)
forecast.write_excel(result, __import__("pathlib").Path(sys.argv[2]) / "probe.xlsx")
print(json.dumps([a.__dict__ for a in netguard.attempts()], default=list))
"""


def test_data_libraries_make_no_outbound_attempts(tmp_path):
    """Fresh interpreter, guard first, then import and exercise pandas/numpy/statsmodels/openpyxl."""
    env = {**os.environ, "LOCALPROOF_HOME": str(tmp_path / "home")}
    env.pop(netguard.ALLOW_ENV, None)
    proc = subprocess.run(
        [sys.executable, "-c", LIBRARY_PROBE, str(REPO_ROOT / "sample_data" / "monthly_cashflow.csv"), str(tmp_path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    attempts = json.loads(proc.stdout.strip().splitlines()[-1])
    assert attempts == [], f"outbound attempts from data libraries: {attempts}"
