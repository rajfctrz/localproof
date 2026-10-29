"""Generate packaging/flatpak/python-deps.json from requirements.txt.

Run on Linux x86_64 with the same Python minor version as the Flatpak runtime
(markers and wheel tags are resolved for the interpreter running this script):

    python3 packaging/flatpak/generate_python_deps.py

Every source is pinned by URL and sha256 so flatpak-builder can install
offline and reproducibly. PyGObject and pycairo are skipped: the GNOME runtime
provides them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("python-deps.json")
PROVIDED_BY_RUNTIME = {"pygobject", "pycairo"}
MAX_RESOLVE_ROUNDS = 5
# PEP 440: a specifier that names a pre-release (e.g. formulaic's wrapt>=1.17.0rc1)
# lets pip choose pre-releases. We exclude each one found and resolve again.
PRERELEASE = re.compile(r"(a|b|rc|dev)\d*", re.IGNORECASE)


def flatpak_requirements() -> list[str]:
    keep = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        spec = line.split("#", 1)[0].strip()
        if not spec:
            continue
        name = re.split(r"[=<>!~;\[ ]", spec, maxsplit=1)[0].lower()
        if name not in PROVIDED_BY_RUNTIME:
            keep.append(spec)
    return keep


def _resolve_once(requirements: list[str], constraints: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        reqs = Path(tmp) / "requirements.txt"
        reqs.write_text("\n".join(requirements) + "\n")
        cons = Path(tmp) / "constraints.txt"
        cons.write_text("\n".join(constraints) + "\n")
        report = Path(tmp) / "report.json"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
             "--prefer-binary", "--report", str(report), "-r", str(reqs), "-c", str(cons)],
            check=True,
        )
        return json.loads(report.read_text())["install"]


def resolve(requirements: list[str]) -> list[dict]:
    constraints: list[str] = []
    for _ in range(MAX_RESOLVE_ROUNDS):
        items = _resolve_once(requirements, constraints)
        pre = [i["metadata"] for i in items if PRERELEASE.search(i["metadata"]["version"])]
        if not pre:
            return items
        constraints += [f"{m['name']}!={m['version']}" for m in pre]
        print(f"excluding pre-releases: {', '.join(constraints)}")
    raise SystemExit(f"still resolving pre-releases after {MAX_RESOLVE_ROUNDS} rounds: {constraints}")


def sha256_of(item: dict) -> str:
    info = item["download_info"]
    hashes = info.get("archive_info", {}).get("hashes", {})
    if "sha256" in hashes:
        return hashes["sha256"]
    legacy = info.get("archive_info", {}).get("hash", "")
    if legacy.startswith("sha256="):
        return legacy.split("=", 1)[1]
    raise SystemExit(f"no sha256 for {item['metadata']['name']}")


def main() -> None:
    items = resolve(flatpak_requirements())
    names = sorted(item["metadata"]["name"] for item in items)
    module = {
        "name": "python3-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --verbose --exists-action=i --no-index --find-links=\"file://${PWD}\" "
            "--prefix=${FLATPAK_DEST} --no-build-isolation " + " ".join(names)
        ],
        "sources": [
            {"type": "file", "url": item["download_info"]["url"], "sha256": sha256_of(item)}
            for item in sorted(items, key=lambda i: i["metadata"]["name"].lower())
        ],
        "x-generated-for": f"Python {sys.version_info.major}.{sys.version_info.minor} on {sys.platform}",
    }
    OUT.write_text(json.dumps(module, indent=2) + "\n")
    print(f"wrote {OUT} ({len(items)} packages for Python {sys.version_info.major}.{sys.version_info.minor})")


if __name__ == "__main__":
    main()
