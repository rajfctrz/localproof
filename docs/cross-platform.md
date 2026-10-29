# Cross-platform addendum

This extends `claude-code-prompt-localproof.md`. Where the two conflict, this file wins.

## Principle

LocalProof runs and installs on Windows, macOS and Linux. The strength of the "no outbound" guarantee differs per OS. The app must **report the actual enforcement level honestly** and never imply OS-level enforcement where there is none.

## Enforcement tiers

| OS | Package | OS-level enforcement | Tier |
|---|---|---|---|
| Windows 10/11 | Inno Setup installer | Per-app outbound block via Windows Firewall rule | **Enforced** (when the rule is present) |
| Linux | Flatpak | Sandbox with no `--share=network`: the app gets its own network namespace with only loopback | **Enforced** |
| Linux | AppImage | None | **Guard only** |
| macOS (arm64 + x86_64) | .app in a DMG | None built in (the macOS firewall is inbound only) | **Guard only**; detect LuLu / Little Snitch and recommend them |

"Guard only" means the Python netguard is the sole protection. It's real, but bypassable by native code.

## Code structure

Add a package `localproof/enforcement/` with one provider per OS behind a common interface:

```python
@dataclass
class EnforcementStatus:
    tier: Literal["enforced", "guard_only", "dev_override"]
    mechanism: str          # e.g. "Windows Firewall rule 'LocalProof - block outbound'"
    active: bool
    verify_steps: list[str] # commands a reviewer can run themselves
    notes: str              # honest limitations

def detect() -> EnforcementStatus: ...
```

- `windows.py`: query the firewall rule via `netsh advfirewall firewall show rule name=...`.
- `linux.py`: detect Flatpak via `/.flatpak-info`. Parse its `[Context]` section and confirm `shared=` doesn't include `network`. Otherwise report AppImage/dev as guard only.
- `macos.py`: always guard only. Check for `/Applications/LuLu.app` or `/Applications/Little Snitch.app` and mention it if found, without claiming it's configured for this app.

The Trust Panel and `--self-audit` both use `detect()`. The self-audit exit code is 0 only when the tier is `enforced` and the guard is active. `guard_only` returns a distinct non-zero code (e.g. 2) so CI and reviewers can tell the difference.

Also make these cross-platform:
- "Open data folder": `os.startfile` (Windows), `open` (macOS), `xdg-open` (Linux).
- Executable hash: hash `sys.executable` when frozen on Windows/Linux; hash the main binary inside the `.app` bundle on macOS. Flatpak: report the Flatpak commit (`flatpak info`) instead.

## Packaging

**Windows**
- PyInstaller onedir → Inno Setup. As in the main spec.

**macOS**
- PyInstaller with a `BUNDLE` step to produce `LocalProof.app`.
- Build separately on Intel and Apple Silicon runners. Don't attempt universal2; numpy/pandas wheels make it fragile.
- Package with `create-dmg`.
- Code signing + notarization: placeholder CI steps (`codesign`, `xcrun notarytool`) driven by secrets, disabled by default.
- README must explain the unsigned-app workaround (right-click → Open, or `xattr -dr com.apple.quarantine`).

**Linux**
- **Flatpak (the recommended, enforced channel).**
  - Manifest in `packaging/flatpak/` on the `org.gnome.Platform` runtime (it ships WebKitGTK for pywebview).
  - `finish-args` must **not** include `--share=network`. Include `--socket=wayland`, `--socket=fallback-x11`, `--device=dri`, and `--filesystem=xdg-documents:ro` for CSV import.
  - Python deps via `flatpak-pip-generator`.
  - App ID: `io.github.<owner>.LocalProof`. Leave the owner as a placeholder.
- **AppImage (convenience channel, guard only).**
  - PyInstaller onedir → appimagetool.
  - Build on Ubuntu 22.04 for older glibc compatibility.

## CI (`.github/workflows/build.yml`)

Matrix jobs: `windows-latest`, `macos-14` (arm64), `macos-13` (x86_64), `ubuntu-22.04` (AppImage), and a Flatpak job using `flatpak/flatpak-github-actions`.

Each job runs the tests, builds, and computes SHA-256. A final job collects all artifacts, generates one CycloneDX SBOM, writes a `SHA256SUMS` file, and attaches everything to a draft release.

## Tests

- Unit-test each enforcement provider with mocked command output and mocked files (`/.flatpak-info` with and without network).
- Keep a test that `detect()` never returns `enforced` when the underlying check fails.

## README changes

- Replace "Windows-first" with the tier table above.
- "Verify it yourself" gets one subsection per OS with exact commands:
  - Windows: `netsh advfirewall firewall show rule name="LocalProof - block outbound"`
  - Flatpak: `flatpak info --show-permissions io.github.<owner>.LocalProof`
  - macOS: run `--self-audit` and see "guard only"
- State plainly: macOS and AppImage builds have no OS-level enforcement.

## Phase order (replaces the main spec's)

1. forecast + Flask in browser
2. netguard + tests
3. launcher with pywebview (verify on Linux locally)
4. enforcement providers + Trust Panel
5. self-audit
6. PyInstaller builds per OS
7. Inno Setup
8. macOS bundle + DMG
9. AppImage
10. Flatpak
11. CI matrix
12. README
