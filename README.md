# LocalProof

**Ship your Flask app to people who don't trust the cloud, and let them verify it.**

Finance, legal and health teams are told every day that their data "stays private", usually by tools that run in a browser and feel exactly like the cloud. A desktop app helps, but "trust us, it's local" is still just a claim. LocalProof is a boilerplate that turns a Flask app into an installable desktop app whose *"your data never leaves this machine"* promise can be checked by the person using it, or by their IT team, with commands they run themselves.

<!-- Demo GIF placeholder: the Trust Panel "Try it" button blocking a connection to example.com and the counter going up. -->
> 📽️ *Demo GIF coming soon: pressing **Try it** in the Trust Panel, watching the connection to example.com get blocked, and the counter go up.*

## What you get

| Layer | What it does |
|---|---|
| **Runtime network guard** (`localproof/netguard.py`) | Patches Python's socket layer so only loopback traffic works. Every other attempt is refused with `OutboundBlockedError` and logged with a timestamp, target and stack summary. |
| **OS-level enforcement** | Windows: the installer adds a Windows Firewall rule that blocks all outbound traffic for `LocalProof.exe`. Linux: the Flatpak ships with **no network permission**. This is the hard guarantee; the Python guard is defence in depth. |
| **Trust Panel** | Inside the app: the enforcement tier with commands to check it yourself, a live counter and log of blocked attempts, a **Try it** button, your data folder (open it, set upload retention, or delete everything), the build version and the SHA-256 of the running executable. |
| **Self-audit CLI** | `LocalProof --self-audit` prints a plain-text report and exits `0` only when OS-level enforcement is confirmed *and* the guard is active. |
| **Transparent builds** | GitHub Actions builds every package, runs the checks on each OS, and publishes `SHA256SUMS` and a CycloneDX SBOM. |

The demo app is a small but real **Cash Flow Forecast**: upload a `date,amount` CSV (or use the bundled 36-month sample), get a Holt-Winters forecast for 6 to 12 months with a 95% prediction band, a chart and a table, and export it to Excel. Uploads and exports go only to your per-user data folder.

## Enforcement tiers: what protects you, per OS

The strength of the guarantee differs by OS, and LocalProof reports the real tier, never a better one.

| OS | Package | OS-level enforcement | Tier |
|---|---|---|---|
| Windows 10/11 | Inno Setup installer | Per-app outbound block via a Windows Firewall rule | **Enforced** (when the rule is present) |
| Linux | Flatpak | Sandbox without `--share=network`: own network namespace, loopback only | **Enforced** |
| Linux | AppImage | None | **Guard only** |
| macOS (arm64, x86_64) | `.app` in a DMG | None (the macOS firewall only filters inbound) | **Guard only**; LuLu or Little Snitch are detected and recommended |

