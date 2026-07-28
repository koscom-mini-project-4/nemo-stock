"""API 통합 테스트: 수동 시세 적재 -> 워크플로 생성 -> 백테스트 실행 -> 결과 조회."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.deps import get_ai_client, get_price_ingest_client
from app.dao.base import PriceBarRecord
from tests.unit.ai_test_doubles import FakeAIClient


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

    # 매매 시점(trades)이 종목/대상 universe와 함께 저장되어야 한다 — 매일 상승하는 합성 시세라
    # if_else(price > prev_close)가 매일 통과해 매수가 15번 모두 체결되어야 한다.
    assert result["universe"] == ["TESTSYM"]
    assert len(result["trades"]) == 15
    assert all(t["symbol"] == "TESTSYM" and t["side"] == "buy" and t["status"] == "filled" for t in result["trades"])
    assert {t["date"] for t in result["trades"]} == {d["date"] for d in result["daily_runs"]}

    # 대상 종목의 시세(OHLCV)를 백테스트 기간 그대로 조회할 수 있어야 한다.
    prices_resp = app_client.get(f"/backtest/{result['id']}/prices", params={"symbol": "TESTSYM"}, headers=auth_headers)
    assert prices_resp.status_code == 200, prices_resp.text
    assert len(prices_resp.json()) == 15

    # 대상이 아닌 종목은 400.
    bad_prices_resp = app_client.get(
        f"/backtest/{result['id']}/prices", params={"symbol": "NOTINUNIVERSE"}, headers=auth_headers
    )
    assert bad_prices_resp.status_code == 400

    # 워크플로에 data.news 노드가 없으므로 "참고한 뉴스"는 비어 있어야 한다.
    news_used_resp = app_client.get(
        f"/backtest/{result['id']}/news/used", params={"symbol": "TESTSYM"}, headers=auth_headers
    )
    assert news_used_resp.status_code == 200
    assert news_used_resp.json() == []

    # news 테이블에 아무것도 적재하지 않았으므로 "전체 뉴스"도 비어 있어야 한다.
    news_all_resp = app_client.get(
        f"/backtest/{result['id']}/news/all", params={"symbol": "TESTSYM"}, headers=auth_headers
    )
    assert news_all_resp.status_code == 200
    assert news_all_resp.json() == []


def test_backtest_with_progress_run_id_publishes_progress_events(app_client: TestClient, auth_headers: dict):
    """§0-11: progress_run_id를 주면 POST /backtest가 끝난 뒤 event_bus에 시작+거래일별
    진행 이벤트가 쌓여 있어야 한다(WS /ws/runs/{id}가 실시간으로 이걸 실어나른다)."""
    start = date(2025, 1, 1)
    app_client.post(
        "/data/ingest/prices/manual",
        json=_bars_payload("TESTSYM", start, days=5, start_price=100.0),
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
            "end_date": (start + timedelta(days=4)).isoformat(),
            "initial_capital": 1_000_000,
            "progress_run_id": "progress-flow-1",
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 201, bt_resp.text

    events = app_client.app.state.container.event_bus.get_history("progress-flow-1")
    assert len(events) == 6  # 시작 1건 + 거래일 5건
    assert events[0].output_snapshot["day_index"] == 0
    assert events[0].output_snapshot["total_days"] == 5
    assert [e.output_snapshot["day_index"] for e in events[1:]] == [1, 2, 3, 4, 5]


def _workflow_payload_with_news() -> dict:
    return {
        "name": "백테스트용 뉴스 참고 매수",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "NEWSSYM"}},
                {"id": "n2", "type": "data.price", "params": {}},
                {"id": "n3", "type": "data.news", "params": {"limit": 3}},
                {"id": "n4", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
                {"id": "n5", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
                {"from": "n3", "to": "n4"},
                {"from": "n4", "to": "n5"},
            ],
        },
    }


def test_backtest_news_used_and_ai_explain(app_client: TestClient, auth_headers: dict):
    """data.news 노드가 그 날 조회한 뉴스만 "참고한 뉴스"로 노출되고, /ai/backtest-explain이
    그 근거 데이터를 포함해 정상 동작하는지 확인한다."""
    start = date(2025, 3, 1)
    app_client.post(
        "/data/ingest/prices/manual",
        json=_bars_payload("NEWSSYM", start, days=5, start_price=100.0),
        headers=auth_headers,
    )
    app_client.post(
        "/data/ingest/news/manual",
        json={
            "symbol": "NEWSSYM",
            "items": [
                {
                    "title": "테스트기업 실적 호조",
                    "body": "분기 실적이 예상치를 상회했다.",
                    "published_at": f"{start.isoformat()}T09:00:00",
                }
            ],
        },
        headers=auth_headers,
    )

    wf_resp = app_client.post("/workflows", json=_workflow_payload_with_news(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    bt_resp = app_client.post(
        "/backtest",
        json={
            "workflow_id": workflow_id,
            "universe": ["NEWSSYM"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=4)).isoformat(),
            "initial_capital": 1_000_000,
        },
        headers=auth_headers,
    )
    assert bt_resp.status_code == 201, bt_resp.text
    result = bt_resp.json()

    news_used_resp = app_client.get(
        f"/backtest/{result['id']}/news/used", params={"symbol": "NEWSSYM"}, headers=auth_headers
    )
    assert news_used_resp.status_code == 200
    used = news_used_resp.json()
    assert len(used) == 5  # 매일 data.news 노드가 실행되며 같은 뉴스를 조회
    assert all(m["used"] is True and m["title"] == "테스트기업 실적 호조" for m in used)

    # /ai/backtest-explain: changed=false(순수 설명) 경로.
    fake_ai = FakeAIClient(
        responses=[{"reply": "이 구간에서는 상승세라 매일 매수했습니다.", "changed": False}]
    )
    app_client.app.dependency_overrides[get_ai_client] = lambda: fake_ai
    try:
        explain_resp = app_client.post(
            "/ai/backtest-explain",
            json={
                "backtest_id": result["id"],
                "message": "왜 매일 매수했는지 설명해줘",
                "selection": {"kind": "range", "symbol": "NEWSSYM", "start_date": start.isoformat(), "end_date": (start + timedelta(days=4)).isoformat()},
            },
            headers=auth_headers,
        )
    finally:
        app_client.app.dependency_overrides.pop(get_ai_client, None)

    assert explain_resp.status_code == 200, explain_resp.text
    body = explain_resp.json()
    assert body["changed"] is False
    assert "매수" in body["reply"]
    assert len(fake_ai.calls) == 1
    # AI에 전달된 프롬프트에 참고 뉴스(used_news)는 포함되지만, news/all 체크박스용 데이터는
    # 별도로 조회하지 않았으므로 프롬프트 조립 과정에 관여하지 않는다(설계 결정).
    _, user_prompt = fake_ai.calls[0]
    assert "테스트기업 실적 호조" in user_prompt


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
