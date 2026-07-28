from __future__ import annotations

from datetime import date, datetime, timedelta

from app.backtest.runner import PROGRESS_NODE_ID, BacktestRunner
from app.dao.base import AIUsageRecord, AIUsageRepository, PriceBarRecord
from app.dao.memory.repositories import InMemoryNodeEventRepository, InMemoryPriceBarRepository, InMemoryRunRepository
from app.market_data.historical import HistoricalMarketDataProvider
from app.nodes import load_all_nodes
from app.workflow.engine import WorkflowEngine
from app.workflow.events import InMemoryEventBus
from app.workflow.graph import WorkflowGraph

load_all_nodes()


class _FakeAIUsageRepo(AIUsageRepository):
    def __init__(self) -> None:
        self.saved: list[AIUsageRecord] = []

    def save(self, record: AIUsageRecord) -> None:
        self.saved.append(record)

    def list_since(self, since: datetime | None) -> list[AIUsageRecord]:
        if since is None:
            return list(self.saved)
        return [r for r in self.saved if r.created_at >= since]


def _seed_uptrend(repo: InMemoryPriceBarRepository, symbol: str, start: date, days: int, start_price: float) -> None:
    """일정하게 우상향하는 합성 가격 시계열을 만든다(결정적 백테스트 결과를 위해)."""
    price = start_price
    bars = []
    for i in range(days):
        d = start + timedelta(days=i)
        open_ = price
        close = price * 1.01  # 매일 1% 상승
        bars.append(
            PriceBarRecord(
                symbol=symbol, trade_date=d, open=open_, high=close, low=open_, close=close, volume=10000,
            )
        )
        price = close
    repo.save_many(bars)


def _buy_on_uptrend_graph() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 1, "universe": "TESTSYM"}},
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


def test_historical_provider_replays_bars_up_to_advance_date():
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=10, start_price=100.0)

    provider = HistoricalMarketDataProvider(repo, universe=["TESTSYM"])
    provider.advance_to(start + timedelta(days=4))
    tick = provider.get_price("TESTSYM")
    # 5번째 거래일(index 4)까지의 데이터만 보여야 한다.
    assert tick.price > 100.0
    bars = provider.get_ohlcv("TESTSYM", start, start + timedelta(days=4))
    assert len(bars) == 5


def test_backtest_runner_on_synthetic_uptrend_produces_positive_return():
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=20, start_price=100.0)

    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    run_repo = InMemoryRunRepository()
    node_event_repo = InMemoryNodeEventRepository()
    runner = BacktestRunner(engine, repo, run_repo, node_event_repo, bus)

    result = runner.run(
        workflow_id="wf1",
        graph=graph,
        universe=["TESTSYM"],
        start=start,
        end=start + timedelta(days=19),
        initial_capital=1_000_000.0,
    )

    assert result.trading_days == 20
    assert len(result.equity_curve) == 20
    # 매일 상승하는 종목을 계속 사들이므로 최종 자산이 초기 자본보다 커야 한다.
    assert result.final_equity > result.initial_capital
    assert result.metrics.total_return_pct > 0
    assert result.metrics.mdd_pct == 0.0  # 우상향만 하므로 낙폭이 없어야 한다

    # 거래일마다 별도 run_id로 RunRecord/NodeEventRecord가 저장되어야 한다(일자별 그래프 재생용).
    assert len(result.daily_runs) == 20
    for day, run_id in result.daily_runs:
        assert run_repo.get(run_id) is not None
        assert run_repo.get(run_id).mode == "backtest"
        assert len(node_event_repo.list_by_run(run_id)) > 0

    # 매일 상승하는 합성 시세라 조건이 매일 통과 -> 매수도 매일 체결되며, OrderResult.filled_at은
    # 실제 벽시계 시각이므로 러너가 시뮬레이션 날짜를 직접 태깅해야 한다.
    assert result.universe == ["TESTSYM"]
    assert len(result.trades) == 20
    daily_run_ids = {run_id for _, run_id in result.daily_runs}
    for day, run_id, order in result.trades:
        assert order.symbol == "TESTSYM"
        assert order.side == "buy"
        assert order.status == "filled"
        assert run_id in daily_run_ids
    assert {d for d, _, _ in result.trades} == {d for d, _ in result.daily_runs}


