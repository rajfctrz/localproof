"""Request hardening for a server that only ever talks to its own window.

- Host check: rejects requests whose Host header is not loopback, which blocks
  DNS-rebinding attacks from a web page in the user's normal browser.
- CSRF: per-session token required on every POST, since any local web page
  could otherwise submit forms to 127.0.0.1.
- Response headers: a strict CSP that only allows same-origin assets.
"""

from __future__ import annotations

import hmac
import re
import secrets

from flask import Flask, Response, abort, request, session

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
CSRF_SESSION_KEY = "_csrf"
CSRF_FIELD = "csrf_token"
CSRF_TOKEN_BYTES = 32
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# host, optionally followed by :port; IPv6 literals stay bracketed.
HOST_HEADER = re.compile(r"(?P<host>\[[^\]]*\]|[^:\[\]]+)(?::\d+)?")

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _host_without_port(host: str) -> str | None:
    match = HOST_HEADER.fullmatch(host)
    return match.group("host") if match else None


def csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
        session[CSRF_SESSION_KEY] = token
    return token


def _check_host() -> None:
    if _host_without_port(request.host.lower()) not in LOOPBACK_HOSTS:
        abort(400, description="This app only answers requests addressed to 127.0.0.1.")


def _check_csrf() -> None:
    if request.method in SAFE_METHODS:
        return
    expected = session.get(CSRF_SESSION_KEY, "")
    submitted = request.form.get(CSRF_FIELD, "")
    if not expected or not hmac.compare_digest(expected.encode(), submitted.encode()):
        abort(400, description="The form expired. Reload the page and try again.")


def _add_headers(response: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def init_app(app: Flask) -> None:
    app.before_request(_check_host)
    app.before_request(_check_csrf)
    app.after_request(_add_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token
