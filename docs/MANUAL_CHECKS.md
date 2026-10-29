# Verification status and manual checks

What has actually been run, where, and what is still unverified. Nothing in the "unverified" list has been run; each item gives the exact commands and the expected output.

## Verified

| Target | Where | What ran |
|---|---|---|
| macOS arm64, from source | this Mac (macOS 14, Apple Silicon), conda env | `scripts/verify.sh`: 207 tests under the enforcing guard (0 unexpected outbound attempts), no-outbound grep, browser mode (`flask run`), native window smoke (WKWebView: index, forecast, Trust Panel), `--self-audit` exit 2 (guard only) |
| macOS arm64, frozen `.app` | this Mac, plain venv + PyInstaller | `--version`, `--serve-smoke`, `--window-smoke`, `--self-audit` exit 2; self-audit SHA-256 equals `shasum -a 256` of the binary; 0 outbound attempts in the app's audit log |
| macOS arm64 DMG | this Mac, `create-dmg` 1.3.0 with `DMG_SKIP_FINDER=1` | `packaging/macos/verify_dmg.sh --window`: mounted read-only, `--version`, `--serve-smoke`, `--self-audit` exit 2, `--window-smoke` |
| Linux aarch64, from source + frozen | native arm64 `ubuntu:22.04` Docker container on this Mac | PyGObject 3.50.1 built against girepository-1.0, WebKit2 4.1 loads; 206 tests; source and frozen `--window-smoke` under Xvfb (WebKitGTK: index, forecast, Trust Panel); frozen `--serve-smoke`; `--self-audit` exit 2 |
| Linux aarch64 AppImage | same container, appimagetool 1.9.0 (aarch64) | built; from the AppImage: `--serve-smoke`, `--window-smoke`, `--self-audit` exit 2 with mechanism `none (AppImage)` and the hash of the `.AppImage` file |
| Linux aarch64 Flatpak | native arm64 `ghcr.io/flathub-infra/flatpak-github-actions:gnome-50` container (`--privileged`) | `flatpak-builder` build + install; permissions `shared=ipc;` (no network); `--self-audit` **exit 0, ENFORCED**; `--probe-outbound` with `LOCALPROOF_ALLOW_NETWORK=1` → `no_network`; `--serve-smoke`; `--window-smoke` inside the sandbox |

The aarch64 Flatpak was built from a scratch copy whose `python-deps.json` was regenerated for aarch64 with the same generator. The committed `python-deps.json` (x86_64 wheels) has **not** been built.

## Unverified: needs CI (see BLOCKERS.md #1) or a manual run

### CI itself

```bash
gh auth refresh -h github.com -s workflow
git push ci main
gh run watch -R rajfctrz/localproof-ci
gh run view -R rajfctrz/localproof-ci --log-failed     # on failure
```
Expected: jobs `windows`, `macos (macos-14, arm64)`, `macos (macos-15-intel, x86_64)`, `appimage`, `flatpak`, `release` all green; the `release-bundle` artifact contains the installer, two DMGs, the AppImage, `LocalProof.flatpak`, `localproof-sbom.cdx.json` and `SHA256SUMS`.
Unknowns to watch: whether the `macos-15-intel` label is available to the account, whether WebView2 opens a window on the Windows runner, and whether the Windows runner's firewall profiles are all ON (required for `enforced`).

### Windows 10/11 (nothing has run on Windows)

Build (PowerShell, repo root):
```powershell
py -3.12 -m venv .venv; .venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q                         # expect: all passed, "netguard: 0 unexpected"
.venv\Scripts\python packaging\write_build_info.py
.venv\Scripts\pyinstaller --noconfirm packaging\localproof.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 packaging\installer.iss
```
1. **Uninstalled exe is guard only:**
   `scripts\ci\run_expect.ps1 -Exe dist\LocalProof\LocalProof.exe -Expect 2 -AppArgs '--self-audit'`
   Expect: `The firewall rule is missing.` and `exit code: 2`.
2. **Per-user install with UAC (normal user, not admin):** run `dist\installer\LocalProof-Setup-0.1.0.exe`, keep "Block all outbound network traffic…" ticked. Expect: one UAC prompt for `netsh`. Then
   `netsh advfirewall firewall show rule name="LocalProof - block outbound" verbose`
   Expect: `Enabled: Yes`, `Direction: Out`, `Action: Block`, `Program: C:\Users\<you>\AppData\Local\Programs\LocalProof\LocalProof.exe`.
3. **Installed exe is enforced:**
   `scripts\ci\run_expect.ps1 -Exe "$env:LOCALAPPDATA\Programs\LocalProof\LocalProof.exe" -Expect 0 -AppArgs '--self-audit'`
   Expect: `Result: ENFORCED` and `exit code: 0`.
