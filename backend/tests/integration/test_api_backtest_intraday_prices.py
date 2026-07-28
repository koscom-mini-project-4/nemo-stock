"""GET /backtest/{id}/prices?interval=minute60 — 시간봉 데이터가 있으면 시간봉을 반환하는지,
없으면 빈 배열(프론트가 일봉으로 폴백)을 반환하는지 검증."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.dao.base import IntradayPriceBarRecord


def _workflow_payload() -> dict:
    return {
        "name": "시간봉 테스트용",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "TESTSYM"}},
                {"id": "n2", "type": "data.price", "params": {}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        },
    }


def _bars_payload(symbol: str, start: date, days: int, start_price: float) -> dict:
    bars = []
    price = start_price
    for i in range(days):
        d = start + timedelta(days=i)
        close = price * 1.01
        bars.append(
            {"trade_date": d.isoformat(), "open": price, "high": close, "low": price, "close": close, "volume": 10000}
        )
        price = close
    return {"symbol": symbol, "bars": bars}


def _run_backtest(app_client: TestClient, auth_headers: dict, start: date, end: date) -> str:
    app_client.post(
        "/data/ingest/prices/manual",
        json=_bars_payload("TESTSYM", start, days=(end - start).days + 1, start_price=100.0),
        headers=auth_headers,
    )
    wf_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]
    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["TESTSYM"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "initial_capital": 10_000_000,
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 201, bt_resp.text
    return bt_resp.json()["id"]


def test_prices_default_interval_is_daily(app_client: TestClient, auth_headers: dict):
    start, end = date(2025, 1, 1), date(2025, 1, 3)
    result_id = _run_backtest(app_client, auth_headers, start, end)

    resp = app_client.get(f"/backtest/{result_id}/prices", params={"symbol": "TESTSYM"}, headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3
    assert resp.json()[0]["date"] == "2025-01-01"


def test_prices_minute60_returns_intraday_bars_when_available(app_client: TestClient, auth_headers: dict):
    start, end = date(2025, 1, 1), date(2025, 1, 3)
    result_id = _run_backtest(app_client, auth_headers, start, end)

    app_client.app.state.container.intraday_price_bar_repo.save_many([
        IntradayPriceBarRecord(
            symbol="TESTSYM", bar_datetime=datetime(2025, 1, 2, 10, 0), interval="minute60",
            open=100.0, high=101.0, low=99.0, close=100.5, volume=500,
        ),
        IntradayPriceBarRecord(
            symbol="TESTSYM", bar_datetime=datetime(2025, 1, 2, 11, 0), interval="minute60",
            open=100.5, high=102.0, low=100.0, close=101.5, volume=600,
        ),
    ])

    resp = app_client.get(
        f"/backtest/{result_id}/prices", params={"symbol": "TESTSYM", "interval": "minute60"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["date"] == "2025-01-02 10:00"
    assert body[1]["close"] == 101.5


def test_prices_minute60_returns_empty_without_intraday_data(app_client: TestClient, auth_headers: dict):
    start, end = date(2025, 1, 1), date(2025, 1, 3)
    result_id = _run_backtest(app_client, auth_headers, start, end)

    resp = app_client.get(
        f"/backtest/{result_id}/prices", params={"symbol": "TESTSYM", "interval": "minute60"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []
