# Prompt for Claude Code — "LocalProof" Flask desktop boilerplate

Copy everything below the line into Claude Code, run in an empty folder.

---

## Goal

Build an open-source boilerplate, working name **LocalProof**, that turns a Flask web app into an installable Windows desktop app whose "your data never leaves this machine" claim is **provable**, not just stated.

Existing projects (flaskwebgui, PyFladesk, pywebview's flask example) already solve "show Flask in a desktop window". Do not compete on that. Our edge is **verifiable locality** for sensitive-data apps (finance, legal, health):

1. **Runtime network guard**: blocks all non-loopback outbound connections from Python and logs every attempt.
2. **OS-level enforcement**: the installer adds a Windows Firewall rule blocking outbound traffic for the app's executable. This is the hard guarantee; the Python guard is defence-in-depth.
3. **Trust Panel in the UI**: shows the data folder (with an "Open folder" button), a live counter of blocked outbound attempts, an offline status badge, the build version, and the executable's SHA-256.
4. **Self-audit CLI**: `LocalProof.exe --self-audit` prints a plain-text report an IT/security reviewer can run themselves.
5. **Transparent build pipeline**: GitHub Actions builds the installer, publishes SHA-256 hashes and an SBOM (CycloneDX), so anyone can verify what they installed.

## Stack (use exactly these unless something is broken; tell me if you deviate)

- Python 3.11+
- Flask (app), waitress (WSGI server, bind 127.0.0.1 only, random free port)
- pywebview (native window via Edge WebView2 on Windows)
- platformdirs (per-user data, logs, config folders)
- pandas, numpy, statsmodels (demo forecast only)
- Chart.js: **downloaded into `static/vendor/`**, never loaded from a CDN
- PyInstaller (onedir mode) for the build
- Inno Setup script for the installer (including the firewall rule)
- cyclonedx-bom for the SBOM
- pytest for tests

## Demo app (keep it small but realistic)

A "Cash Flow Forecast" page that fits the target audience (CFOs, finance teams):
- Upload a CSV (date, amount), or use the bundled `sample_data/monthly_cashflow.csv` (36 months, synthetic, with seasonality).
- Run a Holt-Winters forecast for the next 6 to 12 months, with a confidence band.
- Show a Chart.js chart, plus a table.
- "Export to Excel" writes the result into the user data folder and offers to open it.
- Uploaded files and outputs go only to the platformdirs user data folder, never the install directory.

## Repository layout

```
localproof/
  app/
    __init__.py         # Flask app factory
    routes.py
    forecast.py         # pure functions, unit tested
    templates/  static/ (vendor/ holds Chart.js and any CSS)
  localproof/
    netguard.py         # socket-level outbound blocker + audit log
    paths.py            # platformdirs wrappers
    selfaudit.py        # --self-audit report
    launcher.py         # entry point: guard → server thread → pywebview window
  sample_data/
  packaging/
    localproof.spec     # PyInstaller
    installer.iss       # Inno Setup, adds/removes firewall rule
  .github/workflows/build.yml
  tests/
  README.md  LICENSE (MIT)  SECURITY.md  docs/how-it-works.md
```

## Implementation requirements

**netguard.py**
- Patch `socket.socket.connect`, `socket.socket.connect_ex`, `socket.create_connection` and `socket.getaddrinfo` to allow only loopback (127.0.0.0/8, ::1, "localhost").
- Raise a clear `OutboundBlockedError` and record each attempt (timestamp, host, port, stack summary) in memory and in a log file under the user log dir.
- Install it before importing anything else in `launcher.py`.
- Provide `LOCALPROOF_ALLOW_NETWORK=1` for development only, and show a red banner in the UI when it's active.
- Document honestly in SECURITY.md that a Python-level guard can be bypassed by native extensions; the firewall rule is the real enforcement.

**launcher.py**
- Pick a free port and start waitress on 127.0.0.1 in a daemon thread.
- Wait for the health endpoint, then open the pywebview window.
- Shut down cleanly when the window closes.
- Generate a random per-install Flask `SECRET_KEY`, stored in the user config dir.
- Handle `--self-audit` and `--version` without opening a window.

**Trust Panel** (a route plus a small always-visible header badge)
- Data folder path, with an "Open folder" button (os.startfile on Windows; equivalents on macOS/Linux).
- Blocked outbound attempts: count and list.
- Network guard status, and whether the firewall rule exists (Windows: query via `netsh advfirewall firewall show rule name=...`).
- App version, build timestamp, SHA-256 of the running executable when frozen.
- A "Try it" button that deliberately attempts a connection to example.com and shows it getting blocked. This is the LinkedIn demo moment.

**selfaudit.py**
- Prints: version, executable hash, guard active yes/no, firewall rule present yes/no, data folder location and size, list of blocked attempts in the last session, and Python packages with versions.
- Exit code 0 if the guard and firewall are both active, non-zero otherwise.

**installer.iss**
- Install per-user to the default location.
- On install: `netsh advfirewall firewall add rule name="LocalProof - block outbound" dir=out action=block program="{app}\LocalProof.exe" enable=yes` (requires admin; if not elevated, skip and let the Trust Panel show "firewall rule missing" with instructions).
- On uninstall: remove the rule.
- Leave the user data folder in place on uninstall, and say so.

**build.yml (GitHub Actions, windows-latest)**
- Install deps, run tests, run PyInstaller, run Inno Setup (choco install innosetup), generate the SBOM, compute SHA-256 of the installer and the exe, upload all of them as release artifacts.
- Add a placeholder step for code signing with secrets, disabled by default, with a comment explaining it.

**Tests**
- forecast.py: correct shape, no NaNs, handles short series with a clear error.
- netguard: loopback allowed, external host blocked, attempt recorded, env override works.
- paths: nothing written inside the app/install directory.

## README (this is the LinkedIn landing page; write it well)

- One-line pitch: "Ship your Flask app to people who don't trust the cloud, and let them verify it."
- The problem in 3 sentences (sensitive data, browser-based tools feel like cloud, trust is the blocker).
- How it compares to flaskwebgui / PyFladesk / plain pywebview: a short, fair table. They solve windowing; we solve provable locality.
- Quickstart: dev run, build, install.
- "Verify it yourself" section: turn off Wi-Fi, run `--self-audit`, check the firewall rule, check the hashes against the release.
- Placeholder for a demo GIF of the "Try it" blocked-connection moment.
- Limitations, stated plainly (Windows-first, Python guard is bypassable, unsigned builds trigger SmartScreen).

## How to work

1. Propose the plan and any stack deviations first, in under 15 lines. Then build.
2. Build in this order: forecast + Flask app runs in a browser → netguard + tests → launcher with pywebview → Trust Panel → self-audit → PyInstaller build → Inno Setup → CI → README.
3. After each step, run it or test it and fix failures before moving on.
4. Do not add any telemetry, update checks or external calls. Any CDN reference anywhere is a bug.
5. If you can't test something here (e.g. Inno Setup or the firewall on non-Windows), say exactly what I need to run manually and what output to expect.

## Done means

- `python -m localproof.launcher` opens a native window with the forecast demo working offline.
- The "Try it" button shows a blocked connection and the counter increments.
- `pytest` passes.
- The PyInstaller build runs on Windows, and `LocalProof.exe --self-audit` prints the report.
- The README is ready to publish.
