from pathlib import Path

import pytest

from localproof import paths

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO_ROOT / "sample_data" / "monthly_cashflow.csv"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point every user folder at a temp dir so tests never touch real data."""
    home = tmp_path / "localproof-home"
    monkeypatch.setenv(paths.HOME_ENV, str(home))
    return home


@pytest.fixture
def app(isolated_home):
    from app import create_app

    return create_app({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()
