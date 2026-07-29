"""API 통합 테스트: AI 초안 생성, 뉴스/공시 수집 엔드포인트.

실제 OpenAI 호출 없이 FastAPI dependency_overrides로 get_ai_client를 FakeAIClient로 교체한다.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.deps import get_ai_client, get_strategy_ai_client
from app.dao.base import AIUsageRecord
from tests.unit.ai_test_doubles import FakeAIClient


class _UsageRecordingFakeClient(FakeAIClient):
    """§0-11: 실제 OpenAIClient._record_usage()가 하는 것처럼, 호출마다 container의
    ai_usage_repo에 사용량을 기록하는 FakeAIClient. 델타 계산 로직(app/api/routers/ai.py::
    _usage_delta)이 실제로 새 레코드를 반영하는지 검증하는 데 쓴다."""

    def __init__(self, container, tokens: int, **kwargs):
        super().__init__(**kwargs)
        self._container = container
        self._tokens = tokens
        self._call_no = 0

    def complete_json(self, *args, **kwargs):
        self._call_no += 1
        self._container.ai_usage_repo.save(
            AIUsageRecord(
                id=f"usage-{id(self)}-{self._call_no}", purpose="test", model=self._model,
                prompt_tokens=self._tokens, completion_tokens=0, total_tokens=self._tokens,
            )
        )
        return super().complete_json(*args, **kwargs)

_VALID_DRAFT_RESPONSE = {
    "name": "뉴스 긍정 매수 전략",
    "nodes": [
        {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
        {"id": "n2", "type": "data.price", "params": {}},
        {"id": "n3", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
}


def test_generate_draft_without_api_key_returns_400(app_client: TestClient, auth_headers: dict):
    resp = app_client.post("/ai/generate-draft", json={"idea": "긍정 뉴스 나온 종목을 산다"}, headers=auth_headers)
    assert resp.status_code == 400


def test_generate_draft_with_fake_ai_client_returns_valid_workflow(app_client: TestClient, auth_headers: dict):
    fake_client = FakeAIClient(responses=[_VALID_DRAFT_RESPONSE])
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_client
    try:
        resp = app_client.post("/ai/generate-draft", json={"idea": "긍정 뉴스 나온 종목을 산다"}, headers=auth_headers)
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "뉴스 긍정 매수 전략"
    assert "disclaimer" in body and body["disclaimer"]
    assert len(body["graph"]["nodes"]) == 3


def test_generate_draft_created_workflow_can_be_saved_and_validated(app_client: TestClient, auth_headers: dict):
    fake_client = FakeAIClient(responses=[_VALID_DRAFT_RESPONSE])
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_client
    try:
        draft_resp = app_client.post("/ai/generate-draft", json={"idea": "테스트"}, headers=auth_headers)
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)
    draft = draft_resp.json()

    create_resp = app_client.post(
        "/workflows",
        json={"name": draft["name"], "graph": draft["graph"], "schedule_interval_sec": 60},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["id"]

    validate_resp = app_client.post(f"/workflows/{workflow_id}/validate", headers=auth_headers)
    assert validate_resp.json()["valid"] is True


def test_generate_draft_response_includes_ai_usage_delta(app_client: TestClient, auth_headers: dict):
    """§0-11: 이 호출 동안 새로 쌓인 토큰 사용량이 응답의 usage 필드에 실려야 한다."""
    container = app_client.app.state.container
    fake_client = _UsageRecordingFakeClient(container, tokens=120, responses=[_VALID_DRAFT_RESPONSE])
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_client
    try:
        resp = app_client.post("/ai/generate-draft", json={"idea": "테스트"}, headers=auth_headers)
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["usage"] == {"prompt_tokens": 120, "completion_tokens": 0, "total_tokens": 120}


def test_generate_draft_usage_is_null_when_nothing_recorded(app_client: TestClient, auth_headers: dict):
    """usage_repo에 새로 기록된 게 없으면(FakeAIClient는 기본적으로 기록 안 함) usage는 null."""
    fake_client = FakeAIClient(responses=[_VALID_DRAFT_RESPONSE])
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_client
    try:
        resp = app_client.post("/ai/generate-draft", json={"idea": "테스트"}, headers=auth_headers)
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["usage"] is None


def _read_sse_frames(response) -> list[dict]:
    frames = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            frames.append(json.loads(line[len("data: "):]))
    return frames


def test_generate_draft_stream_sends_chunk_frames_then_result(app_client: TestClient, auth_headers: dict):
    """§0-18: /ai/generate-draft/stream이 chunk 프레임을 실시간으로 보내고 마지막에 기존
    블로킹 엔드포인트와 동일한 필드를 담은 result 프레임 하나로 끝나는지 확인한다."""
    fake_client = FakeAIClient(responses=[_VALID_DRAFT_RESPONSE])
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_client
    try:
        with app_client.stream(
            "POST", "/ai/generate-draft/stream", json={"idea": "긍정 뉴스 나온 종목을 산다"}, headers=auth_headers
        ) as resp:
            assert resp.status_code == 200
            frames = _read_sse_frames(resp)
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)

    assert len(frames) >= 2
    assert all(f["type"] in ("chunk", "result") for f in frames)
    assert frames[-1]["type"] == "result"
    assert frames[-1]["name"] == "뉴스 긍정 매수 전략"
    assert len(frames[-1]["graph"]["nodes"]) == 3
    # chunk 프레임들을 이어붙이면 최종 결과와 동일한 원문 JSON이 나와야 한다(FakeAIClient가
    # 단일 청크로 흉내내지만 인터페이스 계약은 동일).
    assert any(f["type"] == "chunk" for f in frames)


def test_generate_draft_stream_without_api_key_returns_400(app_client: TestClient, auth_headers: dict):
    """스트림 시작 전에 available 체크가 먼저 실패하므로 일반 HTTPException(400)으로 응답한다."""
    resp = app_client.post("/ai/generate-draft/stream", json={"idea": "테스트"}, headers=auth_headers)
    assert resp.status_code == 400


def test_generate_draft_uses_strategy_ai_client_not_default(app_client: TestClient, auth_headers: dict):
    """§0-19: /ai/generate-draft는 get_strategy_ai_client를 쓰고 /ai/workflow-chat 등은
    get_ai_client를 쓴다 — 둘이 실제로 다른 의존성 함수라는 걸 확인한다. strategy_ai_client만
    오버라이드해 generate-draft는 성공하고, ai_client가 없는(기본값=진짜 컨테이너의
    available=False) workflow-chat은 여전히 400인지로 검증."""
    fake_strategy_client = FakeAIClient(responses=[_VALID_DRAFT_RESPONSE], model="strategy-model")
    app_client.app.dependency_overrides[get_strategy_ai_client] = lambda: fake_strategy_client
    try:
        draft_resp = app_client.post(
            "/ai/generate-draft", json={"idea": "긍정 뉴스 나온 종목을 산다"}, headers=auth_headers
        )
        chat_resp = app_client.post(
            "/ai/workflow-chat",
            json={"name": "테스트", "graph": {"nodes": [], "edges": []}, "message": "안녕", "history": []},
            headers=auth_headers,
        )
    finally:
        app_client.app.dependency_overrides.pop(get_strategy_ai_client, None)

    assert draft_resp.status_code == 200, draft_resp.text
    assert chat_resp.status_code == 400  # get_ai_client는 오버라이드 안 했으니 여전히 미설정


def test_workflow_chat_without_api_key_returns_400(app_client: TestClient, auth_headers: dict):
    resp = app_client.post(
        "/ai/workflow-chat",
        json={"name": "전략", "graph": {"nodes": [], "edges": []}, "message": "설명해줘"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_workflow_chat_explain_returns_reply_without_graph_change(app_client: TestClient, auth_headers: dict):
    fake_client = FakeAIClient(responses=[{"reply": "삼성전자를 매수하는 전략입니다.", "changed": False}])
    app_client.app.dependency_overrides[get_ai_client] = lambda: fake_client
    try:
        resp = app_client.post(
            "/ai/workflow-chat",
            json={"name": "전략", "graph": _VALID_DRAFT_RESPONSE, "message": "지금 뭐하는거야?"},
            headers=auth_headers,
        )
    finally:
        app_client.app.dependency_overrides.pop(get_ai_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] is False
    assert body["graph"] is None


def test_workflow_chat_edit_returns_updated_graph(app_client: TestClient, auth_headers: dict):
    edited_graph = {
        "reply": "수량을 2주로 늘렸습니다.",
        "changed": True,
        "name": "뉴스 긍정 매수 전략",
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "execution.market_order", "params": {"side": "buy", "qty": 2}},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }
    fake_client = FakeAIClient(responses=[edited_graph])
    app_client.app.dependency_overrides[get_ai_client] = lambda: fake_client
    try:
        resp = app_client.post(
            "/ai/workflow-chat",
            json={"name": "전략", "graph": _VALID_DRAFT_RESPONSE, "message": "수량을 2주로 늘려줘"},
            headers=auth_headers,
        )
    finally:
        app_client.app.dependency_overrides.pop(get_ai_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] is True
    assert body["graph"]["nodes"][2]["params"]["qty"] == 2
    assert body["disclaimer"]


def test_workflow_chat_response_includes_ai_usage_delta(app_client: TestClient, auth_headers: dict):
    container = app_client.app.state.container
    fake_client = _UsageRecordingFakeClient(
        container, tokens=55, responses=[{"reply": "설명입니다.", "changed": False}]
    )
    app_client.app.dependency_overrides[get_ai_client] = lambda: fake_client
    try:
        resp = app_client.post(
            "/ai/workflow-chat",
            json={"name": "전략", "graph": _VALID_DRAFT_RESPONSE, "message": "지금 뭐하는거야?"},
            headers=auth_headers,
        )
    finally:
        app_client.app.dependency_overrides.pop(get_ai_client, None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["usage"] == {"prompt_tokens": 55, "completion_tokens": 0, "total_tokens": 55}


def test_ingest_manual_news(app_client: TestClient, auth_headers: dict):
    resp = app_client.post(
        "/data/ingest/news/manual",
        json={
            "symbol": "005930",
            "items": [
                {"title": "실적 발표", "body": "영업이익 증가", "published_at": "2025-01-01T09:00:00"},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 1


def test_ingest_public_disclosures_without_key_returns_400(app_client: TestClient, auth_headers: dict):
    resp = app_client.post(
        "/data/ingest/disclosures/public",
        json={"symbols": ["005930"], "start": "2025-01-01", "end": "2025-01-10"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
