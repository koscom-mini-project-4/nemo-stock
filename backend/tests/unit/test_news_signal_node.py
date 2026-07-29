"""ai.news_signal 노드 단위 테스트. 실제 크롤링/OpenAI 없이 FakeNewsTrader로 검증한다."""

from __future__ import annotations

from datetime import date, datetime

from app.nodes import load_all_nodes
from app.nodes.ai.news_signal import resolve_news_signal_clusters
from app.nodes.base import NodeContext, create_node
from app.workflow.graph import NodeDef

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
    # start는 실행일 그 자체가 아니라 period_days만큼 앞당긴 날짜여야 한다(2026-07-28 - 7일).
    # newsstock-lib의 window(start, period)는 [start, start+period]로 앞을 보는 라이브러리라,
    # 실행일을 그대로 start로 넘기면 미래를 보게 되는 룩어헤드 버그가 있었다(회귀 방지).
    assert trader.calls == [("stock", "삼성전자", "2026-07-21", 7)]
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

    assert ("sector", "반도체 및 반도체 장비", "2026-07-21", 7) in trader.calls
    assert ("macro", "증권", "2026-07-21", 7) in trader.calls


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


def test_indicator_calc_params_are_forwarded_to_factory():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})
    factory = FakeNewsTraderFactory(trader)

    _run(
        {
            "axis": "종목",
            "threshold": 0.25,
            "decay_base": 0.5,
            "include_zero": False,
            "decay_from": "start",
        },
        factory,
        {"005930": {}},
    )

    assert factory.calls == [
        {"auto_update": True, "threshold": 0.25, "decay_base": 0.5, "include_zero": False, "decay_from": "start", "model": None}
    ]


def test_indicator_calc_params_default_when_not_set():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})
    factory = FakeNewsTraderFactory(trader)

    _run({"axis": "종목"}, factory, {"005930": {}})

    assert factory.calls == [
        {"auto_update": True, "threshold": 0.1, "decay_base": 0.3, "include_zero": True, "decay_from": "end", "model": None}
    ]


def test_missing_provider_raises_runtime_error():
    node = create_node("ai.news_signal", "news1", {"axis": "종목"})
    try:
        node.execute(_ctx({"005930": {}}))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "news_trader_factory" in str(exc)


def test_query_window_ends_at_context_timestamp_without_lookahead():
    """백테스트는 과거 날짜로 context.timestamp를 바꿔가며 같은 노드를 반복 실행한다.

    회귀 대상 버그: newsstock-lib의 window(start, period)는 [start, start+period]로 "앞으로"
    조회하는 라이브러리라, 실행일(as-of 날짜)을 그대로 start로 넘기면 [그날, 그날+7일]이 되어
    백테스트가 미래(그날 이후 실제로 크롤링된 뉴스)를 참고하는 룩어헤드 버그가 생겼다(실사용
    중 발견 — §status.md 2026-07-29 참조). start는 as-of 날짜가 구간의 "끝"이 되도록
    period_days만큼 앞당긴 날짜여야 한다: [그날-period_days, 그날]."""
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})
    factory = FakeNewsTraderFactory(trader)
    node = create_node("ai.news_signal", "news1", {"axis": "종목"})

    ctx = NodeContext(run_id="r1", mode="backtest", timestamp=datetime(2026, 6, 1))
    ctx.symbols["005930"] = {}
    node.execute(ctx, news_trader_factory=factory)

    assert trader.calls == [("stock", "삼성전자", "2026-05-25", 7)]


def test_top_topic_surfaces_the_largest_contributing_cluster():
    """사용자 요청: true/false 판정에 어떤 주제가 가장 큰 영향을 미쳤는지 확인 가능해야 한다."""
    trader = FakeNewsTrader({
        "삼성전자": {
            "판정": "f",
            "평균": -0.27,
            "클러스터수": 2,
            "클러스터": [
                {"클러스터id": 1, "대표제목": "삼성전자 신규 스마트폰 공개", "점수": 0.12},
                {"클러스터id": 2, "대표제목": "코스피 서킷브레이커 발동", "점수": -0.99},
            ],
        }
    })
    factory = FakeNewsTraderFactory(trader)

    # verdict="f"는 "중립 아님" 조건을 통과하므로 symbols[code]에도 필드가 남는다.
    out = _run({"axis": "종목", "pass_when": "중립 아님"}, factory, {"005930": {}})

    data = out.meta["decisions"]["news1"]["005930"]
    assert data["metrics"]["top_topic"] == "코스피 서킷브레이커 발동"
    assert data["metrics"]["top_topic_score"] == -0.99
    assert "코스피 서킷브레이커 발동" in data["reason"]
    assert out.symbols["005930"]["news_top_topic"] == "코스피 서킷브레이커 발동"
    assert out.symbols["005930"]["news_top_topic_score"] == -0.99


def test_top_topic_is_none_without_cluster_detail():
    trader = FakeNewsTrader({"삼성전자": {"판정": "t", "평균": 0.1, "클러스터수": 1}})  # 클러스터 목록 없음
    factory = FakeNewsTraderFactory(trader)

    out = _run({"axis": "종목"}, factory, {"005930": {}})

    assert out.symbols["005930"]["news_top_topic"] is None
    assert out.symbols["005930"]["news_top_topic_score"] is None


def test_resolve_news_signal_clusters_returns_cluster_list_for_matching_node():
    """app/api/routers/backtest.py(마커)와 app/api/routers/ai.py(AI 설명 근거)가 공유하는
    헬퍼. 워크플로의 ai.news_signal 노드 파라미터로 축/키를 결정해 클러스터 원본을 반환한다."""
    trader = FakeNewsTrader({
        "삼성전자": {
            "판정": "t",
            "평균": 0.3,
            "클러스터수": 2,
            "클러스터": [
                {"클러스터id": 1, "대표제목": "삼성전자 신규 스마트폰 공개", "최초발생날짜": "2026-07-24"},
                {"클러스터id": 2, "대표제목": "코스피 서킷브레이커 발동", "최초발생날짜": "2026-07-25"},
            ],
        }
    })
    factory = FakeNewsTraderFactory(trader)
    node = NodeDef(id="n3", type="ai.news_signal", params={"axis": "종목"})

    clusters = resolve_news_signal_clusters(node, "005930", date(2026, 7, 23), date(2026, 7, 28), factory)

    assert [c["클러스터id"] for c in clusters] == [1, 2]
    assert clusters[0]["대표제목"] == "삼성전자 신규 스마트폰 공개"
    # 회귀 대상: window는 [start_date - period_days, end_date]여야 한다(2026-07-23 - 7일 =
    # 2026-07-16, span은 (end-start).days + period_days = 5+7=12). 이전 버그는 [start_date,
    # end_date + period_days]를 조회해 end_date 이후로 새는 방향이 반대였다.
    assert trader.calls == [("stock", "삼성전자", "2026-07-16", 12)]


def test_resolve_news_signal_clusters_returns_empty_for_non_news_signal_node():
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)
    node = NodeDef(id="n3", type="data.price", params={})

    clusters = resolve_news_signal_clusters(node, "005930", date(2026, 7, 23), date(2026, 7, 28), factory)

    assert clusters == []


def test_resolve_news_signal_clusters_returns_empty_when_symbol_unmapped():
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)
    node = NodeDef(id="n3", type="ai.news_signal", params={"axis": "종목"})

    clusters = resolve_news_signal_clusters(node, "UNMAPPED", date(2026, 7, 23), date(2026, 7, 28), factory)

    assert clusters == []
