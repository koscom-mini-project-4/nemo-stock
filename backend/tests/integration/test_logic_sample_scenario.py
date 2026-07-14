"""기획서 logic_sample.png 원본 시나리오 통합 테스트.

Schedule Node(시세 변경 시 실행) -> GET 시세 데이터 -> [트레이딩 전략 조건: True]
-> GET 뉴스/공시 데이터 -> [긍정적 뉴스 데이터: True] -> 구매

Phase 1 통합 테스트(test_api_workflow_flow.py)는 AI/뉴스 노드가 구현되기 전이라
스케줄러->시세->조건->매수로 축소된 버전이었다. 이 테스트는 Phase 3에서 추가된
data.news/ai.sentiment_score까지 포함해 원본 다이어그램 그대로를 검증한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai.base import AIClient
from tests.unit.ai_test_doubles import FakeAIClient

SYMBOL = "005930"


def _install_fake_ai_client(app_client: TestClient, fake_ai: FakeAIClient) -> AIClient:
    """/workflows/{id}/run은 container.node_providers()를 통해 container.ai_client를 직접
    읽으므로(별도 FastAPI Depends 경유가 아님) app.state.container.ai_client를 바로 교체한다.
    (/ai/generate-draft처럼 Depends(get_ai_client)를 쓰는 라우터는 dependency_overrides로 충분하다.)
    """
    container = app_client.app.state.container
    original = container.ai_client
    container.ai_client = fake_ai
    return original


def _scenario_graph() -> dict:
    return {
        "name": "logic_sample 원본 시나리오",
        "schedule_interval_sec": 1,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 1, "universe": SYMBOL}},
                {"id": "n2", "type": "data.price", "params": {}},
                {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
                {"id": "n4", "type": "data.news", "params": {"limit": 3}},
                {"id": "n5", "type": "ai.sentiment_score", "params": {"source": "news"}},
                {"id": "n6", "type": "logic.if_else", "params": {"expr": "sentiment_score > 50"}},
                {"id": "n7", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
                {"from": "n3", "to": "n4"},
                {"from": "n4", "to": "n5"},
                {"from": "n5", "to": "n6"},
                {"from": "n6", "to": "n7"},
            ],
        },
    }


def _seed_positive_news(app_client: TestClient, auth_headers: dict) -> None:
    resp = app_client.post(
        "/data/ingest/news/manual",
        json={
            "symbol": SYMBOL,
            "items": [
                {
                    "title": "실적 서프라이즈",
                    "body": "분기 영업이익이 시장 예상치를 크게 상회했다.",
                    "published_at": "2026-07-14T09:00:00",
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


def test_uptrend_and_positive_news_leads_to_buy(app_client: TestClient, auth_headers: dict):
    _seed_positive_news(app_client, auth_headers)

    wf_resp = app_client.post("/workflows", json=_scenario_graph(), headers=auth_headers)
    assert wf_resp.status_code == 201, wf_resp.text
    workflow_id = wf_resp.json()["id"]

    validate_resp = app_client.post(f"/workflows/{workflow_id}/validate", headers=auth_headers)
    assert validate_resp.json()["valid"] is True

    fake_ai = FakeAIClient(responses=[{"score": 85, "summary": "매우 긍정적인 실적 발표"}])
    original_ai = _install_fake_ai_client(app_client, fake_ai)
    try:
        run_resp = app_client.post(
            f"/workflows/{workflow_id}/run",
            # 상승(price>prev_close) 오버라이드로 첫 번째 조건(트레이딩 전략)을 통과시킨다.
            json={"overrides": {"n2": {SYMBOL: {"price": 71000, "prev_close": 70000}}}},
            headers=auth_headers,
        )
    finally:
        app_client.app.state.container.ai_client = original_ai

    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    assert result["status"] == "success"
    assert result["final_symbols"][SYMBOL]["order_status"] == "filled"
    assert result["final_symbols"][SYMBOL]["sentiment_score"] == 85.0
    assert len(fake_ai.calls) == 1

    node_ids_seen = {e["node_id"] for e in result["events"]}
    assert node_ids_seen == {"n1", "n2", "n3", "n4", "n5", "n6", "n7"}


def test_negative_news_blocks_buy_even_when_price_uptrend(app_client: TestClient, auth_headers: dict):
    _seed_positive_news(app_client, auth_headers)  # 뉴스 자체는 있지만 AI 판단이 부정적인 케이스

    wf_resp = app_client.post("/workflows", json=_scenario_graph(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    fake_ai = FakeAIClient(responses=[{"score": -40, "summary": "우려가 반영된 실적"}])
    original_ai = _install_fake_ai_client(app_client, fake_ai)
    try:
        run_resp = app_client.post(
            f"/workflows/{workflow_id}/run",
            json={"overrides": {"n2": {SYMBOL: {"price": 71000, "prev_close": 70000}}}},
            headers=auth_headers,
        )
    finally:
        app_client.app.state.container.ai_client = original_ai

    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    assert result["final_symbols"] == {}  # 두 번째 if_else(긍정 뉴스)에서 탈락
    assert len(fake_ai.calls) == 1  # AI가 실제로 호출되었는지 확인(회피 경로로 우연히 통과한 것이 아님)


def test_downtrend_price_blocks_before_news_lookup(app_client: TestClient, auth_headers: dict):
    """첫 번째 조건(가격 상승)에서 탈락하면 뉴스/AI 단계까지 도달하지 않아야 한다."""
    _seed_positive_news(app_client, auth_headers)

    wf_resp = app_client.post("/workflows", json=_scenario_graph(), headers=auth_headers)
    workflow_id = wf_resp.json()["id"]

    fake_ai = FakeAIClient(responses=[])  # 호출되면 AssertionError -> 테스트 실패로 드러남
    original_ai = _install_fake_ai_client(app_client, fake_ai)
    try:
        run_resp = app_client.post(
            f"/workflows/{workflow_id}/run",
            json={"overrides": {"n2": {SYMBOL: {"price": 69000, "prev_close": 70000}}}},
            headers=auth_headers,
        )
    finally:
        app_client.app.state.container.ai_client = original_ai

    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    assert result["final_symbols"] == {}
    assert len(fake_ai.calls) == 0
