import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Every test gets its own empty database, so none can read or write a real one."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    from app.db import init_db
    init_db()


@pytest.fixture
def client(_isolated_db):
    from app.main import app
    with TestClient(app) as c:
        yield c
