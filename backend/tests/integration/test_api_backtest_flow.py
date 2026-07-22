"""API 통합 테스트: 수동 시세 적재 -> 워크플로 생성 -> 백테스트 실행 -> 결과 조회."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.deps import get_price_ingest_client
from app.dao.base import PriceBarRecord


def _bars_payload(symbol: str, start: date, days: int, start_price: float) -> dict:
    bars = []
    price = start_price
    for i in range(days):
        d = start + timedelta(days=i)
        close = price * 1.01
        bars.append(
            {
                "trade_date": d.isoformat(),
                "open": price,
                "high": close,
                "low": price,
                "close": close,
                "volume": 10000,
            }
        )
        price = close
    return {"symbol": symbol, "bars": bars}


def _workflow_payload() -> dict:
    return {
        "name": "백테스트용 상승추세 매수",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "TESTSYM"}},
                {"id": "n2", "type": "data.price", "params": {}},
                {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
                {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
                {"from": "n3", "to": "n4"},
            ],
        },
    }


def test_manual_ingest_then_backtest_end_to_end(app_client: TestClient, auth_headers: dict):
    start = date(2025, 1, 1)
    ingest_resp = app_client.post(
        "/data/ingest/prices/manual",
        json=_bars_payload("TESTSYM", start, days=15, start_price=100.0),
        headers=auth_headers,
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["ingested"] == 15

    wf_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    assert wf_resp.status_code == 201
    workflow_id = wf_resp.json()["id"]

    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["TESTSYM"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=14)).isoformat(),
            "initial_capital": 1_000_000,
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 201, bt_resp.text
    result = bt_resp.json()
    assert result["trade_count"] >= 0
    assert len(result["equity_curve"]) == 15
    assert result["final_equity"] > result["initial_capital"]

    get_resp = app_client.get(f"/backtest/{result['id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == result["id"]

    # 거래일마다 별도 run_id가 저장되어 일자별 노드 그래프를 재생할 수 있어야 한다.
    assert len(result["daily_runs"]) == 15
    first_run = result["daily_runs"][0]
    run_resp = app_client.get(f"/workflows/{workflow_id}/runs/{first_run['run_id']}", headers=auth_headers)
    assert run_resp.status_code == 200, run_resp.text
    run_out = run_resp.json()
    assert run_out["mode"] == "backtest"
    assert len(run_out["events"]) > 0
    assert any(e["node_id"] == "n1" for e in run_out["events"])


def test_backtest_without_price_data_returns_400(app_client: TestClient, auth_headers: dict):
    wf_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["NODATA"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 400


def test_public_ingest_without_service_key_returns_400(app_client: TestClient, auth_headers: dict):
    resp = app_client.post(
        "/data/ingest/prices/public",
        json={"symbol": "005930", "start": "2025-01-01", "end": "2025-01-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


class _FakeNaverClient:
    def __init__(self, bars: list[PriceBarRecord]):
        self.bars = bars
        self.calls = 0

    def fetch_daily_bars(self, symbol: str, start: date, end: date) -> list[PriceBarRecord]:
        self.calls += 1
        return self.bars

    def fetch_hourly_bars(self, symbol: str, start: date, end: date) -> list:
        return []


def test_backtest_auto_ingests_missing_prices_when_enabled(app_client: TestClient, auth_headers: dict):
    """auto_ingest_prices=true면 데이터가 없어도 자동 수집 후 백테스트가 성공해야 한다."""
    start = date(2025, 2, 1)
    fake_bars = []
    price = 100.0
    for i in range(10):
        d = start + timedelta(days=i)
        close = price * 1.01
        fake_bars.append(
            PriceBarRecord(symbol="AUTOSYM", trade_date=d, open=price, high=close, low=price, close=close, volume=1000)
        )
        price = close
    fake_client = _FakeNaverClient(fake_bars)

    app_client.app.state.container.settings.auto_ingest_prices = True
    app_client.app.dependency_overrides[get_price_ingest_client] = lambda: fake_client
    try:
        wf_resp = app_client.post(
            "/workflows",
            json={
                "name": "자동수집 백테스트",
                "schedule_interval_sec": 60,
                "graph": {
                    "nodes": [
                        {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "AUTOSYM"}},
                        {"id": "n2", "type": "data.price", "params": {}},
                        {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
                        {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
                    ],
                    "edges": [
                        {"from": "n1", "to": "n2"},
                        {"from": "n2", "to": "n3"},
                        {"from": "n3", "to": "n4"},
                    ],
                },
            },
            headers=auth_headers,
        )
        workflow_id = wf_resp.json()["id"]

        bt_resp = app_client.post(
            "/backtest",
            json={
                "workflow_id": workflow_id,
                "universe": ["AUTOSYM"],
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=9)).isoformat(),
                "initial_capital": 1_000_000,
            },
            headers=auth_headers,
        )
        assert bt_resp.status_code == 201, bt_resp.text
        assert fake_client.calls == 1

        # 자동 수집된 데이터가 실제로 저장됐는지 확인 — 두 번째 시도에서는 이미 데이터가 있으므로 재수집하지 않는다.
        bt_resp_2 = app_client.post(
            "/backtest",
            json={
                "workflow_id": workflow_id,
                "universe": ["AUTOSYM"],
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=9)).isoformat(),
                "initial_capital": 1_000_000,
            },
            headers=auth_headers,
        )
        assert bt_resp_2.status_code == 201
        assert fake_client.calls == 1
    finally:
        app_client.app.dependency_overrides.pop(get_price_ingest_client, None)
