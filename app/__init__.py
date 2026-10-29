"""Flask app factory for the LocalProof demo (Cash Flow Forecast)."""

from __future__ import annotations

from typing import Any

from flask import Flask

from localproof import __version__, paths

from . import security

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def create_app(overrides: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=paths.secret_key(),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        APP_VERSION=__version__,
    )
    if overrides:
        app.config.update(overrides)

    security.init_app(app)

    from .routes import bp

    app.register_blueprint(bp)
    return app
