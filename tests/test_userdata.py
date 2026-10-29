import os
import sys
import time

import pytest

from localproof import buildinfo, paths, settings, userdata


def test_default_retention_is_30_days():
    assert settings.load().upload_retention_days == 30


def test_retention_round_trips():
    settings.save(settings.Settings(upload_retention_days=7))
    assert settings.load().upload_retention_days == 7


@pytest.mark.parametrize("bad", ["0", "366", "-1", "abc", "", "1.5"])
def test_invalid_retention_rejected(bad):
    with pytest.raises(settings.SettingsError):
        settings.validate_retention(bad)


def test_corrupt_settings_fall_back_to_defaults():
    (paths.config_dir() / settings.SETTINGS_FILE).write_text("{not json")
    assert settings.load() == settings.Settings()
    (paths.config_dir() / settings.SETTINGS_FILE).write_text('{"upload_retention_days": 9999}')
    assert settings.load() == settings.Settings()


def _upload(name: str, age_days: float) -> "os.PathLike":
    path = paths.uploads_dir() / name
    path.write_text("date,amount\n")
    stamp = time.time() - age_days * userdata.SECONDS_PER_DAY
    os.utime(path, (stamp, stamp))
    return path


def test_purge_removes_only_expired_uploads():
    old = _upload("old.csv", 31)
    fresh = _upload("fresh.csv", 29)
    removed = userdata.purge_expired_uploads(30)
    assert removed == (old,)
    assert not old.exists() and fresh.exists()


def test_purge_leaves_exports_alone():
    export = paths.exports_dir() / "cashflow-forecast-20200101-000000-abcdef.xlsx"
    export.write_bytes(b"x")
    os.utime(export, (0, 0))
    userdata.purge_expired_uploads(1)
    assert export.exists()


def test_delete_all_removes_uploads_exports_and_empties_logs():
    _upload("a.csv", 0)
    (paths.exports_dir() / "b.xlsx").write_bytes(b"12345")
    log = paths.log_dir() / "netguard.log"
    log.write_text("secret host names\n")
    settings.save(settings.Settings(upload_retention_days=5))
    key = paths.secret_key()

    report = userdata.delete_all()

    assert report.removed_files == 2 and report.truncated_logs >= 1 and not report.failed
    assert list(paths.uploads_dir().iterdir()) == [] and list(paths.exports_dir().iterdir()) == []
    assert log.read_text() == ""
    assert settings.load().upload_retention_days == 5 and paths.secret_key() == key


def test_executable_identity_from_source():
    buildinfo.executable_identity.cache_clear()
    identity = buildinfo.executable_identity()
    assert "running from source" in identity.value
    buildinfo.executable_identity.cache_clear()


def test_executable_identity_hashes_frozen_binary(tmp_path, monkeypatch):
    exe = tmp_path / "LocalProof"
    exe.write_bytes(b"binary")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delenv("APPIMAGE", raising=False)
    buildinfo.executable_identity.cache_clear()
    identity = buildinfo.executable_identity(info_path=tmp_path / "none")
    assert identity.value == buildinfo.sha256_file(exe) and identity.label == "SHA-256 of LocalProof"
    buildinfo.executable_identity.cache_clear()


def test_executable_identity_prefers_appimage_file(tmp_path, monkeypatch):
    appimage = tmp_path / "LocalProof-x86_64.AppImage"
    appimage.write_bytes(b"outer")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", str(appimage))
    buildinfo.executable_identity.cache_clear()
    identity = buildinfo.executable_identity(info_path=tmp_path / "none")
    assert identity.label == "SHA-256 of LocalProof-x86_64.AppImage"
    buildinfo.executable_identity.cache_clear()


def test_executable_identity_reports_flatpak_commit(tmp_path):
    info = tmp_path / "flatpak-info"
    info.write_text("[Application]\nname=io.github.OWNER.LocalProof\n[Instance]\napp-commit=deadbeef\n[Context]\nshared=ipc;\n")
    buildinfo.executable_identity.cache_clear()
    identity = buildinfo.executable_identity(info_path=info)
    assert identity.value == "deadbeef" and "Flatpak commit" in identity.label
    buildinfo.executable_identity.cache_clear()


def test_build_timestamp_defaults_to_dev():
    assert buildinfo.build_timestamp() == buildinfo.DEV_BUILD or buildinfo.build_timestamp().endswith("Z")
