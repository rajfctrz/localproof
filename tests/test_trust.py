import os
import re
import time

import pytest

from localproof import enforcement, netguard, opener, paths, settings, userdata
from tests.conftest import SAMPLE_CSV


def csrf(client, path="/trust/") -> str:
    page = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def test_panel_shows_tier_guard_data_and_build(client):
    page = client.get("/trust/").get_data(as_text=True)
    status = enforcement.detect()
    assert status.label in page
    assert "Python network guard" in page and "enforcing" in page
    assert str(paths.data_dir()) in page
    assert "Delete all my data" in page and "Upload retention" in page
    for step in status.verify_steps:
        assert step.replace('"', "&#34;") in page or step in page


def test_badge_on_every_page(client):
    page = client.get("/").get_data(as_text=True)
    assert 'class="trust-badge' in page and "blocked" in page


def test_override_banner_shown_only_with_env(client, monkeypatch):
    assert "Network override is ON" not in client.get("/").get_data(as_text=True)
    monkeypatch.setenv(netguard.ALLOW_ENV, "1")
    netguard.install()
    try:
        page = client.get("/").get_data(as_text=True)
        assert "Network override is ON" in page and "trust-badge--dev_override" in page
    finally:
        monkeypatch.delenv(netguard.ALLOW_ENV)
        netguard.install(mode="enforcing", label="pytest")


@pytest.mark.expected_outbound
def test_try_it_is_blocked_and_counted(client):
    before = len(netguard.blocked_attempts())
    response = client.post("/trust/try", data={"csrf_token": csrf(client)})
    assert response.status_code == 302 and "notice=try-blocked" in response.headers["Location"]
    assert len(netguard.blocked_attempts()) == before + 1
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "never left this computer" in page
    assert f'counter__value">{before + 1}<' in page
    assert "example.com:443" in page


def test_try_it_refuses_when_guard_not_enforcing(client):
    token = csrf(client)
    netguard.uninstall()
    try:
        before = len(netguard.attempts())
        response = client.post("/trust/try", data={"csrf_token": token})
        assert "notice=try-unavailable" in response.headers["Location"]
        assert len(netguard.attempts()) == before
        assert "disabled" in client.get("/trust/").get_data(as_text=True)
    finally:
        netguard.install(mode="enforcing", label="pytest")


def test_open_folder_uses_opener(client, monkeypatch):
    opened = []
    monkeypatch.setattr(opener, "open_path", lambda p: opened.append(p) or (True, "ok"))
    response = client.post("/trust/open-folder", data={"csrf_token": csrf(client)})
    assert "notice=opened" in response.headers["Location"]
    assert opened == [paths.data_dir()]


def test_open_folder_failure_is_reported(client, monkeypatch):
    monkeypatch.setattr(opener, "open_path", lambda p: (False, "no xdg-open"))
    response = client.post("/trust/open-folder", data={"csrf_token": csrf(client)})
    assert "notice=open-failed" in response.headers["Location"]


def test_delete_requires_confirmation(client):
    (paths.uploads_dir() / "keep.csv").write_text("x")
    response = client.post("/trust/delete-data", data={"csrf_token": csrf(client)})
    assert "notice=delete-unconfirmed" in response.headers["Location"]
    assert (paths.uploads_dir() / "keep.csv").exists()


def test_delete_requires_csrf(client):
    (paths.uploads_dir() / "keep.csv").write_text("x")
    assert client.post("/trust/delete-data", data={"confirm_delete": "yes"}).status_code == 400
    assert (paths.uploads_dir() / "keep.csv").exists()


def test_delete_all_my_data(client):
    (paths.uploads_dir() / "a.csv").write_text("x")
    (paths.exports_dir() / "b.xlsx").write_text("y")
    response = client.post("/trust/delete-data", data={"csrf_token": csrf(client), "confirm_delete": "yes"})
    assert "notice=deleted" in response.headers["Location"]
    assert list(paths.uploads_dir().iterdir()) == [] and list(paths.exports_dir().iterdir()) == []


def test_retention_form_saves_and_purges(client):
    old = paths.uploads_dir() / "old.csv"
    old.write_text("x")
    stamp = time.time() - 10 * userdata.SECONDS_PER_DAY
    os.utime(old, (stamp, stamp))
    response = client.post("/trust/retention", data={"csrf_token": csrf(client), "retention_days": "7"})
    assert "notice=retention-saved" in response.headers["Location"]
    assert settings.load().upload_retention_days == 7
    assert not old.exists()


@pytest.mark.parametrize("bad", ["0", "999", "x"])
def test_retention_form_rejects_bad_values(client, bad):
    response = client.post("/trust/retention", data={"csrf_token": csrf(client), "retention_days": bad})
    assert "notice=retention-invalid" in response.headers["Location"]
    assert settings.load().upload_retention_days == settings.DEFAULT_RETENTION_DAYS


def test_unknown_notice_code_is_ignored(client):
    page = client.get("/trust/?notice=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page


def test_app_start_purges_expired_uploads(isolated_home):
    old = paths.uploads_dir() / "old.csv"
    old.write_text("x")
    stamp = time.time() - 40 * userdata.SECONDS_PER_DAY
    os.utime(old, (stamp, stamp))
    from app import create_app

    create_app({"TESTING": True})
    assert not old.exists()


def test_upload_triggers_purge(client):
    old = paths.uploads_dir() / "old.csv"
    old.write_text("x")
    stamp = time.time() - 40 * userdata.SECONDS_PER_DAY
    os.utime(old, (stamp, stamp))
    page = client.get("/").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    data = {"source": "upload", "horizon": "6", "csrf_token": token, "csv_file": (open(SAMPLE_CSV, "rb"), "s.csv")}
    assert client.post("/forecast", data=data, content_type="multipart/form-data").status_code == 302
    assert not old.exists()
    assert len(list(paths.uploads_dir().iterdir())) == 1


def test_open_export_calls_opener(client, monkeypatch):
    opened = []
    monkeypatch.setattr(opener, "open_path", lambda p: opened.append(p) or (True, "ok"))
    token = csrf(client, "/")
    client.post("/forecast/sample/export", data={"horizon": "12", "csrf_token": token})
    [export] = paths.exports_dir().glob("*.xlsx")
    response = client.post(f"/exports/{export.name}/open", data={"csrf_token": token, "run_id": "sample", "horizon": "12"})
    assert response.status_code == 302 and "opened=1" in response.headers["Location"]
    assert opened == [export]
    assert client.post("/exports/nope.xlsx/open", data={"csrf_token": token}).status_code == 404
