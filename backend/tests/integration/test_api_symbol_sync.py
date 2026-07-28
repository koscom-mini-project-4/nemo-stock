"""POST /data/symbols/sync, GET /data/symbols/stats — 종목 마스터 캐시 동기화(§0-10).

실제 공공데이터포털 호출 없이 PublicDataPriceClient.fetch_market_snapshot을 몽키패치해
검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.market_data import symbol_master


@pytest.fixture(autouse=True)
def _restore_symbol_cache():
    original = symbol_master.list_symbols()
    yield
    symbol_master.load_cache(original)


def test_sync_symbols_requires_service_key(app_client: TestClient, auth_headers: dict):
    resp = app_client.post("/data/symbols/sync", headers=auth_headers)
    assert resp.status_code == 400


def test_sync_symbols_updates_cache_and_repo(app_client: TestClient, auth_headers: dict, monkeypatch):
    app_client.app.state.container.settings.data_go_kr_service_key = "dummy-key"

    def _fake_fetch_market_snapshot(self, as_of, **kwargs):
        return date(2026, 7, 27), [
            {"symbol": "000270", "name": "기아", "market": "KOSPI"},
            {"symbol": "066570", "name": "LG전자", "market": "KOSPI"},
        ]

    monkeypatch.setattr(
        "app.data_ingestion.public_data_price.PublicDataPriceClient.fetch_market_snapshot",
        _fake_fetch_market_snapshot,
    )

    resp = app_client.post("/data/symbols/sync", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"synced": 2, "as_of": "2026-07-27"}

    # in-memory 캐시가 즉시 교체돼 이 프로세스 내 다른 조회에도 바로 반영돼야 한다.
    assert symbol_master.get_symbol_name("000270") == "기아"

    stats_resp = app_client.get("/data/symbols/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json() == {"count": 2, "db_count": 2}

    search_resp = app_client.get("/data/symbols", params={"q": "기아"}, headers=auth_headers)
    assert [s["symbol"] for s in search_resp.json()] == ["000270"]


def test_symbols_stats_before_sync_reports_fallback_seed(app_client: TestClient, auth_headers: dict):
    resp = app_client.get("/data/symbols/stats", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 8, "db_count": 0}


def test_symbol_sync_endpoints_require_auth(app_client: TestClient):
    assert app_client.post("/data/symbols/sync").status_code == 401
    assert app_client.get("/data/symbols/stats").status_code == 401
