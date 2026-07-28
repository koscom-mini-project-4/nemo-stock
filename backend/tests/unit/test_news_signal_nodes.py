"""Phase 3 — 뉴스 신호 노드가 계산+조건을 자체 내장해 종목을 필터링하는지 검증(IF 노드 없이)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.broker.dummy import DummyOrderExecutionProvider
from app.dao.base import NewsSignalRecord
from app.dao.memory.repositories import InMemoryNewsSignalRepository
from app.market_data.dummy import DummyMarketDataProvider
from app.nodes import load_all_nodes
from app.workflow.engine import WorkflowEngine
from app.workflow.events import InMemoryEventBus
from app.workflow.graph import WorkflowGraph

load_all_nodes()

AS_OF = datetime(2026, 7, 19, 12, 0, 0)


def _sig(days_ago, *, symbol=None, sector=None, event_type="General_Market", themes=None, sector_score=0.0):
    return NewsSignalRecord(
        id=f"s-{days_ago}-{sector}-{event_type}-{sector_score}-{themes}-{id(themes)}",
        symbol=symbol, sector=sector, direction=0, event_type=event_type,
        themes=themes or [], base_impact=sector_score, sector_score=sector_score,
        domestic_score=0.0, overseas_score=0.0,
        published_at=AS_OF - timedelta(days=days_ago),
    )


def _run(graph_dict, signal_repo):
    graph = WorkflowGraph.from_dict(graph_dict)
    engine = WorkflowEngine(InMemoryEventBus())
    market_data = DummyMarketDataProvider(seed_prices={"005930": 70000}, seed=1)
    broker = DummyOrderExecutionProvider(initial_cash=100_000_000)
    return engine.execute(
        workflow_id="wf1", graph=graph, mode="test", market_data=market_data, broker=broker,
        timestamp=AS_OF, extra_providers={"news_signal_repo": signal_repo},
    )


def _breakout_signals():
    repo = InMemoryNewsSignalRepository()
    repo.save_many([
        _sig(1, sector="반도체", sector_score=0.9),
        _sig(2, sector="반도체", sector_score=0.3),  # 평균 0.6
        _sig(1, themes=["HBM"]), _sig(1, themes=["HBM"]), _sig(1, themes=["HBM"]),
        _sig(0, themes=["HBM"]), _sig(0, themes=["HBM"]),  # 테마 z ≈ 2.83
    ])
    return repo


def test_chained_condition_nodes_are_AND_and_trigger_buy():
    """조건 내장 노드 2개를 직렬 연결 = AND. 둘 다 만족 → 매수(IF 노드 없음)."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.sector_momentum",
             "params": {"sector": "반도체", "window_days": 7, "condition": "leader"}},  # ≥0.5
            {"id": "n4", "type": "data.theme_zscore",
             "params": {"theme": "HBM", "lookback_days": 20, "condition": "spike"}},  # ≥1.5
            {"id": "n5", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"}, {"from": "n4", "to": "n5"},
        ],
    }
    result = _run(graph, _breakout_signals())
    assert result.status == "success"
    data = result.final_context.symbols["005930"]
    assert data["order_status"] == "filled"
    assert data["sector_momentum"] == 0.6
    assert data["theme_zscore"] >= 1.5


def test_custom_condition_blocks_when_threshold_not_met():
    """'직접 설정'(custom) 연산자/기준값으로도 필터링. 0.6 < 0.9 → 탈락 → 매수 없음."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.sector_momentum",
             "params": {"sector": "반도체", "window_days": 7,
                        "condition": "custom", "operator": "이상", "threshold": 0.9}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"},
        ],
    }
    result = _run(graph, _breakout_signals())
    assert result.status == "success"
    assert result.final_context.symbols == {}  # 조건 미달로 탈락


def test_pass_preset_does_not_filter():
    """'필터 없이 통과'(pass) 프리셋은 값만 노출하고 종목을 드롭하지 않는다."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.sector_momentum",
             "params": {"sector": "반도체", "window_days": 7, "condition": "pass"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"},
        ],
    }
    result = _run(graph, _breakout_signals())
    data = result.final_context.symbols["005930"]
    assert data["sector_momentum"] == 0.6
    assert data["order_status"] == "filled"  # pass → 필터 안 함 → 매수


def test_macro_risk_kill_switch_preset():
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.macro_risk", "params": {"window_days": 3, "condition": "fear"}},  # ≥40%
            {"id": "n4", "type": "execution.market_order", "params": {"side": "sell", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"},
        ],
    }
    repo = InMemoryNewsSignalRepository()
    repo.save_many([
        _sig(0, event_type="Geopolitical_Risk"),
        _sig(1, event_type="Macro_Indicator"),
        _sig(1, event_type="General_Market"),  # 리스크성 2/3 = 66.7% ≥ 40
    ])
    result = _run(graph, repo)
    assert result.status == "success"
    data = result.final_context.symbols["005930"]
    assert round(data["macro_risk_density"], 1) == 66.7
    assert data.get("order_status") is not None  # 조건 통과 → execution 도달


def test_symbol_news_score_filters_per_symbol():
    """종목별 필터: 005930은 긍정, 000660은 부정 → 005930만 통과."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval",
             "params": {"interval_sec": 60, "universe": "005930,000660"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.symbol_news_score",
             "params": {"window_days": 7, "condition": "positive"}},  # ≥0.5
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    }
    repo = InMemoryNewsSignalRepository()
    repo.save_many([
        _sig(1, symbol="005930", sector_score=1.5),   # base_impact 1.5
        _sig(1, symbol="000660", sector_score=-1.0),  # base_impact -1.0
    ])
    result = _run(graph, repo)
    syms = result.final_context.symbols
    assert "005930" in syms and "000660" not in syms


def test_extended_condition_nodes_chain():
    """확장 지표 3종을 조건 내장 상태로 직렬 연결(AND) → 모두 통과 시 매수."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "data.macro_sentiment", "params": {"window_days": 5, "condition": "dom_ok"}},
            {"id": "n4", "type": "data.sentiment_ratio",
             "params": {"sector": "반도체", "window_days": 7, "condition": "bullish"}},
            {"id": "n5", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"}, {"from": "n4", "to": "n5"},
        ],
    }
    repo = InMemoryNewsSignalRepository()
    repo.save_many([
        NewsSignalRecord(
            id="a", symbol="005930", sector="반도체", direction=1, event_type="M&A_Investment",
            themes=["HBM"], base_impact=1.5, sector_score=1.5, domestic_score=1.5, overseas_score=0.0,
            published_at=AS_OF - timedelta(days=1),
        ),
        NewsSignalRecord(
            id="b", symbol="005930", sector="반도체", direction=1, event_type="Earnings_Contract",
            themes=[], base_impact=1.2, sector_score=1.2, domestic_score=0.0, overseas_score=0.0,
            published_at=AS_OF - timedelta(days=2),
        ),
    ])
    result = _run(graph, repo)
    assert result.status == "success"
    data = result.final_context.symbols["005930"]
    assert data["domestic_macro_index"] == 0.75  # (1.5+0)/2 ≥ 0
    assert data["sentiment_ratio"] == 1.0         # 호재 2/2 ≥ 0.3
    assert data["order_status"] == "filled"
