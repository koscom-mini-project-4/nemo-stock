"""ai.news_signal 노드가 포함된 워크플로의 백테스트 기간 제한(AI 호출량 제한) +
뉴스 마커(/backtest/{id}/news/signal) 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.routers.backtest import NEWS_SIGNAL_BACKTEST_MAX_DAYS
from tests.unit.ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory


def _workflow_with_news_signal_payload() -> dict:
    return {
        "name": "뉴스신호 포함 백테스트",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "TESTSYM"}},
                {"id": "n2", "type": "data.price", "params": {}},
                {
                    "id": "n3",
                    "type": "ai.news_signal",
                    "params": {"axis": "종목", "period_days": 7, "auto_update": False, "pass_when": "중립 아님"},
                },
            ],
            "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
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


def test_backtest_over_limit_with_news_signal_is_rejected(app_client: TestClient, auth_headers: dict):
    wf_resp = app_client.post("/workflows", json=_workflow_with_news_signal_payload(), headers=auth_headers)
    assert wf_resp.status_code == 201
    workflow_id = wf_resp.json()["id"]

    start = date(2025, 1, 1)
    end = start + timedelta(days=NEWS_SIGNAL_BACKTEST_MAX_DAYS + 5)  # 제한을 확실히 초과
    resp = app_client.post(
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

    assert resp.status_code == 400
    assert f"{NEWS_SIGNAL_BACKTEST_MAX_DAYS}일" in resp.json()["detail"]


def test_backtest_over_limit_with_free_prompt_is_rejected(app_client: TestClient, auth_headers: dict):
    """ai.free_prompt(§0-9)도 심볼×거래일마다 실제 AI 호출이 나가 동일한 기간 제한이 적용된다."""
    payload = {
        "name": "자유 프롬프트 포함 백테스트",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "TESTSYM"}},
                {"id": "n2", "type": "ai.free_prompt", "params": {"prompt": "무조건 통과", "data_mode": "치환"}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        },
    }
    wf_resp = app_client.post("/workflows", json=payload, headers=auth_headers)
    assert wf_resp.status_code == 201
    workflow_id = wf_resp.json()["id"]

    start = date(2025, 1, 1)
    end = start + timedelta(days=NEWS_SIGNAL_BACKTEST_MAX_DAYS + 5)
    resp = app_client.post(
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

    assert resp.status_code == 400
    assert "ai.free_prompt" in resp.json()["detail"]


def test_backtest_within_limit_with_news_signal_proceeds(app_client: TestClient, auth_headers: dict):
    start = date(2025, 1, 1)
    ingest_resp = app_client.post(
        "/data/ingest/prices/manual", json=_bars_payload("TESTSYM", start, days=10, start_price=100.0), headers=auth_headers
    )
    assert ingest_resp.status_code == 200

    wf_resp = app_client.post("/workflows", json=_workflow_with_news_signal_payload(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    trader = FakeNewsTrader({"TESTSYM": {"판정": "t", "평균": 0.2, "클러스터수": 1}})
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["TESTSYM"],
            "start_date": "2025-01-02",
            "end_date": "2025-01-05",  # 4일(제한 이내)
            "initial_capital": 10_000_000,
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text


def test_backtest_news_signal_markers_come_from_newsstock_not_news_repo(app_client: TestClient, auth_headers: dict):
    """버그 재현 + 수정 검증: ai.news_signal만 쓰는 워크플로는 /news/used·/news/all이 항상 빈
    배열이지만(구 파이프라인 전용), 신규 /news/signal은 newsstock 클러스터를 마커로 돌려준다."""
    start = date(2025, 1, 1)
    ingest_resp = app_client.post(
        "/data/ingest/prices/manual", json=_bars_payload("TESTSYM", start, days=10, start_price=100.0), headers=auth_headers
    )
    assert ingest_resp.status_code == 200

    workflow_payload = _workflow_with_news_signal_payload()
    workflow_payload["graph"]["nodes"][2]["params"] = {
        "axis": "섹터",
        "key": "반도체 및 반도체 장비",
        "period_days": 7,
        "auto_update": False,
        "pass_when": "중립 아님",
    }
    wf_resp = app_client.post("/workflows", json=workflow_payload, headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    trader = FakeNewsTrader({
        "반도체 및 반도체 장비": {
            "판정": "t",
            "평균": 0.42,
            "클러스터수": 1,
            "클러스터": [
                {"클러스터id": 7, "대표제목": "반도체 수출 호조", "최초발생날짜": "2025-01-03 09:00:00", "점수": 0.6},
            ],
        }
    })
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["TESTSYM"],
            "start_date": "2025-01-02",
            "end_date": "2025-01-05",
            "initial_capital": 10_000_000,
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 201, bt_resp.text
    result_id = bt_resp.json()["id"]

    used_resp = app_client.get(f"/backtest/{result_id}/news/used", params={"symbol": "TESTSYM"}, headers=auth_headers)
    all_resp = app_client.get(f"/backtest/{result_id}/news/all", params={"symbol": "TESTSYM"}, headers=auth_headers)
    assert used_resp.json() == []
    assert all_resp.json() == []

    signal_resp = app_client.get(f"/backtest/{result_id}/news/signal", params={"symbol": "TESTSYM"}, headers=auth_headers)
    assert signal_resp.status_code == 200, signal_resp.text
    markers = signal_resp.json()
    assert len(markers) == 1
    assert markers[0]["title"] == "반도체 수출 호조"
    assert markers[0]["date"] == "2025-01-03"
    assert markers[0]["source"] == "newsstock"
    assert markers[0]["used"] is True


def test_backtest_news_signal_returns_empty_without_news_signal_node(app_client: TestClient, auth_headers: dict):
    start = date(2025, 1, 1)
    app_client.post(
        "/data/ingest/prices/manual", json=_bars_payload("TESTSYM", start, days=10, start_price=100.0), headers=auth_headers
    )
    wf_resp = app_client.post(
        "/workflows",
        json={
            "name": "뉴스신호 없는 백테스트",
            "schedule_interval_sec": 60,
            "graph": {
                "nodes": [
                    {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "TESTSYM"}},
                    {"id": "n2", "type": "data.price", "params": {}},
                ],
                "edges": [{"from": "n1", "to": "n2"}],
            },
        },
        headers=auth_headers,
    )
    workflow_id = wf_resp.json()["id"]
    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["TESTSYM"],
            "start_date": "2025-01-02",
            "end_date": "2025-01-05",
            "initial_capital": 10_000_000,
        },
        headers=auth_headers,
    )
    result_id = bt_resp.json()["id"]

    signal_resp = app_client.get(f"/backtest/{result_id}/news/signal", params={"symbol": "TESTSYM"}, headers=auth_headers)
    assert signal_resp.status_code == 200
    assert signal_resp.json() == []
