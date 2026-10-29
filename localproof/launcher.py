"""Desktop entry point: netguard -> local server thread -> native window.

netguard is installed before anything else is imported, so libraries that
capture socket functions at import time get the guarded versions.
"""

import sys

from localproof import netguard

_GUARD = netguard.install(
    label="self-audit" if "--self-audit" in sys.argv else "app",
)

import argparse  # noqa: E402
import os  # noqa: E402
import http.client  # noqa: E402
import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from localproof import __version__, paths  # noqa: E402

APP_TITLE = "LocalProof · Cash Flow Forecast"
HOST = "127.0.0.1"
HEALTH_TIMEOUT_S = 20.0
HEALTH_POLL_S = 0.1
WINDOW_LOAD_TIMEOUT_S = 30.0
WINDOW_SIZE = (1200, 860)
WINDOW_MIN_SIZE = (720, 560)
SERVER_THREADS = 4
SERVER_POLL_S = 0.25

EXIT_OK = 0
EXIT_FAILURE = 1

log = logging.getLogger("localproof")


@dataclass(frozen=True)
class RunningServer:
    server: object
    thread: threading.Thread
    stopping: threading.Event
    port: int
    requests: list[tuple[str, str]]  # (path, user agent), filled only when recording

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    def stop(self) -> None:
        self.stopping.set()
        self.thread.join(timeout=5)


def _serve_until_stopped(server, stopping: threading.Event) -> None:
    # Same loop as waitress's server.run(), but checks a stop flag between polls
    # and closes sockets on this thread, so shutdown never races select().
    while not stopping.is_set() and server._map:
        server.asyncore.loop(timeout=SERVER_POLL_S, map=server._map, count=1)
    server.close()
    server.task_dispatcher.shutdown()


class _RequestRecorder:
    """WSGI middleware that notes which paths the WebView fetched (smoke tests)."""

    def __init__(self, app, sink: list[tuple[str, str]]) -> None:
        self.app = app
        self.sink = sink

    def __call__(self, environ, start_response):
        self.sink.append((environ.get("PATH_INFO", ""), environ.get("HTTP_USER_AGENT", "")))
        return self.app(environ, start_response)


def _configure_logging() -> None:
    handler = logging.FileHandler(paths.log_dir() / "localproof.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def start_server(record_requests: bool = False) -> RunningServer:
    """Serve the Flask app on 127.0.0.1 with an OS-assigned free port."""
    from waitress import create_server

    from app import create_app

    requests: list[tuple[str, str]] = []
    wsgi_app = create_app()
    if record_requests:
        wsgi_app = _RequestRecorder(wsgi_app, requests)
    server = create_server(wsgi_app, host=HOST, port=0, threads=SERVER_THREADS)
    stopping = threading.Event()
    thread = threading.Thread(
        target=_serve_until_stopped, args=(server, stopping), name="waitress", daemon=True
    )
    thread.start()
    return RunningServer(
        server=server, thread=thread, stopping=stopping, port=int(server.effective_port), requests=requests
    )


def wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conn = http.client.HTTPConnection(HOST, port, timeout=1)
        try:
            conn.request("GET", "/health")
            if conn.getresponse().status == 200:
                return True
        except OSError:
            time.sleep(HEALTH_POLL_S)
        finally:
            conn.close()
    return False


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection(HOST, port, timeout=10)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        conn.close()


def _gui_backend() -> str | None:
    # Be explicit on Linux so a missing GTK stack is reported, not silently swapped for Qt.
    return "gtk" if sys.platform.startswith("linux") else None


def _missing_gui_help(exc: Exception) -> str:
    if sys.platform.startswith("linux"):
        return (
            f"Could not open the native window ({exc}).\n"
            "pywebview needs GTK 3 + WebKit2GTK 4.1 with Python bindings. On Debian/Ubuntu:\n"
            "  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libgirepository1.0-dev\n"
            "  pip install PyGObject\n"
            "Or run the browser dev mode instead: flask --app app run"
        )
    if sys.platform == "win32":
        return (
            f"Could not open the native window ({exc}).\n"
            "pywebview needs the Microsoft Edge WebView2 Runtime: "
            "install it from Microsoft, then start LocalProof again."
        )
    return f"Could not open the native window ({exc})."


def _create_window(url: str):
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True  # "Save a copy" of an Excel export
    return webview, webview.create_window(
        APP_TITLE, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1], min_size=WINDOW_MIN_SIZE
    )


def run_window(running: RunningServer) -> int:
    try:
        webview, _window = _create_window(running.url)
        # private_mode: no cookies or web storage persisted by the WebView.
        webview.start(gui=_gui_backend(), private_mode=True)
    except Exception as exc:  # noqa: BLE001 - surface any GUI failure with guidance
        print(_missing_gui_help(exc), file=sys.stderr)
        log.exception("window failed")
        return EXIT_FAILURE
    return EXIT_OK


# Pages the smoke test navigates to, and what the native WebView must fetch for each.
SMOKE_INDEX_ASSETS = ("/", "/static/css/app.css")
SMOKE_PAGES = (
    ("/forecast/sample?horizon=12", ("/forecast/sample", "/static/vendor/chart.umd.js", "/static/js/forecast-chart.js")),
    ("/trust/", ("/trust/",)),
)
# Every platform WebView (WKWebView, WebView2, WebKitGTK) identifies as AppleWebKit.
WEBVIEW_UA_MARKER = "AppleWebKit"


