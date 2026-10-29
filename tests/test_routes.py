import io
import re

import pytest

from localproof import paths
from tests.conftest import REPO_ROOT, SAMPLE_CSV


def csrf(client) -> str:
    page = client.get("/").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def repo_files() -> set:
    return {p for p in REPO_ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_index_renders_form(client):
    page = client.get("/").get_data(as_text=True)
    assert 'name="csv_file"' in page
    assert "Run forecast" in page


def test_security_headers_present(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize(
    "host",
    ["evil.example:5000", "127.0.0.1.evil.com", "localhost.evil.com", "[::1]evil.com", "[::1]:", "127.0.0.1:abc"],
)
def test_non_loopback_host_rejected(client, host):
    assert client.get("/", headers={"Host": host}).status_code == 400


def test_loopback_hosts_accepted(client):
    assert client.get("/", headers={"Host": "127.0.0.1"}).status_code == 200
    assert client.get("/", headers={"Host": "localhost:5000"}).status_code == 200
    assert client.get("/", headers={"Host": "[::1]:5000"}).status_code == 200


def test_post_without_csrf_rejected(client):
    response = client.post("/forecast", data={"source": "sample", "horizon": "12"})
    assert response.status_code == 400


@pytest.mark.parametrize("token", ["wrong", "\u00e9t\u00e9"])
def test_post_with_wrong_csrf_rejected(client, token):
    csrf(client)  # session now holds a real token
    response = client.post("/forecast", data={"source": "sample", "horizon": "12", "csrf_token": token})
    assert response.status_code == 400


def test_csrf_token_from_another_session_rejected(app):
    other = app.test_client()
    stolen = csrf(other)
    victim = app.test_client()
    csrf(victim)
    response = victim.post("/forecast", data={"source": "sample", "horizon": "12", "csrf_token": stolen})
    assert response.status_code == 400


def test_export_without_csrf_rejected(client):
    assert client.post("/forecast/sample/export", data={"horizon": "12"}).status_code == 400
    assert list(paths.exports_dir().iterdir()) == []


def test_unknown_source_rejected(client):
    response = client.post("/forecast", data={"source": "../etc", "horizon": "6", "csrf_token": csrf(client)})
    assert response.status_code == 400


def test_sample_forecast_flow(client):
    response = client.post(
        "/forecast", data={"source": "sample", "horizon": "9", "csrf_token": csrf(client)}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forecast/sample?horizon=9")
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Next 9 months" in page
    assert 'id="chart-data"' in page
    assert "vendor/chart.umd.js" in page


def test_upload_is_stored_only_in_user_data_folder(client):
    before = repo_files()
    data = {
        "source": "upload",
        "horizon": "6",
        "csrf_token": csrf(client),
        "csv_file": (io.BytesIO(SAMPLE_CSV.read_bytes()), "mine.csv"),
    }
    response = client.post("/forecast", data=data, content_type="multipart/form-data")
    assert response.status_code == 302
    stored = list(paths.uploads_dir().glob("*.csv"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == SAMPLE_CSV.read_bytes()
    assert repo_files() == before


def test_invalid_upload_shows_error_and_writes_nothing(client):
    data = {
        "source": "upload",
        "horizon": "6",
        "csrf_token": csrf(client),
        "csv_file": (io.BytesIO(b"date,amount\n2024-01-01,1\n"), "short.csv"),
    }
    response = client.post("/forecast", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "at least 24 months" in response.get_data(as_text=True)
    assert list(paths.uploads_dir().iterdir()) == []


def test_upload_without_file_shows_error(client):
    response = client.post("/forecast", data={"source": "upload", "horizon": "6", "csrf_token": csrf(client)})
    assert response.status_code == 400
    assert "Choose a CSV file" in response.get_data(as_text=True)


def test_bad_horizon_shows_error(client):
    response = client.get("/forecast/sample?horizon=40")
    assert response.status_code == 400
    assert "between 6 and 12" in response.get_data(as_text=True)


@pytest.mark.parametrize("run_id", ["abc", "0" * 31, "Z" * 32, "0" * 32 + "%0A"])
def test_invalid_run_ids_are_404(client, run_id):
    assert client.get(f"/forecast/{run_id}").status_code == 404


def test_export_writes_xlsx_to_exports_folder(client):
    before = repo_files()
    response = client.post("/forecast/sample/export", data={"horizon": "12", "csrf_token": csrf(client)})
    assert response.status_code == 302
    exported = list(paths.exports_dir().glob("*.xlsx"))
    assert len(exported) == 1
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Exported to your data folder" in page
    download = client.get(f"/exports/{exported[0].name}")
    assert download.status_code == 200
    assert download.headers["Content-Disposition"].startswith("attachment")
    assert repo_files() == before


def test_export_download_rejects_other_names(client):
    assert client.get("/exports/notes.txt").status_code == 404
    assert client.get("/exports/cashflow-forecast-20260101-000000-abcdef.xlsx%0A").status_code == 404


def test_spoofed_exported_param_not_rendered(client):
    page = client.get("/forecast/sample?horizon=12&exported=..%2F..%2Fevil.xlsx").get_data(as_text=True)
    assert "Exported to your data folder" not in page
    page = client.get(
        "/forecast/sample?horizon=12&exported=cashflow-forecast-20260101-000000-abcdef.xlsx"
    ).get_data(as_text=True)
    assert "Exported to your data folder" not in page  # well-formed but no such file


def test_two_exports_in_same_second_do_not_collide(client):
    token = csrf(client)
    for _ in range(2):
        client.post("/forecast/sample/export", data={"horizon": "12", "csrf_token": token})
    assert len(list(paths.exports_dir().glob("*.xlsx"))) == 2


def test_malformed_csv_is_400_not_500(app, client):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    data = {
        "source": "upload",
        "horizon": "6",
        "csrf_token": csrf(client),
        "csv_file": (io.BytesIO(b"Date,date,amount\n2024-01-01,2024-01-01,1\n"), "dup.csv"),
    }
    response = client.post("/forecast", data=data, content_type="multipart/form-data")
    assert response.status_code == 400


def test_default_upload_limit_is_10_mb(app):
    assert app.config["MAX_CONTENT_LENGTH"] == 10 * 1024 * 1024


def test_upload_over_default_limit_gets_friendly_error(client):
    token = csrf(client)
    data = {
        "source": "upload",
        "horizon": "6",
        "csrf_token": token,
        "csv_file": (io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "huge.csv"),
    }
    response = client.post("/forecast", data=data, content_type="multipart/form-data")
    assert response.status_code == 413
    page = response.get_data(as_text=True)
    assert "larger than 10 MB" in page
    assert 'name="csv_file"' in page  # back on the form, not a bare error page


def test_upload_too_large(app, client):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    data = {
        "source": "upload",
        "horizon": "6",
        "csrf_token": csrf(client),
        "csv_file": (io.BytesIO(b"x" * 4096), "big.csv"),
    }
    response = client.post("/forecast", data=data, content_type="multipart/form-data")
    assert response.status_code == 413
