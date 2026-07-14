from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.nodes import load_all_nodes

load_all_nodes()


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("database_url", f"sqlite:///{db_path}")
    monkeypatch.setenv("scheduler_tick_seconds", "0.1")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


@pytest.fixture()
def auth_headers(app_client: TestClient) -> dict[str, str]:
    resp = app_client.post("/auth/login", json={"username": "admin", "password": "admin1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
