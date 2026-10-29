import ast
import http.client
import socket
from pathlib import Path

import pytest

from localproof import launcher


def test_netguard_is_installed_before_any_other_import():
    tree = ast.parse(Path(launcher.__file__).read_text())
    body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    first_three = [ast.unparse(n) for n in body[:3]]
    assert first_three[0] == "import sys"
    assert first_three[1] == "from localproof import netguard"
    assert first_three[2].startswith("_GUARD = netguard.install(")


@pytest.fixture
def running():
    server = launcher.start_server(record_requests=True)
    yield server
    server.stop()


def test_server_binds_loopback_only_on_a_free_port(running):
    host, port = running.server.socket.getsockname()[:2]
    assert host == "127.0.0.1"
    assert port == running.port and port > 0


def test_health_and_forecast_served(running):
    assert launcher.wait_for_health(running.port)
    status, page = launcher._get(running.port, "/forecast/sample?horizon=6")
    assert status == 200 and "Next 6 months" in page
    assert ("/health", "") in running.requests


def test_serve_smoke_passes(running):
    assert launcher.wait_for_health(running.port)
    assert launcher.serve_smoke(running) == launcher.EXIT_OK


def test_stop_closes_the_listening_socket(running):
    port = running.port
    assert launcher.wait_for_health(port)
    running.stop()
    assert not running.thread.is_alive()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_wait_for_health_times_out_on_closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert launcher.wait_for_health(port, timeout=0.5) is False


def test_linux_uses_gtk_explicitly(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    assert launcher._gui_backend() == "gtk"
    assert "gir1.2-webkit2-4.1" in launcher._missing_gui_help(RuntimeError("no gtk"))
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    assert launcher._gui_backend() is None


def test_version_flag(capsys):
    assert launcher.main(["--version"]) == launcher.EXIT_OK
    assert capsys.readouterr().out.startswith("LocalProof ")


def test_unknown_args_ignored():
    assert launcher._parse_args(["-psn_0_12345", "--version"]).version
