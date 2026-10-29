# Security

## What LocalProof promises

User data (uploaded files, exports, logs, settings) is stored only in the per-user folders reported by the Trust Panel and `--self-audit`, and the app makes no outbound network connections: no telemetry, update checks, CDNs, fonts or analytics.

## How that is enforced, in layers

1. **OS-level enforcement (the real guarantee).**
   - **Windows:** a Windows Firewall rule (`LocalProof - block outbound`) blocks all outbound traffic for `LocalProof.exe`, including any native code running inside that process.
   - **Linux Flatpak:** the app has no `network` permission, so it runs in its own network namespace with only a loopback interface. This covers every process in the sandbox, including WebKit.
   - **macOS and AppImage:** none. These are reported as **guard only**.
2. **Python network guard (defence in depth).** `localproof/netguard.py` patches `socket.connect`, `connect_ex`, `sendto`, `sendmsg`, `create_connection`, `getaddrinfo`, `gethostbyname(_ex)` and `gethostbyaddr`. Only `127.0.0.0/8`, `::1`, `localhost` and `AF_UNIX` sockets get through. **This guard can be bypassed** by anything that does not use Python's socket module: C extensions that open sockets themselves, the WebView engine, `ctypes`, or subprocesses. Treat it as a tripwire that catches and records mistakes in Python code, not as a sandbox.
3. **The local web server.** waitress binds only to `127.0.0.1` on a random port. Every request must carry a loopback `Host` header (blocks DNS rebinding from web pages in your normal browser), every form needs a per-session CSRF token, and responses carry a strict CSP (`default-src 'self'`, no inline or eval'd scripts, `frame-ancestors 'none'`).

## Known gaps

- **WebView2 on Windows.** The WebView2 runtime runs as separate `msedgewebview2.exe` processes. The firewall rule names `LocalProof.exe` only, so it does not cover them. The page can only load from `127.0.0.1` (CSP), so app content cannot reach the network, but the WebView2 runtime itself may make background connections (for example SmartScreen or component updates). To block those too, add an outbound block rule for the WebView2 runtime, which also affects other apps that use it.
- **WKWebView on macOS** loads pages through a system networking process; macOS has no built-in per-app outbound firewall at all.
- **`LOCALPROOF_ALLOW_NETWORK=1`** turns the guard into audit-only mode. It is for development; the UI shows a red banner and `--self-audit` exits `3` while it is set. Anyone who can set environment variables for your account can set it, and on Windows and Flatpak the OS layer still blocks traffic.
- **Unsigned builds.** Until you add code signing, the binaries' integrity rests on comparing hashes with the published `SHA256SUMS`.
- **Detection limits.** The Windows check parses English `netsh` output; on other languages it reports guard only rather than guessing. The macOS check notices LuLu or Little Snitch but cannot see their rules, so it never claims they protect the app.

## Verifying a build

See "Verify it yourself" in the [README](README.md). In short: compare hashes with `SHA256SUMS`, run `--self-audit` (exit `0` = enforced), and run `--probe-outbound` with `LOCALPROOF_ALLOW_NETWORK=1` to check that the OS layer, not just Python, stops the connection.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security → Report a vulnerability) on this repository rather than a public issue. Include the OS, the package type, and the `--self-audit` output.