def test_progress_events_published_started_and_per_day_then_closed(monkeypatch):
    """§0-11: progress_run_id를 주면 시작 이벤트 1건 + 거래일마다 진행 이벤트가 event_bus에
    발행되고, 끝나면 close_run으로 스트림이 닫혀야 한다.

    close_run 호출 여부는 실제로 재구독(subscribe)해서 확인하지 않는다 —
    InMemoryEventBus.close_run은 "그 시점에 이미 구독 중인" 큐에만 종료 신호를 보내므로,
    끝난 뒤 새로 subscribe하면 신호를 못 받아 영원히 블로킹된다(운영상 문제는 아님 — WS는
    항상 백테스트 시작 전에 먼저 구독하므로 늦게 구독하는 경우가 없다. 테스트에서만
    이 순서 문제가 생기므로 monkeypatch로 호출 여부만 스파이한다).
    """
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=5, start_price=100.0)

    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    runner = BacktestRunner(engine, repo, InMemoryRunRepository(), InMemoryNodeEventRepository(), bus)

    closed_runs: list[str] = []
    original_close_run = bus.close_run
    monkeypatch.setattr(bus, "close_run", lambda run_id: (closed_runs.append(run_id), original_close_run(run_id)))

    runner.run(
        workflow_id="wf1", graph=graph, universe=["TESTSYM"],
        start=start, end=start + timedelta(days=4), initial_capital=1_000_000.0,
        progress_run_id="progress-1",
    )

    events = bus.get_history("progress-1")
    assert len(events) == 6  # 시작 1건 + 거래일 5건
    assert all(e.node_id == PROGRESS_NODE_ID for e in events)

    started = events[0]
    assert started.output_snapshot["day"] is None
    assert started.output_snapshot["day_index"] == 0
    assert started.output_snapshot["total_days"] == 5
    assert started.status == "running"

    per_day = events[1:]
    assert [e.output_snapshot["day_index"] for e in per_day] == [1, 2, 3, 4, 5]
    assert all(e.status == "success" for e in per_day)
    assert all(e.output_snapshot["orders"] == 1 for e in per_day)  # 우상향 그래프는 매일 매수
    assert all(e.output_snapshot["ai_tokens_delta"] is None for e in per_day)  # usage_repo 미주입
    assert all(e.node_type == "backtest.progress" for e in events)

    # WorkflowEngine.execute()도 거래일마다 자기 자신의 run_id를 close_run하므로(§8, 노드별
    # 디버그 재생 채널), closed_runs에는 그것들도 섞여 들어온다 — progress_run_id가 최소
    # 한 번은 닫혔는지만 확인한다.
    assert closed_runs.count("progress-1") == 1


def test_progress_events_include_ai_token_delta_from_usage_repo():
    """거래일마다 ai_usage_repo.list_since()를 조회해 그 델타가 진행 이벤트에 실려야 한다."""

    class _StubUsageRepo(AIUsageRepository):
        def __init__(self, tokens_per_call: int):
            self._tokens = tokens_per_call
            self.call_count = 0

        def save(self, record: AIUsageRecord) -> None:  # pragma: no cover - 미사용
            pass

        def list_since(self, since):
            self.call_count += 1
            return [
                AIUsageRecord(
                    id=str(self.call_count), purpose="test", model="m",
                    prompt_tokens=self._tokens, completion_tokens=0, total_tokens=self._tokens,
                )
            ]

    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=3, start_price=100.0)
    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    usage_repo = _StubUsageRepo(tokens_per_call=42)
    runner = BacktestRunner(
        engine, repo, InMemoryRunRepository(), InMemoryNodeEventRepository(), bus, ai_usage_repo=usage_repo
    )

    runner.run(
        workflow_id="wf1", graph=graph, universe=["TESTSYM"],
        start=start, end=start + timedelta(days=2), initial_capital=1_000_000.0,
        progress_run_id="progress-2",
    )

    per_day = [e for e in bus.get_history("progress-2") if e.output_snapshot["day"] is not None]
    assert len(per_day) == 3
    assert all(e.output_snapshot["ai_tokens_delta"] == 42 for e in per_day)
    assert usage_repo.call_count == 3


def test_progress_stream_closed_even_when_engine_raises(monkeypatch):
    """거래일 처리 중 예외가 나도 close_run은 finally에서 반드시 호출돼야 한다(WS가 영원히
    열려있지 않도록)."""
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=3, start_price=100.0)
    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    runner = BacktestRunner(engine, repo, InMemoryRunRepository(), InMemoryNodeEventRepository(), bus)

    def _boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(engine, "execute", _boom)

    closed_runs: list[str] = []
    original_close_run = bus.close_run
    monkeypatch.setattr(bus, "close_run", lambda run_id: (closed_runs.append(run_id), original_close_run(run_id)))

    import pytest

    with pytest.raises(RuntimeError):
        runner.run(
            workflow_id="wf1", graph=graph, universe=["TESTSYM"],
            start=start, end=start + timedelta(days=2), initial_capital=1_000_000.0,
            progress_run_id="progress-3",
        )

    assert closed_runs == ["progress-3"]
    # 예외가 첫 거래일에서 났으므로 시작 이벤트 1건만 발행되고 거래일 진행 이벤트는 없어야 한다.
    assert [e.node_id for e in bus.get_history("progress-3")] == [PROGRESS_NODE_ID]


def test_backtest_runner_raises_when_no_price_data():
    repo = InMemoryPriceBarRepository()
    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    runner = BacktestRunner(engine, repo, InMemoryRunRepository(), InMemoryNodeEventRepository(), bus)

    import pytest

    with pytest.raises(ValueError):
        runner.run(
            workflow_id="wf1",
            graph=graph,
            universe=["TESTSYM"],
            start=date(2025, 1, 1),
            end=date(2025, 1, 10),
        )
