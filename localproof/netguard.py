"""Socket-level outbound blocker with an audit log.

Patches the Python socket layer so only loopback traffic (127.0.0.0/8, ::1,
"localhost") and local IPC (AF_UNIX) get through. Every other attempt is
recorded (in memory and as JSON lines in the user log folder) and refused with
OutboundBlockedError.

This is defence-in-depth, not the hard guarantee: native code (C extensions,
the WebView engine, subprocesses) does not go through Python's socket module
and is not covered. OS-level enforcement is reported by localproof.enforcement.

Install it before any other import in the entry point, so modules that bind
socket functions at import time get the patched versions.

``LOCALPROOF_ALLOW_NETWORK=1`` (development only) switches to audit mode:
attempts are still recorded, but allowed through.
"""

from __future__ import annotations

import errno
import ipaddress
import json
import os
import socket
import threading
import traceback
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

ALLOW_ENV = "LOCALPROOF_ALLOW_NETWORK"
LOG_FILE = "netguard.log"
LOG_MAX_BYTES = 1024 * 1024
MAX_ATTEMPTS_IN_MEMORY = 1000
STACK_DEPTH = 8
LOCALHOST_NAMES = frozenset({"localhost"})

Mode = Literal["off", "enforcing", "audit"]

_THIS_FILE = os.path.abspath(__file__)
_SOCKET_METHODS = ("connect", "connect_ex", "sendto", "sendmsg")
_MODULE_FUNCTIONS = (
    "create_connection",
    "getaddrinfo",
    "gethostbyname",
    "gethostbyname_ex",
    "gethostbyaddr",
)


class OutboundBlockedError(ConnectionError):
    """A non-loopback network call was refused by netguard."""

    def __init__(self, operation: str, host: object, port: object) -> None:
        self.operation = operation
        self.host = host
        self.port = port
        target = f"{host}:{port}" if port not in (None, "") else str(host)
        super().__init__(
            errno.EACCES,
            f"LocalProof netguard blocked outbound {operation} to {target}. "
            "This app only talks to 127.0.0.1.",
        )


@dataclass(frozen=True)
class Attempt:
    timestamp: str
    session: str
    operation: str
    host: str
    port: str
    allowed: bool
    stack: tuple[str, ...]


@dataclass(frozen=True)
class GuardStatus:
    mode: Mode
    session: str | None
    log_path: str | None

    @property
    def active(self) -> bool:
        """True only when outbound calls are actually being refused."""
        return self.mode == "enforcing"

    @property
    def override(self) -> bool:
        return self.mode == "audit"


class _State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.mode: Mode = "off"
        self.session: str | None = None
        self.label = "app"
        self.originals: dict[str, Callable[..., Any]] = {}
        self.attempts: list[Attempt] = []
        self.log_path: Path | None = None
        self.log_error: str | None = None


_state = _State()


# --- address classification -------------------------------------------------


def is_loopback_host(host: object) -> bool:
    """True for "localhost" and loopback IP literals (incl. IPv4-mapped IPv6)."""
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip().lower().rstrip(".")
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    if name in LOCALHOST_NAMES:
        return True
    name = name.split("%", 1)[0]  # IPv6 zone id, e.g. ::1%lo0
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _split_address(address: object) -> tuple[object, object]:
    if isinstance(address, tuple) and address:
        return address[0], address[1] if len(address) > 1 else None
    return address, None


def _is_local_ipc(sock: socket.socket) -> bool:
    family = getattr(socket, "AF_UNIX", None)
    return family is not None and sock.family == family


# --- recording ----------------------------------------------------------------


def _stack_summary() -> tuple[str, ...]:
    frames = [f for f in traceback.extract_stack() if os.path.abspath(f.filename) != _THIS_FILE]
    return tuple(f"{f.filename}:{f.lineno} in {f.name}" for f in frames[-STACK_DEPTH:])


def _resolve_log_path() -> Path | None:
    try:
        from localproof import paths  # imported lazily: install() must stay import-light

        return paths.log_dir() / LOG_FILE
    except Exception as exc:  # noqa: BLE001 - logging must never break the guard
        _state.log_error = f"{type(exc).__name__}: {exc}"
        return None


def _write_log(record: dict[str, Any]) -> None:
    path = _resolve_log_path()
    _state.log_path = path
    if path is None:
        return
    try:
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        _state.log_error = None
    except OSError as exc:
        _state.log_error = f"{type(exc).__name__}: {exc}"


def _record(operation: str, host: object, port: object, allowed: bool) -> None:
    attempt = Attempt(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        session=_state.session or "",
        operation=operation,
        host=str(host),
        port="" if port is None else str(port),
        allowed=allowed,
        stack=_stack_summary(),
    )
    with _state.lock:
        _state.attempts.append(attempt)
        del _state.attempts[:-MAX_ATTEMPTS_IN_MEMORY]
        _write_log({"event": "attempt", **asdict(attempt)})


