from __future__ import annotations

import pytest

from app.ai.backtest_explain import BACKTEST_EXPLAIN_DISCLAIMER, BacktestExplainError, explain_backtest
from app.nodes import load_all_nodes
from tests.unit.ai_test_doubles import FakeAIClient

load_all_nodes()

_CURRENT_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
        {"id": "n2", "type": "data.price", "params": {}},
        {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
        {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
    ],
    "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"}],
}

_SELECTION = {
    "kind": "range",
    "symbol": "005930",
    "start_date": "2025-01-01",
    "end_date": "2025-01-05",
    "trades": [],
    "daily_summaries": [
        {"date": "2025-01-02", "nodes": [{"node_id": "n3", "node_type": "logic.if_else", "status": "success", "symbols": [], "filtered_out": ["005930"]}]}
    ],
    "price_series": [{"date": "2025-01-02", "close": 100.0}],
    "used_news": [],
}


def _explain_response() -> dict:
    return {"reply": "이 구간은 조건식이 False라 매수가 없었습니다.", "changed": False}


def _fix_response() -> dict:
    return {
        "reply": "조건식을 완화해 매수가 발생하도록 수정했습니다.",
        "changed": True,
        "name": "삼성전자 매수 전략",
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "logic.if_else", "params": {"expr": "True"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"}],
    }


def _invalid_fix_response() -> dict:
    return {
        "reply": "수정했습니다.",
        "changed": True,
        "name": "잘못된 수정",
        "nodes": [{"id": "n1", "type": "data.price", "params": {}}],  # 스케줄러 없음 -> 검증 실패
        "edges": [],
    }


def test_explain_returns_reply_without_graph():
    ai_client = FakeAIClient(responses=[_explain_response()])
    result = explain_backtest(ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, _SELECTION, "왜 매수가 없었어?")

    assert result["changed"] is False
    assert result["graph"] is None
    assert result["disclaimer"] is None
    assert "조건식" in result["reply"]
    assert len(ai_client.calls) == 1
    assert "filtered_out" in ai_client.calls[0][1]


def test_explain_fix_succeeds_on_first_try():
    ai_client = FakeAIClient(responses=[_fix_response()])
    result = explain_backtest(
        ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, _SELECTION, "이 구간에서도 매수가 되게 고쳐줘"
    )

    assert result["changed"] is True
    assert result["disclaimer"] == BACKTEST_EXPLAIN_DISCLAIMER
    assert result["graph"]["nodes"][2]["params"]["expr"] == "True"
    assert len(ai_client.calls) == 1


def test_explain_fix_retries_once_then_succeeds():
    ai_client = FakeAIClient(responses=[_invalid_fix_response(), _fix_response()])
    result = explain_backtest(
        ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, _SELECTION, "이 구간에서도 매수가 되게 고쳐줘"
    )

    assert len(ai_client.calls) == 2
    assert result["changed"] is True
    assert "검증 오류" in ai_client.calls[1][1]


def test_explain_fix_raises_after_two_failures():
    ai_client = FakeAIClient(responses=[_invalid_fix_response(), _invalid_fix_response()])
    with pytest.raises(BacktestExplainError) as exc_info:
        explain_backtest(
            ai_client, "삼성전자 매수 전략", _CURRENT_GRAPH, _SELECTION, "이 구간에서도 매수가 되게 고쳐줘"
        )

    assert len(ai_client.calls) == 2
    assert len(exc_info.value.attempts) == 2
