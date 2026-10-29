# LocalProof

Open-source boilerplate that turns a Flask app into an installable desktop app whose "your data never leaves this machine" claim is verifiable. The full spec is in `docs/claude-code-prompt-localproof.md`. Read it before starting any new phase.

## The one rule

**Nothing may make an outbound network call.** No CDNs, telemetry, update checks, font loading, or analytics. Any `https://` in templates or static files is a bug. All front-end assets are vendored into `app/static/vendor/`. Before finishing any task, check with:

```
grep -rn "https\?://" app/templates app/static --include=*.html --include=*.css --include=*.js | grep -v vendor/
```

## Stack

Python 3.11+, Flask, waitress, pywebview, platformdirs, pandas/numpy/statsmodels (demo only), Chart.js (vendored), PyInstaller (onedir), Inno Setup, cyclonedx-bom, pytest. Ask before adding any dependency, and justify it in one line.

## Layout

- `app/`: Flask app factory, routes, `forecast.py` (pure functions), templates, static
- `localproof/`: `netguard.py`, `paths.py`, `selfaudit.py`, `launcher.py`
- `packaging/`: PyInstaller spec, Inno Setup script
- `sample_data/`, `tests/`, `docs/`, `.github/workflows/`

## Commands

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app run                      # browser dev mode (fastest iteration)
python -m localproof.launcher            # native window mode
python -m localproof.launcher --self-audit
pytest -q
pyinstaller packaging/localproof.spec    # Windows build; runs in CI
```

## Development environment

- Development happens on Ubuntu. Windows is the release target and is built in GitHub Actions.
- pywebview on Linux needs GTK or Qt system packages. If the window fails to open, say which package is missing; don't silently switch backends.
- Anything Windows-only (firewall rule via netsh, `os.startfile`, Inno Setup, exe hashing) must be behind a platform check, and must degrade gracefully on Linux and macOS with a clear "not available on this OS" status.
- When something can only be verified on Windows, list the exact manual steps and expected output instead of claiming it works.

## Conventions

- `netguard` installs before any other import in `launcher.py`. Loopback only: 127.0.0.0/8, ::1, localhost.
- `LOCALPROOF_ALLOW_NETWORK=1` is the dev-only override. The UI must show a red banner when it's active.
- All user files (uploads, exports, logs, config, `SECRET_KEY`) go through `localproof/paths.py`. Never write inside the app or install directory.
- The server binds only to `127.0.0.1` on a random free port. Never `0.0.0.0`.
- Keep `forecast.py` free of Flask imports so it stays unit-testable.
- Type hints on public functions; small modules; no frameworks beyond the stack.

## Honesty in docs

- The Python socket guard is defence-in-depth and can be bypassed by native extensions. The firewall rule is the real enforcement.
- Never write README or SECURITY.md claims the code doesn't back up. When in doubt, state the limitation.

## Workflow

- Work in the phase order given in the spec. Finish each phase with tests passing and the app running before starting the next.
- After each phase, give a 3–5 line summary: what was built, what was verified, and what still needs a manual Windows check.
- Commit after each phase with a clear message.
