"""POST /data/symbols/sync, GET /data/symbols/stats — 종목 마스터 캐시 동기화(§0-10).

실제 공공데이터포털/KOSCOM CHECK-API 호출 없이 PublicDataPriceClient.fetch_market_snapshot /
KoscomMarketDataProvider.fetch_symbol_master를 몽키패치해 검증한다. 공공데이터포털이 빈
응답만 줄 때 KOSCOM CHECK-API로 폴백하는 경로(2026-07-28 실사용 중 발견한 문제의 대응)가
핵심 검증 대상이다.
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


def test_sync_symbols_requires_service_key_or_koscom_credentials(app_client: TestClient, auth_headers: dict):
    """공공데이터 키도, KOSCOM 자격증명도 둘 다 없으면(테스트 환경 기본값) 400."""
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
    assert body == {"synced": 2, "as_of": "2026-07-27", "source": "data.go.kr"}

    # in-memory 캐시가 즉시 교체돼 이 프로세스 내 다른 조회에도 바로 반영돼야 한다.
    assert symbol_master.get_symbol_name("000270") == "기아"

    stats_resp = app_client.get("/data/symbols/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json() == {"count": 2, "db_count": 2}

    search_resp = app_client.get("/data/symbols", params={"q": "기아"}, headers=auth_headers)
    assert [s["symbol"] for s in search_resp.json()] == ["000270"]


def test_sync_symbols_falls_back_to_koscom_when_public_data_empty(
    app_client: TestClient, auth_headers: dict, monkeypatch
):
    """§0-10 폴백: 공공데이터 키가 설정돼 있어도 응답이 비어 있으면(2026-07-28 실사용 중
    확인된 상황) KOSCOM CHECK-API로 자동 전환해야 한다."""
    container = app_client.app.state.container
    container.settings.data_go_kr_service_key = "dummy-key"
    container.settings.koscom_cust_id = "NS00000001"
    container.settings.koscom_auth_key = "authkey123"

    def _empty_snapshot(self, as_of, **kwargs):
        return as_of, []

    def _fake_fetch_symbol_master(self):
        return [
            {"symbol": "005930", "name": "삼성전자", "market": "KOSPI"},
            {"symbol": "066570", "name": "LG전자", "market": "KOSDAQ"},
        ]

    monkeypatch.setattr(
        "app.data_ingestion.public_data_price.PublicDataPriceClient.fetch_market_snapshot", _empty_snapshot
    )
    monkeypatch.setattr(
        "app.market_data.koscom_adapter.KoscomMarketDataProvider.fetch_symbol_master", _fake_fetch_symbol_master
    )

    resp = app_client.post("/data/symbols/sync", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "koscom"
    assert body["synced"] == 2
    assert symbol_master.get_symbol_name("066570") == "LG전자"


def test_sync_symbols_returns_400_when_public_data_empty_and_no_koscom_credentials(
    app_client: TestClient, auth_headers: dict, monkeypatch
):
    app_client.app.state.container.settings.data_go_kr_service_key = "dummy-key"

    def _empty_snapshot(self, as_of, **kwargs):
        return as_of, []

    monkeypatch.setattr(
        "app.data_ingestion.public_data_price.PublicDataPriceClient.fetch_market_snapshot", _empty_snapshot
    )

    resp = app_client.post("/data/symbols/sync", headers=auth_headers)
    assert resp.status_code == 400


def test_symbols_stats_before_sync_reports_fallback_seed(app_client: TestClient, auth_headers: dict):
    resp = app_client.get("/data/symbols/stats", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 8, "db_count": 0}