def _wait_for_paths(running: RunningServer, wanted: tuple[str, ...], timeout: float) -> list[str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        seen = {path for path, ua in running.requests if WEBVIEW_UA_MARKER in ua}
        missing = [p for p in wanted if p not in seen]
        if not missing:
            return []
        time.sleep(HEALTH_POLL_S)
    return missing


def window_smoke(running: RunningServer) -> int:
    """Open the real window, check the WebView fetched each page's assets, close it.

    Checked from the server side because the page's CSP (script-src 'self')
    rightly blocks the eval() that pywebview's evaluate_js relies on.
    """
    result: dict[str, object] = {}

    def check(window) -> None:
        try:
            if not window.events.loaded.wait(WINDOW_LOAD_TIMEOUT_S):
                result["error"] = "index page did not finish loading"
                return
            missing = _wait_for_paths(running, SMOKE_INDEX_ASSETS, WINDOW_LOAD_TIMEOUT_S)
            for path, assets in SMOKE_PAGES:
                if missing:
                    break
                # pywebview sets `loaded` only after its JS bridge injection finishes;
                # waiting for it each time means we never destroy the window mid-injection.
                window.events.loaded.clear()
                window.load_url(running.url.rstrip("/") + path)
                missing = _wait_for_paths(running, assets, WINDOW_LOAD_TIMEOUT_S)
                if not missing and not window.events.loaded.wait(WINDOW_LOAD_TIMEOUT_S):
                    missing = [f"(load event for {path})"]
            if missing:
                result["error"] = f"WebView never requested {missing}"
        except Exception as exc:  # noqa: BLE001
            result["error"] = repr(exc)
        finally:
            window.destroy()

    try:
        webview, window = _create_window(running.url)
        webview.start(check, window, gui=_gui_backend(), private_mode=True)
    except Exception as exc:  # noqa: BLE001
        print(_missing_gui_help(exc), file=sys.stderr)
        return EXIT_FAILURE

    agents = sorted({ua for _, ua in running.requests})
    print(f"WebView fetched {len(running.requests)} resources; user agent(s): {agents}")
    if "error" in result:
        print(f"window smoke FAILED: {result['error']}", file=sys.stderr)
        return EXIT_FAILURE
    print("window smoke ok: index, forecast and Trust Panel pages rendered in the native window")
    return EXIT_OK


def serve_smoke(running: RunningServer) -> int:
    """Headless check for CI: health, a forecast page, and the guard state."""
    status, _ = _get(running.port, "/health")
    page_status, page = _get(running.port, "/forecast/sample?horizon=12")
    ok = status == 200 and page_status == 200 and "Next 12 months" in page
    print(f"serve smoke {'ok' if ok else 'FAILED'}: health={status} forecast={page_status} guard={_GUARD.mode}")
    return EXIT_OK if ok else EXIT_FAILURE


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="LocalProof", description="Local-only desktop app.")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--self-audit", action="store_true", help="print a verification report and exit (0 = enforced, 2 = guard only)")
    parser.add_argument(
        "--probe-outbound",
        nargs="?",
        const="example.com:443",
        metavar="HOST:PORT",
        help="try one TCP connection and report what stopped it (use with LOCALPROOF_ALLOW_NETWORK=1 to test the OS layer)",
    )
    parser.add_argument("--window-smoke", action="store_true", help="open the window, check it loads, close (dev/CI)")
    parser.add_argument("--serve-smoke", action="store_true", help="start the server without a window, check it, exit (CI)")
    # PyInstaller on macOS can pass -psn_* when launched from Finder; ignore unknown args.
    args, _unknown = parser.parse_known_args(argv)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.version or args.self_audit or args.probe_outbound:
        from localproof import winconsole

        winconsole.ensure_stdio()
    if args.version:
        print(f"LocalProof {__version__}")
        return EXIT_OK
    if args.self_audit:
        from localproof import selfaudit

        return selfaudit.run(sys.stdout)
    if args.probe_outbound:
        from localproof import probe

        try:
            return probe.run(args.probe_outbound, sys.stdout)
        except ValueError as exc:
            print(f"--probe-outbound: {exc}", file=sys.stderr)
            return EXIT_FAILURE

    _configure_logging()
    running = start_server(record_requests=args.window_smoke)
    log.info("serving on %s (guard: %s)", running.url, _GUARD.mode)
    try:
        if not wait_for_health(running.port):
            print("LocalProof server did not start; see the log folder for details.", file=sys.stderr)
            return EXIT_FAILURE
        if args.serve_smoke:
            return serve_smoke(running)
        if args.window_smoke:
            return window_smoke(running)
        return run_window(running)
    finally:
        running.stop()
        log.info("stopped")


def exit_after_window(code: int) -> None:
    """Exit without waiting on pywebview's helper threads.

    pywebview injects its JS bridge from a non-daemon thread that blocks, with
    no timeout, on an evaluate_js callback. If the user closes the window while
    that is pending, the callback never arrives and normal interpreter shutdown
    would hang forever, leaving an invisible process. Our own cleanup (server
    stop, logs) has already run in main(), so flush and leave.
    """
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    exit_after_window(main())