**macOS and AppImage builds have no OS-level enforcement.** On those, the Python guard is the only protection: real, but bypassable by native code. If you need the hard guarantee on Linux, use the Flatpak. On macOS, add an outbound firewall such as [LuLu](https://objective-see.org/products/lulu.html) and deny LocalProof all outbound connections.

`--self-audit` exit codes: `0` enforced, `2` guard only, `3` dev override (`LOCALPROOF_ALLOW_NETWORK=1`), `1` guard not running.

## How it compares

These projects are good at what they do. They solve *showing a Flask app in a desktop window*; LocalProof solves *proving it stays local*, and uses pywebview for the window.

| | [flaskwebgui](https://github.com/ClimenteA/flaskwebgui) | [PyFladesk](https://github.com/smoqadam/PyFladesk) | [pywebview](https://pywebview.flowrl.com/) Flask example | **LocalProof** |
|---|---|---|---|---|
| Flask in a desktop window | ✅ (opens an installed browser in app mode) | ✅ (Qt WebEngine) | ✅ (native WebView) | ✅ (pywebview) |
| Blocks outbound connections | ❌ | ❌ | ❌ | ✅ Python guard + OS rule / sandbox |
| Shows the user what was blocked | ❌ | ❌ | ❌ | ✅ Trust Panel + audit log |
| Reviewer-runnable audit | ❌ | ❌ | ❌ | ✅ `--self-audit`, `--probe-outbound` |
| Installer / packages | DIY | DIY | DIY | ✅ Inno Setup, DMG, AppImage, Flatpak |
| Published hashes + SBOM | ❌ | ❌ | ❌ | ✅ CI |

## Quickstart

Python 3.11+ (3.12 recommended).

**Dependencies.** `requirements.txt` (runtime) and `requirements-dev.txt` (tests and build tools) are the single source of truth. Builds and CI install them into a plain `venv`. Conda is fine for local development (`environment.yml` just points pip at `requirements-dev.txt`), but nothing depends on it.

```bash
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

flask --app app run --port 5050            # browser dev mode: http://127.0.0.1:5050 (guard not running)
python -m localproof.launcher              # native window, guard enforcing
python -m localproof.launcher --self-audit
pytest -q                                  # whole suite runs under the enforcing guard
scripts/verify.sh python                   # tests + no-outbound grep + browser + window + self-audit
```

On Linux the native window needs GTK 3 and WebKit2GTK 4.1, for example on Debian/Ubuntu:
`sudo apt install libgirepository1.0-dev libcairo2-dev pkg-config gir1.2-gtk-3.0 gir1.2-webkit2-4.1`.

**Build** (each on its own OS; CI does all of them):

```bash
python packaging/write_build_info.py && pyinstaller --noconfirm packaging/localproof.spec

# Windows installer (adds the firewall rule)
iscc /DAppVersion=0.1.0 packaging\installer.iss

# macOS DMG
packaging/macos/make_dmg.sh && packaging/macos/verify_dmg.sh dist/LocalProof-0.1.0-macos-$(uname -m).dmg

# Linux AppImage (build on Ubuntu 22.04; needs desktop-file-utils)
APPIMAGETOOL=./appimagetool packaging/linux/build_appimage.sh

# Linux Flatpak (replace OWNER in the app ID first)
flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/io.github.OWNER.LocalProof.yml
```

**Install.** Windows: run `LocalProof-Setup-<version>.exe` and keep the firewall task ticked (it asks once for administrator approval). macOS: open the DMG and drag LocalProof to Applications. Linux: `flatpak install LocalProof.flatpak`, or `chmod +x` the AppImage and run it.

Unsigned builds: Windows SmartScreen will warn ("More info" → "Run anyway"). macOS Gatekeeper will refuse to open the app the first time: right-click LocalProof.app → **Open**, or run `xattr -dr com.apple.quarantine /Applications/LocalProof.app`. CI has disabled placeholder steps for code signing and notarization.

## Verify it yourself

Start by checking the download: compare its SHA-256 with `SHA256SUMS` on the release page (`Get-FileHash` on Windows, `shasum -a 256` on macOS, `sha256sum` on Linux). The Trust Panel shows the hash of the running executable too.

Then turn off Wi-Fi, use the app, and check that nothing changes, and run the checks for your OS:

### Windows

```powershell
netsh advfirewall firewall show rule name="LocalProof - block outbound" verbose
# Expect: Enabled: Yes, Direction: Out, Action: Block, Program: ...\LocalProof.exe

& "$env:LOCALAPPDATA\Programs\LocalProof\LocalProof.exe" --self-audit | Out-String
# Expect: "Result: ENFORCED ..." and exit code 0 ($LASTEXITCODE)

$env:LOCALPROOF_ALLOW_NETWORK = "1"   # step the Python guard aside so only the firewall is tested
& "$env:LOCALAPPDATA\Programs\LocalProof\LocalProof.exe" --probe-outbound | Out-String
# Expect: "result: blocked_by_os"
```

### Linux (Flatpak)

```bash
flatpak info --show-permissions io.github.OWNER.LocalProof
# Expect: no "network" in the shared= line

flatpak run io.github.OWNER.LocalProof --self-audit          # Expect: exit code 0, "ENFORCED"
flatpak run --env=LOCALPROOF_ALLOW_NETWORK=1 io.github.OWNER.LocalProof --probe-outbound
# Expect: "result: no_network"
```

### macOS

```bash
/Applications/LocalProof.app/Contents/MacOS/LocalProof --self-audit
# Expect: "GUARD ONLY" and exit code 2. macOS has no built-in per-app outbound blocking.
```

### Linux (AppImage)

```bash
./LocalProof-0.1.0-x86_64.AppImage --self-audit
# Expect: "GUARD ONLY", mechanism "none (AppImage)", exit code 2.
```

`--probe-outbound` makes one TCP handshake (no data) to `example.com:443`, or `HOST:PORT` if you pass one. On a guard-only system with the override set, it really connects, and says so (`CONNECTED`, exit code 4).

## Use it as a boilerplate

- Replace `app/` with your Flask app. Keep the `create_app()` factory, and resolve every file you write through `localproof/paths.py`.
- Vendor every front-end asset into `app/static/vendor/`. CI-friendly check: `grep -rn 'https\?://' app/templates app/static --include='*.html' --include='*.css' --include='*.js' | grep -v vendor/` must print nothing.
- Keep `from localproof import netguard` and `netguard.install()` as the first lines of the entry point.
- Rename the app ID (`io.github.OWNER.LocalProof`), the firewall rule name and the Inno Setup `AppId`.

## Limitations, stated plainly

- **The Python guard is bypassable.** C extensions, the WebView engine and subprocesses don't use Python's socket module. OS-level enforcement is the real guarantee, and only Windows (rule present) and Flatpak have it.
- **The Windows rule covers `LocalProof.exe` only.** The WebView2 runtime runs as separate `msedgewebview2.exe` processes that a per-program rule does not block. The page itself can only load from `127.0.0.1` (strict CSP), but the WebView2 runtime may make its own background connections. See [SECURITY.md](SECURITY.md).
- **macOS and AppImage have no OS-level enforcement** (guard only). WKWebView networking also runs in a separate system process there.
- **Per-user Windows installs need one administrator approval** for the firewall rule. Declined, the app runs with the guard only and the Trust Panel says the rule is missing.
- **Non-English Windows:** netsh output is localised, so the check can't read the rule and reports guard only rather than guessing. Verify manually with the commands above.
- **Unsigned builds** trigger SmartScreen and Gatekeeper warnings until you add signing.
- **The SBOM** is generated from the runtime requirements on Linux; platform-only packages (pyobjc on macOS, pythonnet on Windows) are listed by each build's `--self-audit`.

What is and isn't verified yet on each platform: [docs/MANUAL_CHECKS.md](docs/MANUAL_CHECKS.md) and [docs/BLOCKERS.md](docs/BLOCKERS.md). How it works: [docs/how-it-works.md](docs/how-it-works.md).

## License

MIT. See [LICENSE](LICENSE). Chart.js (MIT) is vendored unmodified; see `app/static/vendor/README.md` for its hash.