def _check(operation: str, host: object, port: object) -> None:
    """Allow loopback; otherwise record and (when enforcing) refuse."""
    if is_loopback_host(host):
        return
    enforcing = _state.mode == "enforcing"
    _record(operation, host, port, allowed=not enforcing)
    if enforcing:
        raise OutboundBlockedError(operation, host, port)


# --- patched functions --------------------------------------------------------


def _original(name: str) -> Callable[..., Any]:
    return _state.originals[name]


def _connect(self: socket.socket, address: object) -> None:
    if not _is_local_ipc(self):
        _check("connect", *_split_address(address))
    return _original("connect")(self, address)


def _connect_ex(self: socket.socket, address: object) -> int:
    if not _is_local_ipc(self):
        _check("connect_ex", *_split_address(address))
    return _original("connect_ex")(self, address)


def _sendto(self: socket.socket, data: bytes, *args: Any) -> int:
    if not _is_local_ipc(self) and args:
        _check("sendto", *_split_address(args[-1]))
    return _original("sendto")(self, data, *args)


def _sendmsg(self: socket.socket, buffers: Any, *args: Any) -> int:
    if not _is_local_ipc(self) and len(args) >= 3 and args[2] is not None:
        _check("sendmsg", *_split_address(args[2]))
    return _original("sendmsg")(self, buffers, *args)


def _create_connection(address: tuple[Any, ...], *args: Any, **kwargs: Any) -> socket.socket:
    _check("create_connection", *_split_address(address))
    return _original("create_connection")(address, *args, **kwargs)


def _getaddrinfo(host: object, port: object, *args: Any, **kwargs: Any) -> list[Any]:
    if host not in (None, ""):  # None/"" = passive lookup for binding
        _check("getaddrinfo", host, port)
    return _original("getaddrinfo")(host, port, *args, **kwargs)


def _gethostbyname(host: str) -> str:
    _check("gethostbyname", host, None)
    return _original("gethostbyname")(host)


def _gethostbyname_ex(host: str) -> tuple[str, list[str], list[str]]:
    _check("gethostbyname_ex", host, None)
    return _original("gethostbyname_ex")(host)


def _gethostbyaddr(host: str) -> tuple[str, list[str], list[str]]:
    _check("gethostbyaddr", host, None)
    return _original("gethostbyaddr")(host)


_PATCHES: dict[str, Callable[..., Any]] = {
    "connect": _connect,
    "connect_ex": _connect_ex,
    "sendto": _sendto,
    "sendmsg": _sendmsg,
    "create_connection": _create_connection,
    "getaddrinfo": _getaddrinfo,
    "gethostbyname": _gethostbyname,
    "gethostbyname_ex": _gethostbyname_ex,
    "gethostbyaddr": _gethostbyaddr,
}


# --- public API -----------------------------------------------------------------


def resolve_mode() -> Mode:
    """Mode implied by the environment: audit when the dev override is set."""
    return "audit" if os.environ.get(ALLOW_ENV, "").strip() == "1" else "enforcing"


def install(mode: Mode | None = None, label: str = "app") -> GuardStatus:
    """Patch the socket layer. Idempotent; a second call can change the mode."""
    with _state.lock:
        chosen: Mode = mode or resolve_mode()
        if chosen == "off":
            uninstall()
            return status()
        if not _state.originals:
            for name in _SOCKET_METHODS:
                if hasattr(socket.socket, name):
                    _state.originals[name] = getattr(socket.socket, name)
                    setattr(socket.socket, name, _PATCHES[name])
            for name in _MODULE_FUNCTIONS:
                _state.originals[name] = getattr(socket, name)
                setattr(socket, name, _PATCHES[name])
        _state.mode = chosen
        _state.label = label
        _state.session = uuid.uuid4().hex
        _write_log(
            {
                "event": "session_start",
                "session": _state.session,
                "label": label,
                "mode": chosen,
                "pid": os.getpid(),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        return status()


def uninstall() -> None:
    """Restore the original socket functions. Recorded attempts are kept."""
    with _state.lock:
        for name, original in _state.originals.items():
            target = socket.socket if name in _SOCKET_METHODS else socket
            setattr(target, name, original)
        _state.originals.clear()
        _state.mode = "off"


def status() -> GuardStatus:
    path = _state.log_path or _resolve_log_path()
    return GuardStatus(
        mode=_state.mode,
        session=_state.session,
        log_path=str(path) if path else None,
    )


def attempts() -> tuple[Attempt, ...]:
    with _state.lock:
        return tuple(_state.attempts)


def blocked_attempts() -> tuple[Attempt, ...]:
    return tuple(a for a in attempts() if not a.allowed)


def clear_attempts() -> None:
    with _state.lock:
        _state.attempts.clear()


def log_error() -> str | None:
    """Last error writing the audit log, if any (shown in the Trust Panel)."""
    return _state.log_error


def read_log(path: Path | None = None) -> list[dict[str, Any]]:
    """Parse the audit log, skipping lines that are not valid JSON."""
    path = path or _resolve_log_path()
    if path is None or not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