4. **The firewall, not Python, blocks it:**
   `$env:LOCALPROOF_ALLOW_NETWORK="1"; scripts\ci\run_expect.ps1 -Exe "$env:LOCALAPPDATA\Programs\LocalProof\LocalProof.exe" -Expect 0 -AppArgs '--probe-outbound'`
   Expect: `result: blocked_by_os` (WinError 10013).
5. **Declined UAC:** reinstall and click "No" on the UAC prompt. Expect: install completes; the Trust Panel shows "Guard only" and "The firewall rule is missing" with the `netsh … add rule` command.
6. **The app window:** launch from the Start menu. Expect: the window opens (WebView2), the header badge says "Enforced by the OS"; Trust Panel → **Try it** → "Blocked…", counter goes up; upload a CSV, export to Excel, **Open in Excel** opens it, **Open data folder** opens Explorer at `%LOCALAPPDATA%\LocalProof`.
7. **CLI from a normal console** (windowed exe, stdout reattached): `& "$env:LOCALAPPDATA\Programs\LocalProof\LocalProof.exe" --self-audit | Out-String` in PowerShell, and `LocalProof.exe --self-audit` in cmd. Expect: the report is printed. (Unverified whether PowerShell waits without the pipe.)
8. **Uninstall:** Settings → Apps → LocalProof → Uninstall. Expect: one UAC prompt if the rule exists; afterwards `netsh advfirewall firewall show rule name="LocalProof - block outbound"` prints `No rules match the specified criteria.`; `%LOCALAPPDATA%\LocalProof` still exists; the final message says it was left in place.
9. **SmartScreen:** download the unsigned installer in Edge. Expect: "Windows protected your PC" → More info → Run anyway.
10. **Non-English Windows:** on a German or French install, expect the Trust Panel to say the netsh output "could not be read" and report guard only (never enforced).

### macOS x86_64 (Intel)

Same as arm64 on an Intel Mac or the `macos-15-intel` runner:
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
.venv/bin/python packaging/write_build_info.py && .venv/bin/pyinstaller --noconfirm packaging/localproof.spec
DMG_SKIP_FINDER=1 PYTHON=.venv/bin/python packaging/macos/make_dmg.sh
packaging/macos/verify_dmg.sh dist/LocalProof-0.1.0-macos-x86_64.dmg --window
```
Expect: `dmg ok`, self-audit exit 2.

### macOS Gatekeeper on a downloaded DMG

On another Mac, download the DMG through a browser (so it is quarantined), drag LocalProof to Applications and double-click. Expect: "LocalProof can't be opened…" (unsigned). Then right-click → Open → Open, or `xattr -dr com.apple.quarantine /Applications/LocalProof.app`. Expect: the app opens; `/Applications/LocalProof.app/Contents/MacOS/LocalProof --self-audit` prints `GUARD ONLY`, exit 2. Also check: with LuLu installed, the Trust Panel mentions it and still says guard only.

### Linux x86_64 AppImage, and other distributions

```bash
sudo apt install libgirepository1.0-dev libcairo2-dev pkg-config gir1.2-gtk-3.0 gir1.2-webkit2-4.1 desktop-file-utils xvfb
# build as in the appimage CI job, then:
./dist/LocalProof-0.1.0-x86_64.AppImage --self-audit      # expect exit 2, mechanism "none (AppImage)"
./dist/LocalProof-0.1.0-x86_64.AppImage                   # expect the window to open
```
Also run the AppImage on a different distro (e.g. Fedora 40+, Ubuntu 24.04). The bundle relies on the host's WebKitGTK helper processes, so expect it to need WebKit2GTK 4.1 installed on the host. The appimagetool runtime is downloaded from the `continuous` release at build time and is not pinned.

### Linux x86_64 Flatpak (committed manifest + x86_64 deps)

```bash
flatpak install --user flathub org.gnome.Platform//50 org.gnome.Sdk//50
flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/io.github.OWNER.LocalProof.yml
flatpak info --user --show-permissions io.github.OWNER.LocalProof         # expect no "network" in shared=
flatpak run io.github.OWNER.LocalProof --self-audit                        # expect exit 0, ENFORCED
flatpak run --env=LOCALPROOF_ALLOW_NETWORK=1 io.github.OWNER.LocalProof --probe-outbound   # expect result: no_network
flatpak run io.github.OWNER.LocalProof                                     # expect the window; Open data folder via the portal
```

### Interactive use in the native window (all OSes)

The window smoke tests confirm each page and its assets load in the native WebView; they do not click through the UI. In the native window, check by hand: upload a CSV; change the horizon; **Export to Excel** → **Open in Excel**; **Save a copy elsewhere** (WebView download); Trust Panel → **Try it** (counter +1), **Open data folder**, retention **Save**, **Delete all my data** with the checkbox. Expect each to behave as in browser mode, where they are covered by tests.

### Release job

Unverified until CI runs: `cyclonedx-py environment` output, `SHA256SUMS` contents, and the draft release on a `v*` tag (`git tag v0.1.0 && git push ci v0.1.0`). Expect a draft release with all packages, the SBOM and `SHA256SUMS`.
