# Verification status and manual checks

What has actually been run, where, and what is still unverified. Nothing in the "unverified" list has been run; each item gives the exact commands and the expected output.

## Verified

### In CI: run [`40876024501`](https://github.com/rajfctrz/localproof-ci/actions/runs/40876024501), private repo `rajfctrz/localproof-ci`, all six jobs green

| Job | What ran and passed |
|---|---|
| `windows` (windows-latest) | 207 tests under the guard (0 unexpected attempts); frozen exe `--serve-smoke`, `--self-audit` exit 2 ("The firewall rule is missing"), `--window-smoke` in WebView2; Inno Setup build; silent install as the (admin) runner user; `netsh` shows the rule Enabled/Out/Block for `…\Programs\LocalProof\LocalProof.exe`, all profiles ON; installed exe `--self-audit` **exit 0, ENFORCED**; `--probe-outbound` with `LOCALPROOF_ALLOW_NETWORK=1` → **`blocked_by_os`**; silent uninstall removed the rule and kept `%LOCALAPPDATA%\LocalProof` |
| `macos (macos-14, arm64)` | 207 tests; `.app` `--serve-smoke`, `--self-audit` exit 2, `--window-smoke`; DMG built and verified mounted |
| `macos (macos-15-intel, x86_64)` | the same as arm64 |
| `appimage` (ubuntu-22.04) | 207 tests; frozen `--serve-smoke`, `--self-audit` exit 2, `--window-smoke` under Xvfb; AppImage built; from the AppImage `--serve-smoke` and `--self-audit` exit 2 mentioning AppImage |
| `flatpak` (GNOME 50 container, x86_64, committed `python-deps.json`) | build + install; permissions `shared=ipc;`; `--self-audit` **exit 0, ENFORCED**; `--serve-smoke`; `--probe-outbound` with the guard overridden → **`no_network`** |
| `release` | CycloneDX SBOM; `SHA256SUMS` for the installer, both DMGs, the AppImage, the Flatpak, `LocalProof.exe` and the SBOM |

Earlier runs: [`40873616205`](https://github.com/rajfctrz/localproof-ci/actions/runs/40873616205) (PyInstaller spec ignored environment markers, fixed), [`40874509364`](https://github.com/rajfctrz/localproof-ci/actions/runs/40874509364) (all Windows checks passed; the uninstall step inherited netsh's expected exit code 1, fixed).

### Locally

| Target | Where | What ran |
|---|---|---|
| macOS arm64, source + `.app` + DMG | this Mac (macOS 14) | `scripts/verify.sh` (tests, no-outbound grep, browser mode, window, self-audit exit 2); frozen app checks with the self-audit hash matching `shasum`; `verify_dmg.sh --window`; 0 outbound attempts in the app's audit log |
| macOS arm64, interactive use of `dist/LocalProof.app` | this Mac, by the owner (2026-10-29) | app opened from the local build after `--self-audit` exit 2; the owner clicked through the window and reported it working (the per-step list below was not recorded item by item) |
| Linux aarch64, source + frozen + AppImage | native arm64 `ubuntu:22.04` container | PyGObject 3.50.1 + WebKit2 4.1; tests; window smoke (source, frozen, AppImage) under Xvfb; self-audit exit 2 |
| Linux aarch64 Flatpak | native arm64 GNOME 50 container | build + install; no network permission; self-audit exit 0; probe `no_network`; window smoke inside the sandbox (with an aarch64 `python-deps.json` in a scratch copy) |

## Still unverified: needs a person

### Windows 10/11, beyond what CI covers

CI installed as an administrator (so the rule was added without a UAC prompt) and never clicked through the UI. On a real machine:

Build (PowerShell, repo root), if not using the CI artifact:
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

### macOS Gatekeeper on a downloaded DMG

On another Mac, download the DMG through a browser (so it is quarantined), drag LocalProof to Applications and double-click. Expect: "LocalProof can't be opened…" (unsigned). Then right-click → Open → Open, or `xattr -dr com.apple.quarantine /Applications/LocalProof.app`. Expect: the app opens; `/Applications/LocalProof.app/Contents/MacOS/LocalProof --self-audit` prints `GUARD ONLY`, exit 2. Also check: with LuLu installed, the Trust Panel mentions it and still says guard only.

### AppImage on other distributions

```bash
sudo apt install libgirepository1.0-dev libcairo2-dev pkg-config gir1.2-gtk-3.0 gir1.2-webkit2-4.1 desktop-file-utils xvfb
# build as in the appimage CI job, then:
./dist/LocalProof-0.1.0-x86_64.AppImage --self-audit      # expect exit 2, mechanism "none (AppImage)"
./dist/LocalProof-0.1.0-x86_64.AppImage                   # expect the window to open
```
Also run the AppImage on a different distro (e.g. Fedora 40+, Ubuntu 24.04). The bundle relies on the host's WebKitGTK helper processes, so expect it to need WebKit2GTK 4.1 installed on the host. The appimagetool runtime is downloaded from the `continuous` release at build time and is not pinned.

### Flatpak on a real desktop (portals, file manager)

```bash
flatpak install --user flathub org.gnome.Platform//50 org.gnome.Sdk//50
flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/io.github.OWNER.LocalProof.yml
flatpak info --user --show-permissions io.github.OWNER.LocalProof         # expect no "network" in shared=
flatpak run io.github.OWNER.LocalProof --self-audit                        # expect exit 0, ENFORCED
flatpak run --env=LOCALPROOF_ALLOW_NETWORK=1 io.github.OWNER.LocalProof --probe-outbound   # expect result: no_network
flatpak run io.github.OWNER.LocalProof                                     # expect the window; Open data folder via the portal
```

### Interactive use in the native window (Windows, Linux; macOS arm64 owner-checked above)

The window smoke tests confirm each page and its assets load in the native WebView; they do not click through the UI. In the native window, check by hand: upload a CSV; change the horizon; **Export to Excel** → **Open in Excel**; **Save a copy elsewhere** (WebView download); Trust Panel → **Try it** (counter +1), **Open data folder**, retention **Save**, **Delete all my data** with the checkbox. Expect each to behave as in browser mode, where they are covered by tests.

### Draft release on a tag

The release job ran and produced the SBOM and `SHA256SUMS`, but the draft-release step only runs for `v*` tags and has not been triggered: `git tag v0.1.0 && git push ci v0.1.0`. Expect a draft release with all packages, the SBOM and `SHA256SUMS`.
