"""ai.free_prompt 노드 단위 테스트 — 치환/도구 호출 두 데이터 조회 방식, 키 누락 정형검증,
AI 오류 시 개별 종목만 탈락하는지를 실제 OpenAI/크롤링 없이 FakeAIClient/FakeNewsTrader로
검증한다.
"""

from __future__ import annotations

from datetime import date, datetime

from app.ai.base import AIUnavailableError
from app.market_data.base import Bar, MarketDataProvider, OrderBook, PriceTick
from app.nodes import load_all_nodes
from app.nodes.base import NodeContext, create_node

from .ai_test_doubles import FakeAIClient, FakeNewsTrader, FakeNewsTraderFactory

load_all_nodes()


class _StubMarketData(MarketDataProvider):
    def __init__(self, prices: dict[str, PriceTick]):
        self._prices = prices

    def get_price(self, symbol: str) -> PriceTick:
        return self._prices[symbol]

    def get_orderbook(self, symbol: str) -> OrderBook:  # pragma: no cover - 미사용
        raise NotImplementedError

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:  # pragma: no cover - 미사용
        raise NotImplementedError


def _ctx(symbols: dict[str, dict]) -> NodeContext:
    ctx = NodeContext(run_id="r1", mode="test", timestamp=datetime(2026, 7, 28))
    for symbol, data in symbols.items():
        ctx.symbols[symbol] = dict(data)
    return ctx


def test_substitute_mode_resolves_placeholders_and_passes():
    ai = FakeAIClient(responses=[{"pass": True, "opinion": "매수", "confidence": 0.8, "reason": "호재 확인"}])
    node = create_node(
        "ai.free_prompt",
        "n1",
        {"prompt": "{{news_verdict}}가 t이면 매수", "data_mode": "치환"},
    )

    out = node.execute(_ctx({"005930": {"news_verdict": "t"}}), ai_client=ai)

    assert "005930" in out.symbols
    assert out.symbols["005930"]["n1_pass"] is True
    assert out.symbols["005930"]["n1_opinion"] == "매수"
    assert out.symbols["005930"]["n1_confidence"] == 0.8
    decision = out.meta["decisions"]["n1"]["005930"]
    assert decision["pass"] is True
    # 프롬프트에 플레이스홀더가 아니라 실제 값("t")이 치환되어 AI로 전달됐는지 확인
    _, user_prompt = ai.calls[0]
    assert "t가 t이면 매수" in user_prompt
    assert ai.purposes == ["free_prompt"]


def test_substitute_mode_fails_symbol_with_missing_key_without_calling_ai():
    ai = FakeAIClient(responses=[])  # 호출되면 AssertionError로 테스트가 실패한다
    node = create_node("ai.free_prompt", "n1", {"prompt": "{{news_verdict}}가 t이면 매수", "data_mode": "치환"})

    out = node.execute(_ctx({"005930": {}}), ai_client=ai)

    assert "005930" not in out.symbols
    assert ai.calls == []
    decision = out.meta["decisions"]["n1"]["005930"]
    assert decision["pass"] is False
    assert "news_verdict" in decision["reason"]
    assert decision["metrics"]["missing_keys"] == ["news_verdict"]


def test_tool_mode_calls_tool_and_uses_final_json():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.5, "클러스터수": 4}})
    factory = FakeNewsTraderFactory(trader)
    ai = FakeAIClient(
        tool_scripts=[
            [
                {"tool_calls": [{"name": "get_symbol_news_signal", "arguments": {"symbol": "005930"}}]},
                {"pass": True, "opinion": "매수", "confidence": 0.6, "reason": "뉴스 호재"},
            ]
        ]
    )
    node = create_node(
        "ai.free_prompt",
        "n1",
        {"prompt": "뉴스가 좋으면 매수해줘", "data_mode": "AI 직접 조회(도구 호출)"},
    )

    out = node.execute(_ctx({"005930": {}}), ai_client=ai, news_trader_factory=factory)

    assert "005930" in out.symbols
    assert out.symbols["005930"]["n1_pass"] is True
    assert ai.tool_calls == [("get_symbol_news_signal", {"symbol": "005930"}, "free_prompt")]
    assert trader.calls == [("stock", "삼성전자", None, None)]


