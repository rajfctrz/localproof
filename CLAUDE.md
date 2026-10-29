# LocalProof

Open-source boilerplate that turns a Flask app into an installable desktop app whose "your data never leaves this machine" claim is verifiable. The full spec is in `docs/claude-code-prompt-localproof.md`. Read it before starting any new phase.

## The one rule

**Nothing may make an outbound network call.** No CDNs, telemetry, update checks, font loading, or analytics. Any `https://` in templates or static files is a bug. All front-end assets are vendored into `app/static/vendor/`. Before finishing any task, check with:

```
grep -rn 'https\?://' app/templates app/static --include='*.html' --include='*.css' --include='*.js' | grep -v vendor/
```

## Stack

Python 3.11+ (dev env uses 3.12), Flask, waitress, pywebview, platformdirs, pandas/numpy/statsmodels (demo only), openpyxl (Excel export), Chart.js (vendored), PyInstaller (onedir; `BUNDLE` on macOS), Inno Setup, create-dmg, appimagetool, flatpak-builder, cyclonedx-bom, pytest. Ask before adding any dependency, and justify it in one line.

## Layout

- `app/`: Flask app factory, routes, `forecast.py` (pure functions), templates, static
- `localproof/`: `netguard.py`, `paths.py`, `selfaudit.py`, `launcher.py`, `enforcement/` (one provider per OS behind `detect()`)
- `packaging/`: PyInstaller spec, Inno Setup script, `flatpak/` manifest, AppImage and DMG scripts
- `sample_data/`, `tests/`, `docs/`, `.github/workflows/`

## Commands

```
# local dev (conda is a convenience for getting Python 3.12; nothing else depends on it)
conda env create -f environment.yml      # first time: Python 3.12 + requirements-dev.txt
conda activate localproof
pip install -r requirements-dev.txt      # after changing requirements

# builds and CI: plain venv, same requirements files
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app run                      # browser dev mode (fastest iteration)
python -m localproof.launcher            # native window mode
python -m localproof.launcher --self-audit
pytest -q
pyinstaller packaging/localproof.spec    # per-OS build; Windows/macOS run in CI
flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/<app-id>.yml
```

## Platforms

- Targets: Windows, macOS (arm64 + x86_64), and Linux (Flatpak + AppImage). Cross-platform rules are in `docs/cross-platform.md`, which overrides the main spec where they differ.
- Development happens on macOS arm64 (Apple Silicon) in the `localproof` conda env. Windows, macOS x86_64 and Linux builds run in GitHub Actions.
- `requirements.txt` (runtime) and `requirements-dev.txt` (tests + build tools) are the single source of truth for dependencies. Builds and CI install them into a plain `venv`; conda is local-dev only and `environment.yml` just points pip at `requirements-dev.txt`. Never add a dependency only to `environment.yml`.
- pywebview on Linux needs GTK or Qt system packages. If the window fails to open, say which package is missing; don't silently switch backends.
- All OS-specific code lives behind `localproof/enforcement/` or an explicit platform check. Never assume Windows.
- Enforcement tier must be reported truthfully. Only Windows (firewall rule present) and Flatpak (no network permission) count as `enforced`. Everything else is `guard_only`.
- macOS arm64 can be verified locally. When something can only be verified on Windows, Linux (GTK window, Flatpak, AppImage) or macOS x86_64, list the exact manual steps and expected output instead of claiming it works.

## Conventions

- `netguard` installs before any other import in `launcher.py`. Loopback only: 127.0.0.0/8, ::1, localhost.
- `LOCALPROOF_ALLOW_NETWORK=1` is the dev-only override. The UI must show a red banner when it's active.
- All user files (uploads, exports, logs, config, `SECRET_KEY`) go through `localproof/paths.py`. Never write inside the app or install directory.
- The server binds only to `127.0.0.1` on a random free port. Never `0.0.0.0`.
- Keep `forecast.py` free of Flask imports so it stays unit-testable.
- Type hints on public functions; small modules; no frameworks beyond the stack.

## Honesty in docs

- The Python socket guard is defence-in-depth and can be bypassed by native extensions. OS-level enforcement (Windows Firewall rule, Flatpak's network-less sandbox) is the real guarantee; macOS and AppImage have none, and the docs must say so.
- Never write README or SECURITY.md claims the code doesn't back up. When in doubt, state the limitation.

## Workflow

- Work in the phase order given in `docs/cross-platform.md` (it replaces the main spec's order). Finish each phase with tests passing and the app running before starting the next.
- After each phase, give a 3–5 line summary: what was built, what was verified, and what still needs a manual Windows/Linux/macOS-x86_64 check.
- Commit after each phase with a clear message.
