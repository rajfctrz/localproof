"""--probe-outbound: test whether the OS lets this process reach the network.

Makes one TCP handshake (no data is sent) to HOST:PORT. Run it with
LOCALPROOF_ALLOW_NETWORK=1 so the Python guard steps aside and only the OS
layer (firewall rule / sandbox) can stop it. With the guard enforcing, the
probe just shows that netguard blocked it.
"""

from __future__ import annotations

import errno
import socket
from dataclasses import dataclass
from typing import TextIO

from localproof import netguard

DEFAULT_TARGET = "example.com:443"
TIMEOUT_S = 5.0
WSAEACCES = 10013  # Windows: "forbidden by its access permissions" (firewall)
OS_BLOCK_ERRNOS = {errno.EACCES, errno.EPERM, WSAEACCES}
NO_ROUTE_ERRNOS = {errno.ENETUNREACH, errno.EHOSTUNREACH, getattr(errno, "WSAENETUNREACH", 10051)}

EXIT_BLOCKED = 0
EXIT_INCONCLUSIVE = 1
EXIT_CONNECTED = 4


@dataclass(frozen=True)
class ProbeResult:
    outcome: str  # blocked_by_guard | blocked_by_os | no_network | connected | inconclusive
    detail: str

    @property
    def exit_code(self) -> int:
        if self.outcome == "connected":
            return EXIT_CONNECTED
        if self.outcome == "inconclusive":
            return EXIT_INCONCLUSIVE
        return EXIT_BLOCKED


def parse_target(target: str) -> tuple[str, int]:
    host, sep, port = target.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ValueError(f"expected HOST:PORT, got {target!r}")
    return host.strip("[]"), int(port)


def classify(exc: BaseException) -> ProbeResult:
    if isinstance(exc, netguard.OutboundBlockedError):
        return ProbeResult("blocked_by_guard", f"netguard refused it ({exc}). Set {netguard.ALLOW_ENV}=1 to test the OS layer.")
    if isinstance(exc, socket.gaierror):
        return ProbeResult("no_network", f"name resolution failed ({exc}): no network is reachable from this process")
    code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    if code in OS_BLOCK_ERRNOS:
        return ProbeResult("blocked_by_os", f"the OS refused the connection ({exc}): firewall rule or sandbox")
    if code in NO_ROUTE_ERRNOS:
        return ProbeResult("no_network", f"no route to the network ({exc}): sandboxed or offline")
    return ProbeResult("inconclusive", f"connection failed for another reason ({type(exc).__name__}: {exc})")


def probe(target: str = DEFAULT_TARGET) -> ProbeResult:
    host, port = parse_target(target)
    try:
        socket.create_connection((host, port), timeout=TIMEOUT_S).close()
    except OSError as exc:
        return classify(exc)
    return ProbeResult("connected", f"CONNECTED to {host}:{port}: outbound traffic is possible from this process")


def run(target: str, out: TextIO) -> int:
    guard = netguard.status()
    print(f"LocalProof outbound probe -> {target} (guard: {guard.mode})", file=out)
    result = probe(target)
    print(f"result: {result.outcome}", file=out)
    print(result.detail, file=out)
    return result.exit_code
