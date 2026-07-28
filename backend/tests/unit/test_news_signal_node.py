"""ai.news_signal 노드 단위 테스트. 실제 크롤링/OpenAI 없이 FakeNewsTrader로 검증한다."""

from __future__ import annotations

from datetime import datetime

from app.nodes import load_all_nodes
from app.nodes.base import NodeContext, create_node

from .ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory

load_all_nodes()


def _ctx(symbols: dict[str, dict]) -> NodeContext:
    ctx = NodeContext(run_id="r1", mode="test", timestamp=datetime(2026, 7, 28))
    for symbol, data in symbols.items():
        ctx.symbols[symbol] = dict(data)
    return ctx


def _run(params: dict, factory: FakeNewsTraderFactory, symbols: dict[str, dict]) -> NodeContext:
    node = create_node("ai.news_signal", "news1", params)
    return node.execute(_ctx(symbols), news_trader_factory=factory)


def test_stock_axis_auto_maps_symbol_to_korean_name():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.42, "클러스터수": 5}})
    factory = FakeNewsTraderFactory(trader)

    out = _run({"axis": "종목", "pass_when": "호재(t)"}, factory, {"005930": {}})

    assert "005930" in out.symbols
    assert out.symbols["005930"]["news_true"] is True
    assert out.symbols["005930"]["news_verdict"] == "t"
    assert out.symbols["005930"]["news_score"] == 0.42
    assert trader.calls == [("stock", "삼성전자", 7)]
    assert factory.auto_update_calls == [True]

    decision = out.meta["decisions"]["news1"]["005930"]
    assert decision["pass"] is True
    assert "삼성전자" in decision["reason"]


def test_stock_axis_unmapped_symbol_fails_without_calling_trader():
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)

    out = _run({"axis": "종목"}, factory, {"999999": {}})

    assert "999999" not in out.symbols
    assert trader.calls == []  # 매핑 실패 시 조회 자체를 하지 않는다
    decision = out.meta["decisions"]["news1"]["999999"]
    assert decision["pass"] is False
    assert "매핑" in decision["reason"]


def test_sector_and_macro_axis_use_explicit_key():
    trader = FakeNewsTrader({
        "반도체 및 반도체 장비": {"판정": "f", "평균": -0.3, "클러스터수": 3},
        "증권": {"판정": "n", "평균": 0.0, "클러스터수": 1},
    })
    factory = FakeNewsTraderFactory(trader)

    out_sector = _run(
        {"axis": "섹터", "key": "반도체 및 반도체 장비", "pass_when": "악재(f)"},
        factory,
        {"005930": {}},
    )
    assert "005930" in out_sector.symbols
    assert out_sector.symbols["005930"]["news_verdict"] == "f"

    out_macro = _run({"axis": "거시경제", "key": "증권", "pass_when": "중립 아님"}, factory, {"005930": {}})
    assert "005930" not in out_macro.symbols  # 중립(n)이므로 "중립 아님" 조건 불통과

    assert ("sector", "반도체 및 반도체 장비", 7) in trader.calls
    assert ("macro", "증권", 7) in trader.calls


def test_pass_when_filters_correctly_for_all_three_options():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.5, "클러스터수": 2}})
    factory = FakeNewsTraderFactory(trader)

    assert "005930" in _run({"axis": "종목", "pass_when": "호재(t)"}, factory, {"005930": {}}).symbols
    assert "005930" not in _run({"axis": "종목", "pass_when": "악재(f)"}, factory, {"005930": {}}).symbols
    assert "005930" in _run({"axis": "종목", "pass_when": "중립 아님"}, factory, {"005930": {}}).symbols


def test_auto_update_param_is_forwarded_to_factory():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})
    factory = FakeNewsTraderFactory(trader)

    _run({"axis": "종목", "auto_update": False}, factory, {"005930": {}})

    assert factory.auto_update_calls == [False]


def test_trader_is_closed_after_execution():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})
    factory = FakeNewsTraderFactory(trader)

    _run({"axis": "종목"}, factory, {"005930": {}})

    assert trader.closed is True


def test_missing_provider_raises_runtime_error():
    node = create_node("ai.news_signal", "news1", {"axis": "종목"})
    try:
        node.execute(_ctx({"005930": {}}))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "news_trader_factory" in str(exc)