def test_tool_mode_does_not_hard_fail_on_missing_key():
    """치환 모드와 달리 도구 모드는 누락 키가 있어도 AI 호출 자체는 계속 진행한다."""
    ai = FakeAIClient(tool_scripts=[[{"pass": False, "opinion": "중립", "confidence": 0.1, "reason": "정보 부족"}]])
    node = create_node(
        "ai.free_prompt",
        "n1",
        {"prompt": "{{news_verdict}}를 참고해서 판단", "data_mode": "AI 직접 조회(도구 호출)"},
    )

    out = node.execute(_ctx({"005930": {}}), ai_client=ai)

    assert len(ai.calls) == 1  # AI가 실제로 호출됨(치환 모드였다면 0)
    assert "005930" not in out.symbols  # 이번엔 AI 스스로 pass=False라고 답했을 뿐


def test_ai_unavailable_fails_only_that_symbol():
    ai = FakeAIClient(available=False)
    node = create_node("ai.free_prompt", "n1", {"prompt": "아무 조건이나", "data_mode": "치환"})

    out = node.execute(_ctx({"005930": {}}), ai_client=ai)

    assert "005930" not in out.symbols
    decision = out.meta["decisions"]["n1"]["005930"]
    assert decision["pass"] is False
    assert "AI 미설정" in decision["reason"]


def test_ai_json_error_fails_only_that_symbol_and_continues_others():
    class _BrokenAIClient(FakeAIClient):
        def complete_json(self, *a, **kw):
            raise RuntimeError("malformed response")

    ai = _BrokenAIClient()
    node = create_node("ai.free_prompt", "n1", {"prompt": "아무 조건이나", "data_mode": "치환"})

    out = node.execute(_ctx({"005930": {}, "000660": {}}), ai_client=ai)

    assert out.symbols == {}
    assert out.meta["decisions"]["n1"]["005930"]["pass"] is False
    assert out.meta["decisions"]["n1"]["000660"]["pass"] is False
    assert len(out.meta["errors"]) == 2


def test_get_price_tool_reads_market_data_provider():
    ai = FakeAIClient(
        tool_scripts=[
            [
                {"tool_calls": [{"name": "get_price", "arguments": {"symbol": "005930"}}]},
                {"pass": True, "opinion": "매수", "confidence": 0.5, "reason": "가격 확인"},
            ]
        ]
    )
    market_data = _StubMarketData({"005930": PriceTick("005930", 71000.0, 70000.0, 1000, datetime(2026, 7, 28))})
    node = create_node(
        "ai.free_prompt", "n1", {"prompt": "현재가를 조회해봐", "data_mode": "AI 직접 조회(도구 호출)"}
    )

    out = node.execute(_ctx({"005930": {}}), ai_client=ai, market_data=market_data)

    assert out.symbols["005930"]["n1_pass"] is True
    assert ai.tool_calls == [("get_price", {"symbol": "005930"}, "free_prompt")]


def test_validate_params_rejects_unbalanced_placeholder_braces():
    node = create_node("ai.free_prompt", "n1", {"prompt": "{{news_verdict가 t이면 매수"})

    errors = node.validate_params()

    assert any("괄호" in e for e in errors)


def test_multiple_instances_do_not_collide_on_output_keys():
    ai = FakeAIClient(
        responses=[
            {"pass": True, "opinion": "매수", "confidence": 0.9, "reason": "a"},
            {"pass": True, "opinion": "매도", "confidence": 0.4, "reason": "b"},
        ]
    )
    node1 = create_node("ai.free_prompt", "n1", {"prompt": "판단1", "data_mode": "치환"})
    node2 = create_node("ai.free_prompt", "n2", {"prompt": "판단2", "data_mode": "치환"})

    ctx1 = node1.execute(_ctx({"005930": {}}), ai_client=ai)
    ctx2 = node2.execute(ctx1, ai_client=ai)

    data = ctx2.symbols["005930"]
    assert data["n1_opinion"] == "매수"
    assert data["n2_opinion"] == "매도"
