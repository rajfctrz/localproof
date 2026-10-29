# PyInstaller spec for LocalProof (onedir). Build from the repo root:
#   python packaging/write_build_info.py && pyinstaller --noconfirm packaging/localproof.spec
# Output: dist/LocalProof/ (Windows, Linux) or dist/LocalProof.app (macOS).
import sys
from pathlib import Path

from packaging.requirements import Requirement
from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from localproof import __version__  # noqa: E402

APP_NAME = "LocalProof"
BUNDLE_ID = "io.github.OWNER.LocalProof"
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def runtime_requirements():
    """Requirement names for this platform (environment markers honoured)."""
    names = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        req = Requirement(line)
        if req.marker is None or req.marker.evaluate():
            names.append(req.name)
    return names


datas = [
    (str(ROOT / "app" / "templates"), "app/templates"),
    (str(ROOT / "app" / "static"), "app/static"),
    (str(ROOT / "sample_data" / "monthly_cashflow.csv"), "sample_data"),
]
# Package metadata lets --self-audit list every bundled package and version.
for name in runtime_requirements():
    datas += copy_metadata(name, recursive=True)

a = Analysis(
    [str(ROOT / "localproof" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["localproof._build_info"],
    excludes=["tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    # Windows/macOS: a GUI app with no console window. CLI flags reattach stdio
    # (localproof/winconsole.py on Windows; macOS keeps stdio for the inner binary).
    console=not (IS_WIN or IS_MAC),
    upx=False,
    argv_emulation=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": __version__,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            # Loading http://127.0.0.1 without enabling arbitrary loads.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
