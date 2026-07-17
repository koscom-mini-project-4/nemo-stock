from __future__ import annotations

import pytest

from app.ai.workflow_chat import CHAT_DISCLAIMER, WorkflowChatError, chat_about_workflow
from app.nodes import load_all_nodes
from tests.unit.ai_test_doubles import FakeAIClient

load_all_nodes()

_CURRENT_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
        {"id": "n2", "type": "data.price", "params": {}},
        {"id": "n3", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
}


def _explain_response() -> dict:
    return {"reply": "이 전략은 삼성전자를 60초마다 조회해 시장가로 매수합니다.", "changed": False}


def _edit_response() -> dict:
    return {
        "reply": "매수 수량을 3주로 늘렸습니다.",
        "changed": True,
        "name": "삼성전자 매수 전략",
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "execution.market_order", "params": {"side": "buy", "qty": 3}},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }


def _invalid_edit_response() -> dict:
    # 스케줄러 노드가 없어 검증 실패해야 하는 응답
    return {
        "reply": "수량을 늘렸습니다.",
        "changed": True,
        "name": "잘못된 수정",
        "nodes": [{"id": "n1", "type": "data.price", "params": {}}],
        "edges": [],
    }


def test_chat_explain_returns_reply_without_graph():
    ai_client = FakeAIClient(responses=[_explain_response()])
    result = chat_about_workflow(ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, "지금 이 전략 뭐하는거야?")

    assert result["changed"] is False
    assert result["graph"] is None
    assert result["disclaimer"] is None
    assert "삼성전자" in result["reply"]
    assert len(ai_client.calls) == 1


def test_chat_edit_succeeds_on_first_try():
    ai_client = FakeAIClient(responses=[_edit_response()])
    result = chat_about_workflow(ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, "매수 수량을 3주로 늘려줘")

    assert result["changed"] is True
    assert result["disclaimer"] == CHAT_DISCLAIMER
    assert result["graph"]["nodes"][2]["params"]["qty"] == 3
    assert len(ai_client.calls) == 1


def test_chat_edit_retries_once_then_succeeds():
    ai_client = FakeAIClient(responses=[_invalid_edit_response(), _edit_response()])
    result = chat_about_workflow(ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, "매수 수량을 3주로 늘려줘")

    assert len(ai_client.calls) == 2
    assert result["changed"] is True
    assert "검증 오류" in ai_client.calls[1][1]


def test_chat_edit_raises_after_two_failures():
    ai_client = FakeAIClient(responses=[_invalid_edit_response(), _invalid_edit_response()])
    with pytest.raises(WorkflowChatError) as exc_info:
        chat_about_workflow(ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, "매수 수량을 3주로 늘려줘")

    assert len(ai_client.calls) == 2
    assert len(exc_info.value.attempts) == 2


def test_chat_passes_history_and_last_run_into_prompt():
    ai_client = FakeAIClient(responses=[_explain_response()])
    chat_about_workflow(
        ai_client,
        "삼성전자 매수 전략",
        _CURRENT_GRAPH,
        "방금 실행 어땠어?",
        history=[{"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답변"}],
        last_run={"status": "success", "events": [], "final_symbols": {}},
    )

    user_prompt = ai_client.calls[0][1]
    assert "이전 질문" in user_prompt
    assert "이전 답변" in user_prompt
    assert '"status": "success"' in user_prompt
