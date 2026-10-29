"""Give a windowed (no-console) Windows build somewhere to print CLI output.

PyInstaller windowed apps start with sys.stdout = None. For --self-audit and
friends we reuse an inherited pipe/file handle (`LocalProof.exe --self-audit | more`,
or redirection), else attach to the parent console (cmd / PowerShell).
"""

from __future__ import annotations

import io
import os
import sys

STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
ATTACH_PARENT_PROCESS = -1
INVALID_HANDLE_VALUE = -1
FILE_TYPE_UNKNOWN = 0


def _stream_from_handle(kernel32, which: int):
    import msvcrt

    handle = kernel32.GetStdHandle(which)
    if not handle or handle == INVALID_HANDLE_VALUE or kernel32.GetFileType(handle) == FILE_TYPE_UNKNOWN:
        return None
    fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_TEXT)
    return io.TextIOWrapper(io.FileIO(fd, "w", closefd=False), encoding="utf-8", line_buffering=True)


def ensure_stdio() -> None:
    """No-op unless this is Windows and stdout/stderr are missing."""
    if sys.platform != "win32" or (sys.stdout is not None and sys.stderr is not None):
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    out = _stream_from_handle(kernel32, STD_OUTPUT_HANDLE)
    err = _stream_from_handle(kernel32, STD_ERROR_HANDLE)
    if out is None and kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        out = open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
        err = err or out
    sys.stdout = out or io.StringIO()
    sys.stderr = err or sys.stdout
