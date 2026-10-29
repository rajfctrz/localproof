# How LocalProof works

## Start-up order (`localproof/launcher.py`)

1. `from localproof import netguard` and `netguard.install()` run before any other import, so libraries that capture socket functions at import time get the guarded versions. A test checks this order with the AST.
2. CLI flags that need no server (`--version`, `--self-audit`, `--probe-outbound`) run and exit. On windowed Windows builds, `winconsole.ensure_stdio()` first reattaches stdout to a pipe, file or the parent console.
3. waitress serves the Flask app on `127.0.0.1`, port `0` (the OS picks a free port, so there is no gap between choosing and binding).
4. The launcher waits for `/health`, then opens a pywebview window (`private_mode=True`: no cookies or storage persisted by the WebView). On Linux the GTK backend is forced so a missing GTK stack is reported, not silently swapped for Qt.
5. When the window closes, the server loop stops on its own thread, logs are flushed and the process exits. (`os._exit` is used because pywebview's JS-bridge thread can block forever if the window closes mid-load.)

## The network guard (`localproof/netguard.py`)

| Patched | Why |
|---|---|
| `socket.socket.connect`, `connect_ex` | TCP and connected UDP, including `ssl`, `http.client`, `urllib`, `urllib3`/`requests`, asyncio |
| `socket.socket.sendto`, `sendmsg` | unconnected UDP (for example hand-rolled DNS) |
| `socket.create_connection` | refuse before resolution |
| `socket.getaddrinfo`, `gethostbyname(_ex)`, `gethostbyaddr` | DNS lookups leak hostnames even when no connection follows |

Allowed: `127.0.0.0/8`, `::1` (including IPv4-mapped and zone-scoped forms), `localhost`, and `AF_UNIX`. Everything else is recorded (`Attempt`: time, session, call, host, port, allowed, stack summary) in memory and as JSON lines in `<log dir>/netguard.log`, then refused with `OutboundBlockedError`, a `ConnectionError`, so libraries treat it like any network failure. Each start writes a `session_start` record, so `--self-audit` can show the previous app session's attempts.

`LOCALPROOF_ALLOW_NETWORK=1` selects audit mode: the same records, but calls go through.

The test suite runs entirely under the enforcing guard; any attempt outside the tests that deliberately make one fails the run. A fresh-interpreter test imports pandas, numpy, statsmodels and openpyxl after the guard, runs the forecast and writes Excel, and asserts zero attempts.

## Enforcement detection (`localproof/enforcement/`)

`detect()` picks the provider for the OS and returns an `EnforcementStatus(tier, mechanism, active, verify_steps, notes)`.

- **Windows:** `netsh advfirewall firewall show rule name="LocalProof - block outbound" verbose`. A rule must be enabled, outbound, block, and name the running `LocalProof.exe` (paths compared case-insensitively), and `netsh advfirewall show allprofiles state` must show every profile on. Running from source is always guard only.
- **Linux:** `/.flatpak-info` present and its `[Context] shared=` does not include `network` → enforced. A Flatpak with network, an AppImage (`$APPIMAGE`) or a plain run → guard only.
- **macOS:** always guard only; mentions LuLu or Little Snitch if installed, without claiming they are configured.

Any exception, unreadable output, or a provider that says `enforced` but not `active` becomes `guard_only`. With the override set, the tier is `dev_override`. The header badge uses a 60-second cache; the Trust Panel and `--self-audit` always re-check.

## Self-audit and probe

`--self-audit` prints version, build time and commit, the executable identity (SHA-256 of the binary; of the `.AppImage` file for AppImages; the Flatpak commit for Flatpaks), guard state, tier, firewall rule, data folders and size, the last app session's blocked attempts, and every installed package. Exit codes: `0` enforced and guard active, `2` guard only, `3` dev override, `1` guard inactive.

`--probe-outbound [HOST:PORT]` makes one TCP handshake and classifies the result: `blocked_by_guard`, `blocked_by_os` (`EACCES`, `EPERM`, Windows `WSAEACCES` from the firewall), `no_network` (DNS failure or no route, as in the Flatpak sandbox), `connected` (exit `4`), or `inconclusive`. Run it with `LOCALPROOF_ALLOW_NETWORK=1` to test the OS layer on its own.

## Your data

All user files go through `localproof/paths.py` (platformdirs), which refuses any path inside the app or bundle directory. Uploads are kept for a configurable number of days (default 30, purged at start-up and after each upload). **Delete all my data** removes uploads and exports and empties the logs; settings and the session key are kept so the app keeps working. Uninstalling leaves the data folder in place.

## Build pipeline (`.github/workflows/build.yml`)

Each job installs `requirements-dev.txt` into a plain venv, runs the tests, builds, and runs the checks that matter for that package: the Windows job installs the app, confirms the firewall rule, expects `--self-audit` to exit `0` and `--probe-outbound` (guard overridden) to be `blocked_by_os`, then uninstalls and checks the rule is gone. The Flatpak job checks the permissions contain no network, expects `--self-audit` to exit `0` and the probe to find no network. The macOS and AppImage jobs expect exit `2`. A final job writes one CycloneDX SBOM and `SHA256SUMS`, and creates a draft release for `v*` tags.
