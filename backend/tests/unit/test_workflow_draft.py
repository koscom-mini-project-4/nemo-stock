from __future__ import annotations

import pytest

from app.ai.workflow_draft import DISCLAIMER, WorkflowDraftError, generate_workflow_draft
from app.nodes import load_all_nodes
from tests.unit.ai_test_doubles import FakeAIClient

load_all_nodes()


def _valid_graph_response() -> dict:
    return {
        "name": "상승 종목 매수",
        "description": "전일 대비 상승한 종목을 매수하는 전략입니다.",
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
        ],
    }


def _invalid_graph_response() -> dict:
    # 스케줄러 노드가 없어 검증 실패해야 하는 응답
    return {
        "name": "잘못된 초안",
        "nodes": [{"id": "n1", "type": "data.price", "params": {}}],
        "edges": [],
    }


def test_generate_draft_succeeds_on_first_try():
    ai_client = FakeAIClient(responses=[_valid_graph_response()])
    draft = generate_workflow_draft(ai_client, "상승 종목을 사고 싶다")

    assert draft["name"] == "상승 종목 매수"
    assert draft["description"] == "전일 대비 상승한 종목을 매수하는 전략입니다."
    assert draft["disclaimer"] == DISCLAIMER
    assert len(draft["graph"]["nodes"]) == 4
    assert len(ai_client.calls) == 1


def test_generate_draft_defaults_description_to_empty_string_when_missing():
    response = _valid_graph_response()
    del response["description"]
    ai_client = FakeAIClient(responses=[response])
    draft = generate_workflow_draft(ai_client, "상승 종목을 사고 싶다")

    assert draft["description"] == ""


def test_generate_draft_retries_once_then_succeeds():
    ai_client = FakeAIClient(responses=[_invalid_graph_response(), _valid_graph_response()])
    draft = generate_workflow_draft(ai_client, "상승 종목을 사고 싶다")

    assert len(ai_client.calls) == 2
    assert len(draft["graph"]["nodes"]) == 4
    # 두 번째(재시도) 프롬프트에는 첫 시도의 오류 내용이 포함되어야 한다.
    assert "검증 오류" in ai_client.calls[1][1]


def test_generate_draft_raises_after_two_failures():
    ai_client = FakeAIClient(responses=[_invalid_graph_response(), _invalid_graph_response()])
    with pytest.raises(WorkflowDraftError) as exc_info:
        generate_workflow_draft(ai_client, "상승 종목을 사고 싶다")

    assert len(ai_client.calls) == 2
    assert len(exc_info.value.attempts) == 2
