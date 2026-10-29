import os
import stat
import sys

import pytest

from localproof import paths


def test_all_user_folders_are_outside_app_dir():
    app_dir = paths.app_dir()
    for folder in (paths.data_dir(), paths.log_dir(), paths.config_dir(), paths.uploads_dir(), paths.exports_dir()):
        assert folder.is_dir()
        assert not folder.is_relative_to(app_dir)


def test_default_platformdirs_locations_are_outside_app_dir(monkeypatch):
    monkeypatch.delenv(paths.HOME_ENV)
    import platformdirs

    for fn in (platformdirs.user_data_dir, platformdirs.user_log_dir, platformdirs.user_config_dir):
        from pathlib import Path

        assert not Path(fn(paths.APP_NAME, appauthor=False)).resolve().is_relative_to(paths.app_dir())


def test_home_inside_app_dir_is_refused(monkeypatch):
    monkeypatch.setenv(paths.HOME_ENV, str(paths.app_dir() / "should-not-exist"))
    with pytest.raises(paths.UnsafePathError):
        paths.data_dir()
    assert not (paths.app_dir() / "should-not-exist").exists()


def test_frozen_bundle_dir_is_treated_as_app_dir(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv(paths.HOME_ENV, str(bundle / "home"))
    with pytest.raises(paths.UnsafePathError):
        paths.data_dir()


def test_secret_key_is_stable_and_random(isolated_home):
    first = paths.secret_key()
    assert len(first) == 2 * paths.SECRET_KEY_BYTES
    assert paths.secret_key() == first
    assert (paths.config_dir() / paths.SECRET_KEY_FILE).read_text() == first


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_secret_key_file_is_owner_only():
    paths.secret_key()
    mode = (paths.config_dir() / paths.SECRET_KEY_FILE).stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_folder_size_counts_nested_files(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f").write_bytes(b"x" * 10)
    (tmp_path / "g").write_bytes(b"y" * 5)
    assert paths.folder_size(tmp_path) == 15


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_empty_preexisting_secret_key_is_replaced_owner_only():
    key_path = paths.config_dir() / paths.SECRET_KEY_FILE
    key_path.write_text("")
    key_path.chmod(0o644)
    key = paths.secret_key()
    assert key and key_path.read_text() == key
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
